"""Flash manager for Freematics ONE+.

Handles:
- Serial: calls esptool.py subprocess to flash via USB serial port

The firmware binary bundled with this integration is located at:
  custom_components/freematics/firmware/telelogger.bin
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .nvs_helper import generate_partition_table

_LOGGER = logging.getLogger(__name__)

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"

# Config commands supported by /api/control
CONTROL_PATH = "/api/control"

# Partition table flash offset (ESP32 always reads the partition table here)
_PARTITION_TABLE_OFFSET = "0x8000"

# NVS partition flash offset (must match the partition table used by the firmware)
_NVS_PARTITION_OFFSET = "0x9000"


def _firmware_exists() -> bool:
    """Return True if the bundled firmware binary is present."""
    return FIRMWARE_PATH.exists()


async def async_flash_serial(
    serial_port: str,
    baud: int = 921600,
    nvs_data: bytes | None = None,
) -> tuple[bool, str]:
    """Flash firmware (and optionally an NVS partition) via USB serial using esptool.

    Args:
        serial_port: Serial port path (e.g. '/dev/ttyUSB0' or 'COM4').
        baud: Baud rate for flashing (default 921600).
        nvs_data: If provided, the raw NVS partition binary (20 KB) is written
            to the NVS partition offset (0x9000) alongside the firmware.  This
            ensures LED/beep/server settings from the HA config entry are
            applied after every serial flash, not just when a combined
            flash_image.bin is used.

    Returns (success, message).
    Requires esptool to be installed and the serial port to be accessible.
    """
    if not _firmware_exists():
        return False, f"Firmware binary not found at {FIRMWARE_PATH}"

    esptool = shutil.which("esptool.py") or shutil.which("esptool")
    if not esptool:
        return False, (
            "esptool not found. Install it with: pip install esptool\n"
            f"Then flash manually:\n"
            f"  esptool.py --chip esp32 --port {serial_port} --baud {baud} "
            f"write_flash "
            f"{_PARTITION_TABLE_OFFSET} <partitions.bin> "
            f"{_NVS_PARTITION_OFFSET} <nvs.bin> "
            f"0x10000 {FIRMWARE_PATH}"
        )

    # Build the write_flash argument list.
    # Always write the partition table binary at 0x8000 so that a previous
    # huge_app.csv (single-OTA) layout is replaced with the dual-OTA layout
    # required for WiFi OTA updates to work.  Without this, the device
    # continues to boot with only one OTA partition (ota_0) and any OTA
    # attempt crashes with abort() because esp_ota_begin() rejects writing
    # to the currently running partition.
    #
    # Write order: partitions → nvs → firmware (low → high address)
    flash_args = [
        "--flash_mode", "dio",
        "--flash_size", "detect",
    ]

    # Generate the dual-OTA partition table binary and write to a temp file.
    # Using generate_partition_table() (the same function used by the browser
    # flasher and esp-web-tools manifest) ensures all flash paths write an
    # identical, MD5-validated partition table.
    pt_data = generate_partition_table()
    pt_tmp: Any = None
    nvs_tmp: Any = None  # Will be a NamedTemporaryFile when NVS data is given
    try:
        pt_tmp = tempfile.NamedTemporaryFile(
            suffix=".bin", delete=False, prefix="freematics_pt_"
        )
        pt_tmp.write(pt_data)
        pt_tmp.flush()
        pt_tmp.close()
        flash_args += [_PARTITION_TABLE_OFFSET, pt_tmp.name]

        if nvs_data:
            # Write NVS to a temp file; esptool needs a path on disk.
            nvs_tmp = tempfile.NamedTemporaryFile(
                suffix=".bin", delete=False, prefix="freematics_nvs_"
            )
            nvs_tmp.write(nvs_data)
            nvs_tmp.flush()
            nvs_tmp.close()
            flash_args += [_NVS_PARTITION_OFFSET, nvs_tmp.name]

        flash_args += ["0x10000", str(FIRMWARE_PATH)]

        cmd = [
            esptool,
            "--chip", "esp32",
            "--port", serial_port,
            "--baud", str(baud),
            "write_flash",
            *flash_args,
        ]

        _LOGGER.info("Starting serial flash: %s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            output = stdout.decode(errors="replace")
            _LOGGER.debug("esptool output: %s", output)

            if proc.returncode == 0:
                return True, f"Flash successful.\n{output}"
            return False, f"esptool returned exit code {proc.returncode}.\n{output}"

        except asyncio.TimeoutError:
            return False, "Flash timed out after 180 seconds."
        except Exception as exc:  # noqa: BLE001
            return False, f"Flash failed: {exc}"
    finally:
        # Clean up the temporary partition table and NVS files.
        for tmp in (pt_tmp, nvs_tmp):
            if tmp is not None:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass


async def async_send_config(
    device_ip: str,
    device_port: int,
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Send configuration commands to a running device via /api/control.

    config keys: wifi_ssid, wifi_password, cell_apn,
                 ota_token, ota_host, ota_interval,
                 led_white, led_red, beep.
    Returns (all_ok, list_of_result_messages).
    """
    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        return False, ["aiohttp not available – cannot send config over WiFi."]

    from .const import (  # noqa: PLC0415
        CMD_APN,
        CMD_BEEP,
        CMD_LED_RED,
        CMD_LED_WHITE,
        CMD_OTA_HOST,
        CMD_OTA_INTERVAL,
        CMD_OTA_TOKEN,
        CMD_SSID,
        CMD_WIFI_PWD,
    )

    commands: list[tuple[str, str]] = []
    if "wifi_ssid" in config:
        # Use "-" to clear the SSID when the value is empty; the firmware maps
        # "-" to an empty NVS string (device will not attempt WiFi connection).
        commands.append(("SSID", CMD_SSID.format(config["wifi_ssid"] or "-")))
    if "wifi_password" in config:
        commands.append(("WPWD", CMD_WIFI_PWD.format(config["wifi_password"] or "-")))
    if "cell_apn" in config:
        commands.append(("APN", CMD_APN.format(config["cell_apn"] or "DEFAULT")))
    if "ota_token" in config:
        commands.append(("OTA_TOKEN", CMD_OTA_TOKEN.format(config["ota_token"] or "-")))
    if "ota_host" in config:
        commands.append(("OTA_HOST", CMD_OTA_HOST.format(config["ota_host"] or "-")))
    if "ota_interval" in config:
        commands.append(("OTA_INTERVAL", CMD_OTA_INTERVAL.format(int(config["ota_interval"]))))
    if "led_white" in config:
        commands.append(("LED_WHITE", CMD_LED_WHITE.format(1 if config["led_white"] else 0)))
    if "led_red" in config:
        commands.append(("LED_RED", CMD_LED_RED.format(1 if config["led_red"] else 0)))
    if "beep" in config:
        commands.append(("BEEP", CMD_BEEP.format(1 if config["beep"] else 0)))

    if not commands:
        return True, ["No config commands to send."]

    base_url = f"http://{device_ip}:{device_port}{CONTROL_PATH}"
    results: list[str] = []
    all_ok = True

    try:
        async with aiohttp.ClientSession() as session:
            for label, cmd in commands:
                url = f"{base_url}?cmd={cmd}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        text = await resp.text()
                        ok = resp.status == 200
                        results.append(f"{label}: {'OK' if ok else 'FAILED'} ({text})")
                        if not ok:
                            all_ok = False
                except Exception as exc:  # noqa: BLE001
                    results.append(f"{label}: ERROR ({exc})")
                    all_ok = False
    except Exception as exc:  # noqa: BLE001
        return False, [f"Session error: {exc}"]

    return all_ok, results


async def async_send_restart(
    device_ip: str,
    device_port: int,
) -> tuple[bool, str]:
    """Send a RESET command to a running device via /api/control.

    The device closes the connection immediately after receiving RESET, so a
    connection error or short timeout is expected and treated as success.
    Returns (success, message).
    """
    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        return False, "aiohttp not available – cannot restart device over WiFi."

    url = f"http://{device_ip}:{device_port}{CONTROL_PATH}?cmd=RESET"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return True, f"RESET sent, HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001
        # Device resets immediately after receiving RESET – a connection error
        # or EOF at this point is expected and should be treated as success.
        return True, f"RESET sent (device restarted: {exc})"
