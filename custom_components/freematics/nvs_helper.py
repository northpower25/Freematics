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
  SERVER_HOST   – HA hostname / Nabu Casa *.ui.nabu.casa (firmware v5.1+)
  SERVER_PORT   – HTTPS port, usually 443 (firmware v5.1+)
  WEBHOOK_PATH  – Full path: /api/webhook/<webhook_id> (firmware v5.1+)
  ENABLE_HTTPD  – 1 = start built-in HTTP server on boot (firmware with ENABLE_HTTPD=1)
  ENABLE_BLE    – 0 = disable BLE SPP server (frees ~100 KB heap for TLS webhook)
  DATA_INTERVAL – Telemetry post interval in ms (≥500; 0 = firmware default ≈1000 ms)
  SYNC_INTERVAL – Server-sync check interval in seconds (0 = firmware default 120 s)

Single-file flash image (esptool)
----------------------------------
generate_flash_image() combines the partition table, NVS partition, and the
application firmware into one binary written at PARTITION_TABLE_OFFSET (0x8000).
Starting at 0x8000 ensures the correct huge_app partition table is always
programmed, which is required for the firmware to locate the NVS and app
partitions correctly and prevents a reset loop on devices that previously
had a different partition scheme.

  **Important**: Do NOT use the Freematics Builder with this combined image.
  The Builder writes binaries at the app partition offset (0x10000), which
  places partition-table data where firmware belongs and causes a restart loop.
  For the Freematics Builder, use telelogger.bin (firmware only) and provision
  NVS settings separately via the browser-based flasher.

  Layout (relative to PARTITION_TABLE_OFFSET = 0x8000):
    0x0000 – 0x0FFF  Partition table  (huge_app scheme, 4 KB)
    0x1000 – 0x5FFF  NVS partition    (config_nvs.bin, 20 KB)
    0x6000 – 0x7FFF  0xFF padding     (otadata region – preserved as erased)
    0x8000 –  end    Application firmware (telelogger.bin, flash mode = DIO)

  esptool usage:
    python -m esptool write-flash 0x8000 flash_image.bin
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

# Byte offsets within the combined flash image (relative to PARTITION_TABLE_OFFSET).
_NVS_OFFSET_IN_IMAGE = NVS_PARTITION_OFFSET - PARTITION_TABLE_OFFSET   # 0x1000
_APP_OFFSET_IN_IMAGE = APP_PARTITION_OFFSET - PARTITION_TABLE_OFFSET    # 0x8000

# ---------------------------------------------------------------------------
# Partition-table generation
# ---------------------------------------------------------------------------
# Each partition entry is 32 bytes:
#   2 B magic (0xAA 0x50) | 1 B type | 1 B subtype | 4 B offset | 4 B size
#   | 16 B label (null-padded) | 4 B flags
_PT_MAGIC = b"\xaa\x50"
_PT_MD5_MAGIC = b"\xeb\xeb"
_PT_ENTRY_SIZE = 32

