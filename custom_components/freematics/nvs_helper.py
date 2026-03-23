"""NVS (Non-Volatile Storage) partition generator for Freematics ONE+.

Generates an ESP32 NVS binary partition image that is flashed alongside
the firmware so the device boots with the user's WiFi / server settings
already applied – no manual configuration required after flashing.

The generated image is compatible with the NVS partition at offset 0x9000
used by the 'huge_app' partition scheme (board_build.partitions = huge_app.csv).

Stored NVS keys (namespace "storage"):
  WIFI_SSID     – WiFi SSID
  WIFI_PWD      – WiFi password
  CELL_APN      – Cellular APN (empty string = auto)
  SIM_PIN       – SIM card PIN (empty string = no PIN / unlocked)
  SERVER_HOST   – HA hostname / Nabu Casa hooks.nabu.casa (firmware v5.1+)
  SERVER_PORT   – HTTPS port, usually 443 (firmware v5.1+)
  WEBHOOK_PATH  – Full path: /api/webhook/<webhook_id> (firmware v5.1+)
  CELL_HOST     – Cellular-specific server host (overrides SERVER_HOST for
                  cellular connections, firmware v5.1+).  Set to
                  hooks.nabu.casa when Nabu Casa cloud is active so that
                  SIM7600 devices use the cloud webhook endpoint directly
                  rather than the Remote UI proxy (*.ui.nabu.casa).
  CELL_PATH     – Cellular-specific webhook path (overrides WEBHOOK_PATH
                  for cellular connections, firmware v5.1+).  Contains the
                  opaque token path returned by async_create_cloudhook().
  CELL_PORT     – Cellular-specific server port (overrides SERVER_PORT,
                  firmware v5.1+).  Usually 443; stored alongside CELL_HOST.
  ENABLE_HTTPD  – 1 = start built-in HTTP server on boot (firmware with ENABLE_HTTPD=1)
  ENABLE_BLE    – 0 = disable BLE SPP server (frees ~100 KB heap for TLS webhook)
  DATA_INTERVAL – Telemetry post interval in ms (≥500; 0 = firmware default ≈1000 ms)
  SYNC_INTERVAL – Server-sync check interval in seconds (0 = firmware default 120 s)
  OTA_TOKEN     – Secret token embedded in the pull-OTA endpoint URL path
                  (firmware v5.2+).  When set, the device periodically GETs
                  ``{OTA_HOST}:{OTA_PORT}/api/freematics/ota_pull/{OTA_TOKEN}/meta.json``
                  and downloads new firmware if available.
  OTA_HOST      – Hostname of the HA server serving pull-OTA files (firmware v5.2+).
                  May differ from SERVER_HOST when Nabu Casa cloud is active.
  OTA_PORT      – TCP port for OTA_HOST (u16, firmware v5.2+, default 443).
  OTA_INTERVAL  – Seconds between pull-OTA checks (u16, firmware v5.2+, 0 = off).
  NVS_VER       – Settings version string (firmware v5.2+).  Written by the HA
                  integration to record which settings revision was flashed.
                  The firmware prints this string at boot so the user can
                  verify the correct NVS partition was applied.  Format:
                  "<firmware_version>.<settings_timestamp>", e.g.
                  "5.1.2026-03-16T16:11:20+00:00".

Single-file flash image (esptool)
----------------------------------
generate_flash_image() combines the second-stage bootloader, partition table,
NVS partition, and the application firmware into one binary written at
BOOTLOADER_PARTITION_OFFSET (0x1000).

Including the bootloader is critical: esp-web-tools performs a chip erase on
the first installation ("new install"), wiping the bootloader at 0x1000.
Without restoring it the ROM bootloader cannot hand off to the second-stage
bootloader and the device loops endlessly with "flash read err, 1000".
Writing the combined image at 0x1000 ensures the bootloader is always present.

  **Important**: Do NOT use the Freematics Builder with this combined image.
  The Builder writes binaries at the app partition offset (0x10000), which
  places partition-table data where firmware belongs and causes a restart loop.
  For the Freematics Builder, use telelogger.bin (firmware only) and provision
  NVS settings separately via the browser-based flasher.

  Layout (relative to BOOTLOADER_PARTITION_OFFSET = 0x1000):
    0x0000 – bootloader_size  Second-stage bootloader (bootloader.bin, DIO/40 MHz)
    [padding to 0x7000]       0xFF (reserved)
    0x7000 – 0x7FFF           Partition table  (huge_app scheme, 4 KB)
    0x8000 – 0xCFFF           NVS partition    (config_nvs.bin, 20 KB)
    0xD000 – 0xEFFF           0xFF padding     (otadata region – preserved as erased)
    0xF000 –  end             Application firmware (telelogger.bin, flash mode = DIO)

  esptool usage:
    python -m esptool write-flash 0x1000 flash_image.bin
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import struct
import tempfile
import types
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Flash offset of the second-stage bootloader (always 0x1000 on ESP32).
BOOTLOADER_PARTITION_OFFSET = 0x1000

# Flash offset of the partition table (same across all ESP32 schemes).
PARTITION_TABLE_OFFSET = 0x8000

# Size of the ESP32 partition table block.
PARTITION_TABLE_SIZE = 0x1000  # 4 096 bytes

# Standard ESP32 NVS partition size used by the huge_app partition scheme.
NVS_PARTITION_SIZE = 0x5000  # 20 480 bytes

# Flash offset of the NVS partition in the huge_app scheme.
NVS_PARTITION_OFFSET = 0x9000

# Flash offset of the application partition (same across all common ESP32 schemes).
APP_PARTITION_OFFSET = 0x10000

# Byte offsets within the combined flash image (relative to BOOTLOADER_PARTITION_OFFSET).
# The combined image now starts at 0x1000 so the bootloader is always included.
_PT_OFFSET_IN_IMAGE = PARTITION_TABLE_OFFSET - BOOTLOADER_PARTITION_OFFSET   # 0x7000
_NVS_OFFSET_IN_IMAGE = NVS_PARTITION_OFFSET - BOOTLOADER_PARTITION_OFFSET    # 0x8000
_APP_OFFSET_IN_IMAGE = APP_PARTITION_OFFSET - BOOTLOADER_PARTITION_OFFSET    # 0xF000

# ---------------------------------------------------------------------------
# Partition-table generation
# ---------------------------------------------------------------------------
# Each partition entry is 32 bytes:
#   2 B magic (0xAA 0x50) | 1 B type | 1 B subtype | 4 B offset | 4 B size
#   | 16 B label (null-padded) | 4 B flags
_PT_MAGIC = b"\xaa\x50"
_PT_MD5_MAGIC = b"\xeb\xeb"
_PT_ENTRY_SIZE = 32

# Dual-OTA partition layout – required for WiFi OTA updates to work.
#
# Background: huge_app.csv (the previous layout) only had a single OTA app
# partition (app0/ota_0).  When an OTA update is attempted, ESP-IDF calls
# esp_ota_get_next_update_partition() which cycles through available OTA slots.
# With only one slot it returns ota_0 – the currently running partition.
# esp_ota_begin() then fails with ESP_ERR_OTA_PARTITION_CONFLICT (you cannot
# write OTA to the partition you are executing from), and the Arduino Update
# library responds by calling abort(), crashing the device mid-upload.
#
# This layout adds a second slot (app1/ota_1) so that:
#   – First OTA writes to ota_1 while running from ota_0
#   – Subsequent OTAs alternate between ota_0 and ota_1
#
# Layout (all offsets / sizes in hex):
#   nvs      data/nvs      0x9000   0x5000   (20 KB  – NVS key/value store)
#   otadata  data/ota      0xE000   0x2000   ( 8 KB  – OTA selection record)
#   app0     app/ota_0     0x10000  0x1F0000 (~1.94 MB – initial slot)
#   app1     app/ota_1     0x200000 0x1F0000 (~1.94 MB – first OTA target)
#
# Total used: 0x3F0000 ≈ 3.94 MB.  Both slots comfortably hold the current
# firmware binary (~1.75 MB) and the layout fits on 4 MB flash devices while
# leaving the upper portion of 16 MB devices free.
_FREEMATICS_PARTITIONS = [
    # (name, type, subtype, offset, size)
    ("nvs",     0x01, 0x02, 0x9000,   0x5000),
    ("otadata", 0x01, 0x00, 0xE000,   0x2000),
    ("app0",    0x00, 0x10, 0x10000,  0x1F0000),
    ("app1",    0x00, 0x11, 0x200000, 0x1F0000),
]


def _make_partition_entry(
    name: str, ptype: int, subtype: int, offset: int, size: int, flags: int = 0
) -> bytes:
    label = name.encode("utf-8")[:16].ljust(16, b"\x00")
    return (
        _PT_MAGIC
        + bytes([ptype, subtype])
        + struct.pack("<II", offset, size)
        + label
        + struct.pack("<I", flags)
    )


def generate_partition_table() -> bytes:
    """Return a 4 096-byte ESP32 partition-table binary (dual-OTA layout).

    The table contains two OTA app partitions (ota_0 at 0x10000 and ota_1 at
    0x200000, each 1.94 MB) so that WiFi OTA updates work correctly: the
    first OTA writes to ota_1 while the device runs from ota_0, avoiding the
    ESP_ERR_OTA_PARTITION_CONFLICT abort that occurs with a single-slot layout.

    Includes an MD5 checksum entry (compatible with ESP-IDF v4.x+) and is
    padded to PARTITION_TABLE_SIZE with 0xFF bytes.
    """
    entries = b"".join(
        _make_partition_entry(*p) for p in _FREEMATICS_PARTITIONS
    )
    md5_hash = hashlib.md5(entries).digest()
    md5_entry = _PT_MD5_MAGIC + b"\xff" * 14 + md5_hash
    table = entries + md5_entry
    table += b"\xff" * (PARTITION_TABLE_SIZE - len(table))
    return table


def _nvs_available() -> bool:
    """Return True if the esp_idf_nvs_partition_gen package is installed."""
    try:
        import esp_idf_nvs_partition_gen  # noqa: F401
        return True
    except ImportError:
        return False


def generate_nvs_partition(
    wifi_ssid: str = "",
    wifi_password: str = "",
    cell_apn: str = "",
    server_host: str = "",
    server_port: int = 443,
    webhook_path: str = "",
    enable_httpd: bool = False,
    enable_ble: bool = False,
    data_interval_ms: int = 0,
    sync_interval_s: int = 0,
    sim_pin: str = "",
    cell_server_host: str = "",
    cell_server_port: int = 443,
    cell_webhook_path: str = "",
    cell_debug: bool = False,
    led_red_en: bool = True,
    led_white_en: bool = True,
    beep_en: bool = True,
    ota_token: str = "",
    ota_host: str = "",
    ota_port: int = 443,
    ota_check_interval_s: int = 0,
    nvs_version: str = "",
    obd_en: bool = True,
    can_en: bool = False,
    standby_time_s: int = 0,
    deep_standby: bool = False,
) -> bytes | None:
    """Generate an ESP32 NVS partition image with Freematics device settings.

    Returns the raw binary bytes of the NVS partition, or None if the
    esp_idf_nvs_partition_gen package is not available.

    The returned bytes should be flashed to the NVS partition offset
    (NVS_PARTITION_OFFSET = 0x9000) alongside the application binary.

    Args:
        cell_server_host: Cellular-specific server hostname (CELL_HOST NVS key).
            When set (typically ``hooks.nabu.casa`` from the Nabu Casa cloud
            hook), the firmware uses this host for SIM7600/cellular connections
            instead of ``server_host``.  This allows WiFi to use a local or
            Remote-UI URL while cellular uses the publicly-reachable cloud
            webhook endpoint.
        cell_server_port: Cellular-specific port (CELL_PORT NVS key).
        cell_webhook_path: Cellular-specific webhook path (CELL_PATH NVS key).
            Contains the opaque token path returned by
            ``async_create_cloudhook()``.
        cell_debug: When True, writes CELL_DEBUG=1 to NVS so the firmware
            enables verbose cellular diagnostic logging at runtime (TX-Preview,
            hex-dump, AT+CCHSTATUS? and per-packet "Incoming data" lines).
            Off by default; safe to toggle without reflashing the firmware.
        led_red_en: When True (default), the red/power LED lights up while the
            device is powered on or in standby.  Set to False to disable the
            red LED entirely (LED_RED_EN=0 written to NVS).
        led_white_en: When True (default), the white/network LED lights up
            during each data-transmission burst over WiFi or cellular.  Set to
            False to disable the network-activity LED (LED_WHITE_EN=0 in NVS).
        beep_en: When True (default), the buzzer emits a short beep on each
            successful WiFi or cellular connection.  Set to False to suppress
            the connection beep (BEEP_EN=0 written to NVS).
        ota_token: Secret token used to construct the authenticated pull-OTA
            endpoint URL.  Stored in NVS as OTA_TOKEN.  When set, the firmware
            will periodically GET
            ``{server_host}:{server_port}/api/freematics/ota_pull/{ota_token}/meta.json``
            and download/flash a newer version if one is available.
            Empty string disables the pull-OTA feature (default).
        ota_host: Hostname of the Home Assistant server serving the pull-OTA
            endpoint (OTA_HOST NVS key).  Defaults to ``server_host`` when
            empty.  Stored separately so that cloud-webhook deployments (where
            SERVER_HOST is ``hooks.nabu.casa``) still reach the correct HA
            instance for firmware downloads.
        ota_port: TCP port for the OTA host (OTA_PORT NVS key, u16).
            Defaults to 443.
        ota_check_interval_s: How often (seconds) the firmware should check
            for a new firmware version (OTA_INTERVAL NVS key, u16).
            0 = disabled (default).
        nvs_version: Settings version string written to the NVS_VER key.
            Read by the firmware at boot and printed to the serial console so
            the user can verify which settings revision was flashed.  Format:
            "<firmware_version>.<settings_timestamp>", e.g.
            "5.1.2026-03-16T16:11:20+00:00".  Empty string = key not written
            (legacy NVS partitions without this key are silently unaffected).
        obd_en: When True (default), OBD-II PID polling is enabled.  Set to
            False to disable OBD queries (OBD_EN=0 written to NVS), e.g. when
            no OBD-II vehicle is connected or to reduce ECU bus load.
        can_en: When True, CAN bus sniffing is enabled (CAN_EN=1 in NVS).
            Defaults to False; reserved for future CAN bus firmware support.
        standby_time_s: Standby-time override in seconds (5-900).
            Replaces the maximum standby threshold in the firmware's
            STATIONARY_TIME_TABLE so the device enters standby sooner.
            0 = use firmware compile-time default (currently 180 s).
            Written to NVS key STANDBY_TIME (u16) only when non-zero.
        deep_standby: When True, the firmware uses ESP32 deep sleep during
            standby (DEEP_STANDBY=1 written to NVS).  Deep sleep cuts power
            consumption further; the device restarts fully on wake-up.
    """
    try:
        from esp_idf_nvs_partition_gen import nvs_partition_gen  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning(
            "esp_idf_nvs_partition_gen not installed; cannot generate NVS partition. "
            "Install with: pip install esp-idf-nvs-partition-gen"
        )
        return None

    # Build the CSV content. Every field is a string entry under namespace "storage".
    # Only include non-empty values to keep the partition minimal.
    rows = ["key,type,encoding,value", "storage,namespace,,"]

    def _add_str(key: str, value: str) -> None:
        # Escape commas and newlines in values (unlikely but defensive)
        safe = value.replace('"', '""')
        rows.append(f'{key},data,string,"{safe}"')

    def _add_u16(key: str, value: int) -> None:
        rows.append(f"{key},data,u16,{value}")

    def _add_u8(key: str, value: int) -> None:
        rows.append(f"{key},data,u8,{value}")

    if wifi_ssid:
        _add_str("WIFI_SSID", wifi_ssid)
    if wifi_password:
        _add_str("WIFI_PWD", wifi_password)
    # Always write APN (empty string means auto-detect)
    _add_str("CELL_APN", cell_apn)
    # Write SIM PIN only when provided.  An absent NVS key causes the firmware to
    # fall back to the compile-time SIM_CARD_PIN constant (default: empty string).
    if sim_pin:
        _add_str("SIM_PIN", sim_pin)
    if server_host:
        _add_str("SERVER_HOST", server_host)
    if server_port and server_host:
        _add_u16("SERVER_PORT", server_port)
    if webhook_path:
        _add_str("WEBHOOK_PATH", webhook_path)
    # Cellular-specific server overrides (firmware v5.1+).
    # CELL_HOST / CELL_PATH / CELL_PORT are used by the firmware when a
    # cellular (SIM7600) connection is active, in preference to SERVER_HOST /
    # WEBHOOK_PATH / SERVER_PORT.  This allows WiFi to use a local or Remote-UI
    # URL while cellular uses hooks.nabu.casa (the Nabu Casa cloud webhook
    # endpoint that SIM7600 devices can reach reliably).
    if cell_server_host:
        _add_str("CELL_HOST", cell_server_host)
        _add_u16("CELL_PORT", cell_server_port)
    if cell_webhook_path:
        _add_str("CELL_PATH", cell_webhook_path)
    # Enable the built-in HTTP server (requires ENABLE_HTTPD=1 compiled into firmware).
    # Defaults to disabled to preserve RAM for the TLS webhook client.
    _add_u8("ENABLE_HTTPD", 1 if enable_httpd else 0)
    # Enable/disable BLE SPP server.  Disabling frees ~100 KB of heap, which
    # prevents MBEDTLS_ERR_SSL_ALLOC_FAILED on the HTTPS webhook connection.
    # The firmware defaults to BLE on for un-provisioned devices; this key
    # overrides that default.
    _add_u8("ENABLE_BLE", 1 if enable_ble else 0)
    # Enable verbose cellular debug logging.  0 = off (default); 1 = on.
    # When enabled the firmware prints TX-Preview, hex-dump, AT+CCHSTATUS? and
    # per-packet "Incoming data" lines to the serial console.  Only takes effect
    # when the firmware was built without -DNET_DEBUG (i.e. release builds where
    # those log lines are behind the cellNetDebug runtime flag).
    _add_u8("CELL_DEBUG", 1 if cell_debug else 0)
    # LED behaviour control.  1 = enabled (default); 0 = disabled.
    # LED_RED_EN  – red/power LED that lights up in standby/power-on state.
    # LED_WHITE_EN – white/network LED that flashes during data transmission.
    # Both default to 1 so un-provisioned devices keep the original behaviour.
    _add_u8("LED_RED_EN", 1 if led_red_en else 0)
    _add_u8("LED_WHITE_EN", 1 if led_white_en else 0)
    # Beep/buzzer on connection.  1 = enabled (default); 0 = silent.
    # When disabled the buzzer is suppressed on WiFi and cellular connect events.
    _add_u8("BEEP_EN", 1 if beep_en else 0)
    # Optional data-interval override (ms).  0 = firmware compile-time default.
    if data_interval_ms and data_interval_ms >= 500:
        _add_u16("DATA_INTERVAL", data_interval_ms)
    # Optional server-sync-interval override (s).  0 = firmware compile-time default.
    if sync_interval_s and sync_interval_s > 0:
        _add_u16("SYNC_INTERVAL", sync_interval_s)
    # ── Pull-OTA configuration (Variant 1: authenticated endpoint, Variant 2:
    #    /local/ path).  All three keys must be present for the firmware to
    #    enable periodic pull-OTA checks.  The token acts as a path component in
    #    the HA endpoint URL so no Authorization header is required.
    #
    #    OTA_TOKEN   – secret embedded in the endpoint path; empty disables OTA pull.
    #    OTA_HOST    – HA server hostname for downloads (may differ from SERVER_HOST
    #                  when Nabu Casa cloud hook is active and SERVER_HOST is
    #                  hooks.nabu.casa which does not serve pull-OTA files).
    #    OTA_PORT    – TCP port for OTA_HOST (u16, default 443).
    #    OTA_INTERVAL – check interval in seconds (u16, 0 = disabled).
    if ota_token:
        _add_str("OTA_TOKEN", ota_token)
        _ota_host = ota_host or server_host
        if _ota_host:
            _add_str("OTA_HOST", _ota_host)
        _ota_port = ota_port if ota_port else (server_port or 443)
        _add_u16("OTA_PORT", _ota_port)
    if ota_check_interval_s and ota_check_interval_s > 0:
        _add_u16("OTA_INTERVAL", ota_check_interval_s)
    # NVS settings version (NVS_VER key, firmware v5.2+).  Stores the HA
    # effective_version string so the firmware can print it at boot, letting
    # the user verify that the current NVS was written during the last serial
    # flash or OTA NVS update.
    if nvs_version:
        _add_str("NVS_VER", nvs_version)
    # OBD-II polling control.  1 = enabled (default); 0 = disabled.
    # OBD_EN – when 0 the firmware skips OBD init and PID polling entirely.
    _add_u8("OBD_EN", 1 if obd_en else 0)
    # CAN bus control.  0 = disabled (default); 1 = enabled (future use).
    _add_u8("CAN_EN", 1 if can_en else 0)
    # Standby-time override (seconds, 5-900).  0 = use firmware default (180 s).
    if standby_time_s and standby_time_s >= 5:
        _add_u16("STANDBY_TIME", min(standby_time_s, 900))
    # Deep standby: when 1 the firmware uses ESP32 deep sleep during standby.
    _add_u8("DEEP_STANDBY", 1 if deep_standby else 0)

    csv_content = "\n".join(rows) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "nvs_config.csv")
        bin_path = os.path.join(tmpdir, "nvs_config.bin")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        args = types.SimpleNamespace(
            input=csv_path,
            output=bin_path,
            size=hex(NVS_PARTITION_SIZE),
            # Use NVS format version 2 (page-header byte 0xFE).
            # The esp_idf_nvs_partition_gen tool's version=1 writes 0xFF to the
            # page-header version field, but ESP-IDF 4.x (used by Arduino ESP32)
            # defines NVS_VERSION=0xFE and rejects any page whose version byte is
            # greater than that (0xFF > 0xFE → ESP_ERR_NVS_NEW_VERSION_FOUND).
            # This error triggers nvs_flash_erase() in the firmware, which destroys
            # provisioned WiFi credentials before loadConfig() can read them.
            # version=2 writes 0xFE, which satisfies ESP-IDF 4.x (0xFE == NVS_VERSION)
            # and is also accepted by 3.x (0xFE < 0xFF = NVS_VERSION there).
            # All our NVS values are small strings/integers so multi-page blobs
            # (the only functional difference of version=2) are never triggered.
            version=2,
            outdir=tmpdir,
        )

        try:
            # Suppress the tool's stdout prints by redirecting temporarily
            import sys  # noqa: PLC0415
            orig_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                nvs_partition_gen.generate(args)
            finally:
                sys.stdout = orig_stdout

            with open(bin_path, "rb") as f:
                data = f.read()

            _LOGGER.debug(
                "NVS partition generated: %d bytes (wifi=%s, host=%s, path=%s, "
                "cell_host=%s, cell_path=%s, httpd=%s)",
                len(data),
                bool(wifi_ssid),
                bool(server_host),
                bool(webhook_path),
                bool(cell_server_host),
                bool(cell_webhook_path),
                bool(enable_httpd),
            )
            return data

        except (RuntimeError, ValueError, OSError) as exc:
            # RuntimeError covers InputError / InsufficientSizeError / PageFullError
            # raised by nvs_partition_gen.  ValueError covers malformed input.
            # OSError covers file I/O failures in the temp directory.
            _LOGGER.error("Failed to generate NVS partition: %s", exc)
            return None


def generate_flash_image(nvs_data: bytes, firmware_path: Path, bootloader_path: Path | None = None) -> bytes | None:
    """Combine the bootloader, partition table, NVS data, and firmware into one flash image.

    The returned bytes must be flashed at BOOTLOADER_PARTITION_OFFSET (0x1000) using
    esptool – do **not** use the Freematics Builder with this file, because the
    Builder writes binaries at the app partition offset (0x10000) which would
    place partition-table data where firmware belongs and cause a restart loop.
    Use esptool instead.

    Including the second-stage bootloader is **critical**.  During a first-time
    ("new install") flash, esp-web-tools performs a chip erase that wipes the
    bootloader at 0x1000.  Without restoring it the ROM bootloader cannot hand
    off to the second-stage loader and the device loops endlessly with:
        flash read err, 1000  /  ets_main.c 371

    Including the partition table ensures the device always has the correct
    huge_app partition scheme.  Without it, a device that previously had a
    different partition table would also enter a reset loop.

    Memory layout of the returned image (all offsets relative to 0x1000):
      0x0000 – bootloader_size  Second-stage bootloader (DIO/40 MHz)
      [padding to 0x7000]       0xFF (reserved)
      0x7000 – 0x7FFF : Partition table (dual-OTA scheme, 4 KB)
      0x8000 – 0xCFFF : NVS partition   (20 KB, your WiFi/server settings)
      0xD000 – 0xEFFF : 0xFF padding    (otadata region, written as erased)
      0xF000 – end    : Application firmware (telelogger.bin, flash mode
                        patched to DIO for maximum hardware compatibility)

    When flashed at 0x1000 with
    ``python -m esptool write-flash 0x1000 flash_image.bin``
    the device boots immediately with the correct settings.

    Args:
        nvs_data:        NVS partition bytes returned by generate_nvs_partition().
        firmware_path:   Path to the pre-compiled application binary (telelogger.bin).
        bootloader_path: Path to the second-stage bootloader binary (bootloader.bin).
                         When *None* the bootloader section is filled with 0xFF bytes
                         (not recommended — the device may fail to boot if the
                         bootloader was previously erased by a chip erase).

    Returns:
        Combined bytes on success, None on failure.
    """
    try:
        firmware_data: bytes | bytearray = firmware_path.read_bytes()
    except OSError as exc:
        _LOGGER.error("Failed to read firmware binary %s: %s", firmware_path, exc)
        return None

    bootloader_data: bytes | None = None
    if bootloader_path is not None:
        try:
            bootloader_data = bootloader_path.read_bytes()
        except OSError as exc:
            _LOGGER.error(
                "Failed to read bootloader binary %s: %s", bootloader_path, exc
            )
            return None

    # Patch the firmware's flash-mode byte (offset 2 in the ESP32 image header)
    # to DIO (0x02).  esptool's --flash_mode flag only patches binaries whose
    # first byte is the ESP32 magic (0xE9); because the combined image starts
    # with bootloader / partition-table data (not 0xE9 at offset 0), esptool
    # would leave the embedded firmware in its original QIO mode.  DIO works
    # on every ESP32 flash chip and is what the Freematics ONE+ 2nd-stage
    # bootloader expects.
    #
    # When hash_appended=1 (byte offset 23 of the image header), ESP-IDF
    # appends a SHA-256 digest of the entire image as the last 32 bytes.
    # The 2nd-stage bootloader verifies this digest at boot and silently calls
    # esp_restart() if it fails – producing an endless SW_RESET boot loop.
    # We must recompute and update the digest after changing any header byte.
    _ESP32_IMAGE_MAGIC = 0xE9
    _FLASH_MODE_DIO = 0x02
    _HASH_APPENDED_OFFSET = 23  # byte offset of hash_appended field in image header
    _HASH_SIZE = 32              # SHA-256 digest length in bytes
    if len(firmware_data) > 2 and firmware_data[0] == _ESP32_IMAGE_MAGIC:
        firmware_data = bytearray(firmware_data)
        firmware_data[2] = _FLASH_MODE_DIO
        # Re-compute the appended SHA-256 if present, so the bootloader's
        # integrity check still passes after the flash-mode byte was changed.
        _min_hash_len = _HASH_APPENDED_OFFSET + 1 + _HASH_SIZE
        if (
            len(firmware_data) >= _min_hash_len
            and firmware_data[_HASH_APPENDED_OFFSET] == 1
        ):
            hash_start = len(firmware_data) - _HASH_SIZE
            new_hash = hashlib.sha256(firmware_data[:hash_start]).digest()
            firmware_data[hash_start:] = new_hash

    # Build the image starting at BOOTLOADER_PARTITION_OFFSET (0x1000):
    #   [0x0000 – 0x7000): bootloader + 0xFF padding
    #   [0x7000 – 0x8000): partition table
    #   [0x8000 – 0xD000): NVS partition
    #   [0xD000 – 0xF000): 0xFF (otadata)
    #   [0xF000 – end):    application firmware
    image = bytearray(b"\xff" * _APP_OFFSET_IN_IMAGE)
    if bootloader_data is not None:
        image[:len(bootloader_data)] = bootloader_data
    pt_data = generate_partition_table()
    image[_PT_OFFSET_IN_IMAGE : _PT_OFFSET_IN_IMAGE + PARTITION_TABLE_SIZE] = pt_data
    image[_NVS_OFFSET_IN_IMAGE : _NVS_OFFSET_IN_IMAGE + len(nvs_data)] = nvs_data
    image += firmware_data

    _LOGGER.debug(
        "Flash image generated: %d bytes (BL=%d, PT=%d, NVS=%d, firmware=%d)",
        len(image),
        len(bootloader_data) if bootloader_data else 0,
        len(pt_data),
        len(nvs_data),
        len(firmware_data),
    )
    return bytes(image)
