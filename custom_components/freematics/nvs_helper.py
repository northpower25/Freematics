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
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import types

_LOGGER = logging.getLogger(__name__)

# Standard ESP32 NVS partition size used by the huge_app partition scheme.
NVS_PARTITION_SIZE = 0x5000  # 20 480 bytes

# Flash offset of the NVS partition in the huge_app scheme.
NVS_PARTITION_OFFSET = 0x9000


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
