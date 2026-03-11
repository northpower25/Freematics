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
import time
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


async def async_flash_wifi(
    device_ip: str,
    device_port: int = 80,
    queue: asyncio.Queue | None = None,
) -> tuple[bool, str, list[str]]:
    """Upload firmware to the device via HTTP OTA.

    The device must be running a firmware with ENABLE_HTTPD=1 and an OTA
    endpoint at /api/ota that accepts a raw binary POST
    (Content-Type: application/octet-stream).

    Returns (success, message, log_lines) where log_lines is a list of
    timestamped log entries suitable for display in the UI log panel.
    """
    log: list[str] = []

    def _log(level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        log.append(f"[{ts}] [{level.upper()}] {msg}")
        if level == "error":
            _LOGGER.error("WiFi OTA: %s", msg)
        else:
            _LOGGER.info("WiFi OTA: %s", msg)
        if queue is not None:
            queue.put_nowait({"type": "log", "level": level, "message": msg, "ts": ts})

    # Validate device_ip is a plain IP address (not a URL or hostname) to
    # prevent SSRF: ipaddress.ip_address rejects everything except IPv4/IPv6
    # literals, so it cannot be manipulated into a request to an unexpected host.
    # Use the normalised string from the ip_address object in the URL so the
    # taint chain is broken.
    try:
        validated_ip = str(ipaddress.ip_address(device_ip))
    except ValueError:
        msg = f"Invalid device IP address: {device_ip!r}. Must be a plain IPv4 or IPv6 address."
        _log("error", msg)
        return False, msg, log
    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        msg = "aiohttp not available – cannot perform WiFi OTA flash."
        _log("error", msg)
        return False, msg, log

    if not _firmware_exists():
        msg = f"Firmware binary not found at {FIRMWARE_PATH}"
        _log("error", msg)
        return False, msg, log

    url = f"http://{validated_ip}:{device_port}{OTA_UPLOAD_PATH}"
    _log("info", f"Target URL: {url}")

    try:
        firmware_data = FIRMWARE_PATH.read_bytes()
    except OSError as exc:
        msg = f"Cannot read firmware file: {exc}"
        _log("error", msg)
        return False, msg, log

    firmware_kb = len(firmware_data) / 1024
    _log("info", f"Firmware size: {firmware_kb:.1f} KB ({len(firmware_data)} bytes)")
    _log("info", "Connecting to device…")

    t_start = time.monotonic()
    try:
        async with aiohttp.ClientSession() as session:
            # Send the firmware as a raw binary body (Content-Type:
            # application/octet-stream).  The device-side OTA handler reads
            # the Content-Length header to know the total size, writes the
            # first chunk from the httpd buffer, then streams the rest directly
            # from the socket – no multipart parsing needed.
            _log("info", "Uploading firmware (raw binary POST)…")
            async with session.post(
                url,
                data=firmware_data,
                headers={"Content-Type": "application/octet-stream"},
                # No hard total timeout so slow WiFi connections don't time out
                # mid-upload; rely on a per-read timeout instead so a stalled
                # server is still detected.
                timeout=aiohttp.ClientTimeout(total=None, sock_read=600),
            ) as resp:
                # By the time this block is entered, the device has received
                # all firmware bytes, verified the byte count, validated the
                # image (MD5) and committed the OTA partition.  The response
                # headers are now available; we still need to read the body
                # to get the device's final confirmation ("OK" or an error).
                upload_elapsed = time.monotonic() - t_start
                _log(
                    "info",
                    f"Firmware upload complete ({upload_elapsed:.1f} s) —"
                    f" reading device flash confirmation…",
                )
                try:
                    text = await resp.text()
                except aiohttp.ClientPayloadError:
                    # The device reboots immediately after a successful OTA flash,
                    # which closes the TCP connection before the HTTP response body
                    # is fully sent.  Treat an incomplete response as success when
                    # the status was 200.
                    elapsed = time.monotonic() - t_start
                    if resp.status == 200:
                        _log("info", f"HTTP {resp.status} — upload completed in {elapsed:.1f} s")
                        _log("ok", "Device rebooted after flashing (response truncated — expected).")
                        msg = f"OTA flash successful ({elapsed:.1f} s): device rebooted."
                        return True, msg, log
                    _log("error", f"HTTP {resp.status} after {elapsed:.1f} s — response payload incomplete")
                    msg = f"OTA failed, HTTP {resp.status}: response payload incomplete"
                    return False, msg, log
                elapsed = time.monotonic() - t_start
                if resp.status == 200:
                    body = text.strip()
                    # The device-side handler writes "OK" on success or a message
                    # starting with "ERR:" on failure.  Both return HTTP 200 so we
                    # must inspect the body to know whether the flash succeeded.
                    if body.startswith("ERR:"):
                        _log("error", f"OTA handler error after {elapsed:.1f} s: {body}")
                        msg = f"OTA failed: {body}"
                        return False, msg, log
                    _log("info", f"HTTP {resp.status} — upload completed in {elapsed:.1f} s")
                    _log("ok", f"Device response: {body}")
                    msg = f"OTA flash successful ({elapsed:.1f} s): {body}"
                    return True, msg, log
                _log("error", f"HTTP {resp.status} after {elapsed:.1f} s — device response: {text.strip()}")
                msg = f"OTA failed, HTTP {resp.status}: {text.strip()}"
                return False, msg, log

    except aiohttp.ClientConnectorError as exc:
        elapsed = time.monotonic() - t_start
        detail = (
            f"Cannot connect to device at {device_ip}:{device_port} "
            f"after {elapsed:.1f} s.\n"
            f"Ensure the device is powered on, connected to the local network, "
            f"reachable from the Home Assistant server, and that the firmware "
            f"was compiled with ENABLE_HTTPD=1 (check that config_nvs.bin was "
            f"flashed so ENABLE_HTTPD is set in NVS).\n"
            f"Error: {exc}"
        )
        _log("error", f"Connection error after {elapsed:.1f} s: {exc}")
        return False, detail, log
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t_start
        msg = f"OTA flash timed out after {elapsed:.1f} s."
        _log("error", msg)
        return False, msg, log
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t_start
        msg = f"OTA flash failed after {elapsed:.1f} s: {exc}"
        _log("error", msg)
        return False, msg, log


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
