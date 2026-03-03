"""Flash manager for Freematics ONE+.

Handles:
- WiFi OTA: sends firmware binary to device via HTTP (requires device in AP mode
  or reachable on local network with HTTPD enabled)
- Serial: calls esptool.py subprocess to flash via USB serial port

The firmware binary bundled with this integration is located at:
  custom_components/freematics/firmware/telelogger.bin
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import shutil
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"

# OTA endpoint used by the device's built-in HTTP server (ENABLE_HTTPD=1)
OTA_UPLOAD_PATH = "/api/ota"

# Config commands supported by /api/control
CONTROL_PATH = "/api/control"


def _firmware_exists() -> bool:
    """Return True if the bundled firmware binary is present."""
    return FIRMWARE_PATH.exists()


async def async_flash_serial(
    serial_port: str,
    baud: int = 921600,
) -> tuple[bool, str]:
    """Flash firmware via USB serial using esptool.

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
            f"write_flash 0x10000 {FIRMWARE_PATH}"
        )

    cmd = [
        esptool,
        "--chip", "esp32",
        "--port", serial_port,
        "--baud", str(baud),
        "write_flash",
        "--flash_mode", "dio",
        "--flash_size", "detect",
        "0x10000",
        str(FIRMWARE_PATH),
    ]

    _LOGGER.info("Starting serial flash: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode(errors="replace")
        _LOGGER.debug("esptool output: %s", output)

        if proc.returncode == 0:
            return True, f"Flash successful.\n{output}"
        return False, f"esptool returned exit code {proc.returncode}.\n{output}"

    except asyncio.TimeoutError:
        return False, "Flash timed out after 120 seconds."
    except Exception as exc:  # noqa: BLE001
        return False, f"Flash failed: {exc}"


async def async_flash_wifi(
    device_ip: str,
    device_port: int = 80,
) -> tuple[bool, str]:
    """Upload firmware to the device via HTTP OTA.

    The device must be running a firmware with ENABLE_HTTPD=1 and an OTA
    endpoint at /api/ota that accepts a multipart firmware upload.

    Returns (success, message).
    """
    # Validate device_ip is a plain IP address (not a URL or hostname) to
    # prevent SSRF: ipaddress.ip_address rejects everything except IPv4/IPv6
    # literals, so it cannot be manipulated into a request to an unexpected host.
    # Use the normalised string from the ip_address object in the URL so the
    # taint chain is broken.
    try:
        validated_ip = str(ipaddress.ip_address(device_ip))
    except ValueError:
        return False, f"Invalid device IP address: {device_ip!r}. Must be a plain IPv4 or IPv6 address."
    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        return False, "aiohttp not available – cannot perform WiFi OTA flash."

    if not _firmware_exists():
        return False, f"Firmware binary not found at {FIRMWARE_PATH}"

    url = f"http://{validated_ip}:{device_port}{OTA_UPLOAD_PATH}"
    _LOGGER.info("WiFi OTA flash to %s", url)

    try:
        firmware_data = FIRMWARE_PATH.read_bytes()
    except OSError as exc:
        return False, f"Cannot read firmware file: {exc}"

    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                "firmware",
                firmware_data,
                filename="telelogger.bin",
                content_type="application/octet-stream",
            )
            async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                text = await resp.text()
                if resp.status == 200:
                    return True, f"OTA flash successful: {text}"
                return False, f"OTA failed, HTTP {resp.status}: {text}"

    except aiohttp.ClientConnectorError as exc:
        return False, (
            f"Cannot connect to device at {device_ip}:{device_port}.\n"
            f"Ensure the device is powered on, in AP mode (SSID: TELELOGGER), "
            f"and your computer is connected to the device's WiFi network.\n"
            f"Error: {exc}"
        )
    except asyncio.TimeoutError:
        return False, "OTA flash timed out after 120 seconds."
    except Exception as exc:  # noqa: BLE001
        return False, f"OTA flash failed: {exc}"


async def async_send_config(
    device_ip: str,
    device_port: int,
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Send configuration commands to a running device via /api/control.

    config keys: wifi_ssid, wifi_password, cell_apn
    Returns (all_ok, list_of_result_messages).
    """
    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        return False, ["aiohttp not available – cannot send config over WiFi."]

    from .const import CMD_APN, CMD_SSID, CMD_WIFI_PWD  # noqa: PLC0415

    commands: list[tuple[str, str]] = []
    if "wifi_ssid" in config:
        commands.append(("SSID", CMD_SSID.format(config["wifi_ssid"])))
    if "wifi_password" in config:
        commands.append(("WPWD", CMD_WIFI_PWD.format(config["wifi_password"])))
    if "cell_apn" in config:
        commands.append(("APN", CMD_APN.format(config["cell_apn"] or "DEFAULT")))

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