# huge_app partition layout (matches arduino-esp32 hardware/espressif/esp32/
# tools/partitions/huge_app.csv):
#   nvs      data/nvs      0x9000   0x5000
#   otadata  data/ota      0xE000   0x2000
#   app0     app/ota_0     0x10000  0x300000
_HUGE_APP_PARTITIONS = [
    # (name, type, subtype, offset, size)
    ("nvs",     0x01, 0x02, 0x9000,  0x5000),
    ("otadata", 0x01, 0x00, 0xE000,  0x2000),
    ("app0",    0x00, 0x10, 0x10000, 0x300000),
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
    """Return a 4 096-byte ESP32 partition-table binary for the huge_app scheme.

    The table contains an MD5 checksum entry (compatible with ESP-IDF v4.x+)
    and is padded to PARTITION_TABLE_SIZE with 0xFF bytes.
    """
    entries = b"".join(
        _make_partition_entry(*p) for p in _HUGE_APP_PARTITIONS
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
) -> bytes | None:
    """Generate an ESP32 NVS partition image with Freematics device settings.

    Returns the raw binary bytes of the NVS partition, or None if the
    esp_idf_nvs_partition_gen package is not available.

    The returned bytes should be flashed to the NVS partition offset
    (NVS_PARTITION_OFFSET = 0x9000) alongside the application binary.
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
    # Enable the built-in HTTP server (requires ENABLE_HTTPD=1 compiled into firmware).
    # Defaults to disabled to preserve RAM for the TLS webhook client.
    _add_u8("ENABLE_HTTPD", 1 if enable_httpd else 0)
    # Enable/disable BLE SPP server.  Disabling frees ~100 KB of heap, which
    # prevents MBEDTLS_ERR_SSL_ALLOC_FAILED on the HTTPS webhook connection.
    # The firmware defaults to BLE on for un-provisioned devices; this key
    # overrides that default.
    _add_u8("ENABLE_BLE", 1 if enable_ble else 0)
    # Optional data-interval override (ms).  0 = firmware compile-time default.
    if data_interval_ms and data_interval_ms >= 500:
        _add_u16("DATA_INTERVAL", data_interval_ms)
    # Optional server-sync-interval override (s).  0 = firmware compile-time default.
    if sync_interval_s and sync_interval_s > 0:
        _add_u16("SYNC_INTERVAL", sync_interval_s)

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
                "NVS partition generated: %d bytes (wifi=%s, host=%s, path=%s, httpd=%s)",
                len(data),
                bool(wifi_ssid),
                bool(server_host),
                bool(webhook_path),
                bool(enable_httpd),
            )
            return data

        except (RuntimeError, ValueError, OSError) as exc:
            # RuntimeError covers InputError / InsufficientSizeError / PageFullError
            # raised by nvs_partition_gen.  ValueError covers malformed input.
            # OSError covers file I/O failures in the temp directory.
            _LOGGER.error("Failed to generate NVS partition: %s", exc)
            return None


def generate_flash_image(nvs_data: bytes, firmware_path: Path) -> bytes | None:
    """Combine partition table, NVS data, and firmware into one flash image.

    The returned bytes must be flashed at PARTITION_TABLE_OFFSET (0x8000) using
    esptool – do **not** use the Freematics Builder with this file, because the
    Builder writes binaries at the app partition offset (0x10000) which would
    place partition-table data where firmware belongs and cause a restart loop.
    Use esptool instead.

    Including the partition table ensures the device always has the correct
    huge_app partition scheme, which is required for the firmware to locate the
    NVS and app partitions.  Without it, a device that previously had a different
    partition table would enter a reset loop.

    Memory layout of the returned image (all offsets relative to 0x8000):
      0x0000 – 0x0FFF : Partition table (huge_app scheme, 4 KB)
      0x1000 – 0x5FFF : NVS partition   (20 KB, your WiFi/server settings)
      0x6000 – 0x7FFF : 0xFF padding    (otadata region, written as erased)
      0x8000 – end    : Application firmware (telelogger.bin, flash mode
                        patched to DIO for maximum hardware compatibility)

    When flashed at 0x8000 with
    ``python -m esptool write-flash 0x8000 flash_image.bin``
    the device boots immediately with the correct settings.  The bootloader at
    0x1000 that is already on the device is not touched.

    Args:
        nvs_data:      NVS partition bytes returned by generate_nvs_partition().
        firmware_path: Path to the pre-compiled application binary (telelogger.bin).

    Returns:
        Combined bytes on success, None on failure.
    """
    try:
        firmware_data: bytes | bytearray = firmware_path.read_bytes()
    except OSError as exc:
        _LOGGER.error("Failed to read firmware binary %s: %s", firmware_path, exc)
        return None

    # Patch the firmware's flash-mode byte (offset 2 in the ESP32 image header)
    # to DIO (0x02).  esptool's --flash_mode flag only patches binaries whose
    # first byte is the ESP32 magic (0xE9); because the combined image starts
    # with partition-table data (not 0xE9), esptool would leave the embedded
    # firmware in its original QIO mode.  DIO works on every ESP32 flash chip
    # and is what the Freematics ONE+ 2nd-stage bootloader expects.
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

    # Build the image: partition table, NVS bytes, 0xFF gap, then firmware.
    image = bytearray(b"\xff" * _APP_OFFSET_IN_IMAGE)
    pt_data = generate_partition_table()
    image[:PARTITION_TABLE_SIZE] = pt_data
    image[_NVS_OFFSET_IN_IMAGE : _NVS_OFFSET_IN_IMAGE + len(nvs_data)] = nvs_data
    image += firmware_data

    _LOGGER.debug(
        "Flash image generated: %d bytes (PT=%d, NVS=%d, firmware=%d)",
        len(image),
        len(pt_data),
        len(nvs_data),
        len(firmware_data),
    )
    return bytes(image)
