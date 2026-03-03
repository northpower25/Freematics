"""NVS (Non-Volatile Storage) partition generator for Freematics ONE+.

Generates an ESP32 NVS binary partition image that is flashed alongside
the firmware so the device boots with the user's WiFi / server settings
already applied – no manual configuration required after flashing.

The generated image is compatible with the NVS partition at offset 0x9000
used by the 'huge_app' partition scheme (board_build.partitions = huge_app.csv).

Stored NVS keys (namespace "storage"):
  WIFI_SSID    – WiFi SSID
  WIFI_PWD     – WiFi password
  CELL_APN     – Cellular APN (empty string = auto)
  SERVER_HOST  – HA hostname / Nabu Casa *.ui.nabu.casa (firmware v5.1+)
  SERVER_PORT  – HTTPS port, usually 443 (firmware v5.1+)
  WEBHOOK_PATH – Full path: /api/webhook/<webhook_id> (firmware v5.1+)
  ENABLE_HTTPD – 1 = start built-in HTTP server on boot (firmware with ENABLE_HTTPD=1)

Single-file flash image (esptool / browser flasher)
----------------------------------------------------
generate_flash_image() combines the NVS partition with the application firmware
into one binary that must be written at NVS_PARTITION_OFFSET (0x9000) using
an explicit offset with esptool or via the browser-based flasher.

  **Important**: Do NOT use the Freematics Builder with this combined image.
  The Builder writes binaries at the app partition offset (0x10000), which
  places NVS data at the wrong address and causes a restart loop.
  For the Freematics Builder, use telelogger.bin (firmware only) and provision
  NVS settings separately via the browser-based flasher.

  Layout (relative to NVS_PARTITION_OFFSET = 0x9000):
    0x0000 – 0x4FFF  NVS partition (config_nvs.bin, 20 KB)
    0x5000 – 0x6FFF  0xFF padding  (otadata region – preserved as erased)
    0x7000 –  end    Application firmware (telelogger.bin, flash mode = DIO)

  esptool usage:
    esptool.py write_flash 0x9000 flash_image.bin
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import types
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Standard ESP32 NVS partition size used by the huge_app partition scheme.
NVS_PARTITION_SIZE = 0x5000  # 20 480 bytes

# Flash offset of the NVS partition in the huge_app scheme.
NVS_PARTITION_OFFSET = 0x9000

# Flash offset of the application partition (same across all common ESP32 schemes).
APP_PARTITION_OFFSET = 0x10000

# Byte offset of the application within the combined flash image
# (APP_PARTITION_OFFSET - NVS_PARTITION_OFFSET = 0x7000).
_APP_OFFSET_IN_IMAGE = APP_PARTITION_OFFSET - NVS_PARTITION_OFFSET


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
    enable_httpd: bool = True,
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
    if server_host:
        _add_str("SERVER_HOST", server_host)
    if server_port and server_host:
        _add_u16("SERVER_PORT", server_port)
    if webhook_path:
        _add_str("WEBHOOK_PATH", webhook_path)
    # Enable the built-in HTTP server on first boot (requires ENABLE_HTTPD=1
    # compiled into the firmware).
    _add_u8("ENABLE_HTTPD", 1 if enable_httpd else 0)

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
            # Use NVS format version 1 (page-header byte 0xFF = single-page blobs).
            # Version 1 is supported by every ESP-IDF/Arduino release and prevents
            # ESP_ERR_NVS_NEW_VERSION_FOUND on devices running older firmware.
            # Our NVS values are all small (<128 B) so multi-page blobs (v2) are
            # not needed.
            version=1,
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
    """Combine NVS partition data with the application firmware into one binary.

    The returned bytes must be flashed at NVS_PARTITION_OFFSET (0x9000) using
    esptool with an explicit offset – do **not** use the Freematics Builder with
    this file, because the Builder writes binaries at the app partition offset
    (0x10000) which would place NVS data at the wrong address and cause a
    restart loop.  Use esptool or the browser-based flasher instead.

    Memory layout of the returned image (all offsets relative to 0x9000):
      0x0000 – 0x4FFF : NVS partition  (20 KB, your WiFi/server settings)
      0x5000 – 0x6FFF : 0xFF padding   (otadata region, written as erased)
      0x7000 – end    : Application firmware (telelogger.bin, flash mode
                        patched to DIO for maximum hardware compatibility)

    When flashed at 0x9000 with ``esptool.py write_flash 0x9000 flash_image.bin``
    the device boots immediately with the correct settings.  The bootloader and
    partition table that are already on the device are not touched.

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
    # with NVS data (not 0xE9), esptool would leave the embedded firmware in
    # its original QIO mode.  DIO works on every ESP32 flash chip and is what
    # the Freematics ONE+ 2nd-stage bootloader expects, so we patch here.
    _ESP32_IMAGE_MAGIC = 0xE9
    _FLASH_MODE_DIO = 0x02
    if len(firmware_data) > 2 and firmware_data[0] == _ESP32_IMAGE_MAGIC:
        firmware_data = bytearray(firmware_data)
        firmware_data[2] = _FLASH_MODE_DIO

    # Build the image: NVS bytes, then 0xFF gap up to APP_PARTITION_OFFSET,
    # then firmware bytes.
    image = bytearray(b"\xff" * _APP_OFFSET_IN_IMAGE)
    image[: len(nvs_data)] = nvs_data
    image += firmware_data

    _LOGGER.debug(
        "Flash image generated: %d bytes (NVS=%d, firmware=%d)",
        len(image),
        len(nvs_data),
        len(firmware_data),
    )
    return bytes(image)
