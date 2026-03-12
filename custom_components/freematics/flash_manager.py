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
import tempfile
import time
from pathlib import Path
from typing import Any

from .nvs_helper import generate_partition_table

_LOGGER = logging.getLogger(__name__)

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"

# OTA endpoint used by the device's built-in HTTP server (ENABLE_HTTPD=1)
OTA_UPLOAD_PATH = "/api/ota"

# Config commands supported by /api/control
CONTROL_PATH = "/api/control"

# How long (seconds) to wait after a successful cmd=OFF before starting the
# OTA upload.  Gives the telemetry task time to close its SSL connections and
# release heap memory so the OTA has plenty of room to run.
_STANDBY_SETTLE_S = 4

# Report upload progress this often (seconds).
_PROGRESS_INTERVAL_S = 20

# After a successful OTA the device reboots.  Poll the device until it comes
# back online so LED/beep settings can be re-applied via /api/control.  This
# "belt-and-suspenders" re-application ensures the NVS settings are present
# even if the pre-OTA write was lost (e.g. because nvs_flash_init() erased the
# NVS partition on first boot after a firmware version change).
_POST_OTA_WAIT_S = 45   # max seconds to wait for device to come back online
_POST_OTA_POLL_S = 3    # poll interval in seconds

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


async def async_flash_wifi(
    device_ip: str,
    device_port: int = 80,
    queue: asyncio.Queue | None = None,
    led_red_en: bool | None = None,
    led_white_en: bool | None = None,
    beep_en: bool | None = None,
) -> tuple[bool, str, list[str]]:
    """Upload firmware to the device via HTTP OTA.

    The device must be running a firmware with ENABLE_HTTPD=1 and an OTA
    endpoint at /api/ota that accepts a raw binary POST
    (Content-Type: application/octet-stream).

    WiFi OTA preserves the NVS partition (unlike serial flash), so callers
    should only pass led_red_en=False (or led_white_en/beep_en=False) when
    the user has *explicitly disabled* the setting in the HA config.  Passing
    True would overwrite a user's manually-disabled NVS key (e.g.
    LED_RED_EN=0 set via /api/control) with the HA default.  When a parameter
    is None no /api/control command is sent and the existing NVS value is
    preserved intact across the OTA reboot.

    Args:
        led_red_en: When False, sends LED_RED=0 via /api/control before the
            OTA so the red LED stays off after the firmware reboot.  Pass
            None (default) to leave the existing NVS value untouched.
        led_white_en: Same as led_red_en but for the white/network LED.
        beep_en: Same as led_red_en but for the connection beep.

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

    # -----------------------------------------------------------------------
    # Pre-OTA step: ask the device to pause telemetry (cmd=OFF) and apply
    # any LED/beep settings so they are persisted in NVS before the firmware
    # is flashed.  Both are done via /api/control.
    #
    # Sequence:
    #   1. cmd=OFF  – pause telemetry / close SSL connections (frees heap)
    #   2. LED_RED=, LED_WHITE=, BEEP=  – write settings to NVS while device
    #      is paused; they survive the OTA reboot
    #
    # Firmware built without the cmd=OFF handler returns "ERR" or times out;
    # the upload proceeds anyway (but may fail on very old firmware).
    # -----------------------------------------------------------------------
    _log("info", "Connecting to device…")
    off_url = f"http://{validated_ip}:{device_port}{CONTROL_PATH}?cmd=OFF"
    try:
        async with aiohttp.ClientSession() as pre_session:
            async with pre_session.get(
                off_url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                body = (await r.text()).strip()
                if r.status == 200 and body == "OK":
                    _log(
                        "info",
                        f"Device telemetry paused (cmd=OFF → HTTP {r.status} OK). "
                        f"Waiting {_STANDBY_SETTLE_S} s for SSL connections to close…",
                    )
                    await asyncio.sleep(_STANDBY_SETTLE_S)
                else:
                    _log(
                        "info",
                        f"Device did not acknowledge pause command "
                        f"(HTTP {r.status}: {body!r}). "
                        "This is normal for firmware without the HTTP standby handler. "
                        "Proceeding — if the upload fails with a connection reset, "
                        "flash the latest firmware via serial first.",
                    )
    except Exception as exc:  # noqa: BLE001
        _log(
            "info",
            f"Could not reach device control endpoint before OTA ({exc}). "
            "Proceeding with upload anyway.",
        )

    # Apply LED/beep settings via /api/control while the device is paused
    # (or at least reachable).  These commands write the NVS keys (LED_RED_EN,
    # LED_WHITE_EN, BEEP_EN) so the values persist after the firmware reboot.
    # Firmware built without these cmd= handlers returns "ERR" which is silently
    # ignored – the settings will be applied next time the NVS is provisioned.
    # Each tuple is (human-readable NVS key name for logging, /api/control cmd= value).
    _setting_cmds: list[tuple[str, str]] = []
    if led_red_en is not None:
        _setting_cmds.append(("LED_RED_EN", f"LED_RED={1 if led_red_en else 0}"))
    if led_white_en is not None:
        _setting_cmds.append(("LED_WHITE_EN", f"LED_WHITE={1 if led_white_en else 0}"))
    if beep_en is not None:
        _setting_cmds.append(("BEEP_EN", f"BEEP={1 if beep_en else 0}"))
    if _setting_cmds:
        try:
            async with aiohttp.ClientSession() as cfg_session:
                for nvs_key, cmd_str in _setting_cmds:
                    cmd_url = (
                        f"http://{validated_ip}:{device_port}"
                        f"{CONTROL_PATH}?cmd={cmd_str}"
                    )
                    try:
                        async with cfg_session.get(
                            cmd_url,
                            timeout=aiohttp.ClientTimeout(total=5),
                        ) as r:
                            body = (await r.text()).strip()
                            if r.status == 200 and body == "OK":
                                _log("info", f"Applied {nvs_key} setting to device NVS.")
                            else:
                                _log(
                                    "info",
                                    f"Could not apply {nvs_key} "
                                    f"(HTTP {r.status}: {body!r}) — "
                                    "firmware may not support this command yet.",
                                )
                    except Exception as exc:  # noqa: BLE001
                        _log(
                            "info",
                            f"Could not apply {nvs_key} setting ({exc}) — "
                            "device may not support this command yet.",
                        )
        except Exception as exc:  # noqa: BLE001
            _log("info", f"Settings pre-provisioning skipped ({exc}).")

    # Result holders for the OTA upload.  Using variables instead of an
    # immediate return lets us run the post-reboot settings re-application
    # step (below) before returning to the caller.
    _ota_ok: bool = False
    _ota_msg: str = ""

    t_start = time.monotonic()
    try:
        async with aiohttp.ClientSession() as session:
            # Send the firmware as a raw binary body (Content-Type:
            # application/octet-stream).  The device-side OTA handler reads
            # the Content-Length header to know the total size, writes the
            # first chunk from the httpd buffer, then streams the rest directly
            # from the socket – no multipart parsing needed.
            _log("info", "Uploading firmware (raw binary POST)…")

            # Background task: log periodic progress messages so the UI shows
            # activity during the long upload instead of going silent.
            async def _progress_logger() -> None:
                try:
                    while True:
                        await asyncio.sleep(_PROGRESS_INTERVAL_S)
                        elapsed = time.monotonic() - t_start
                        _log(
                            "info",
                            f"Upload in progress… {elapsed:.0f} s elapsed "
                            f"(firmware: {firmware_kb:.0f} KB)",
                        )
                except asyncio.CancelledError:
                    pass

            progress_task = asyncio.create_task(_progress_logger())
            try:
                async with session.post(
                    url,
                    data=firmware_data,
                    headers={"Content-Type": "application/octet-stream"},
                    # No hard total timeout so slow WiFi connections don't time out
                    # mid-upload; rely on a per-read timeout instead so a stalled
                    # server is still detected.
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=600),
                ) as resp:
                    progress_task.cancel()
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
                            _ota_ok = True
                            _ota_msg = f"OTA flash successful ({elapsed:.1f} s): device rebooted."
                        else:
                            _log("error", f"HTTP {resp.status} after {elapsed:.1f} s — response payload incomplete")
                            if resp.status == 404:
                                hint = (
                                    "The device HTTP server returned 404 — the OTA handler "
                                    "was not reached. This can happen when the telemetry task "
                                    "on the device causes a WiFi disruption mid-upload. "
                                    "Update the firmware to include the s_ota_active fix so "
                                    "telemetry is paused during the upload, then retry."
                                )
                                _log("error", hint)
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
                        _ota_ok = True
                        _ota_msg = f"OTA flash successful ({elapsed:.1f} s): {body}"
                    else:
                        _log("error", f"HTTP {resp.status} after {elapsed:.1f} s — device response: {text.strip()}")
                        msg = f"OTA failed, HTTP {resp.status}: {text.strip()}"
                        return False, msg, log
            finally:
                if not progress_task.done():
                    progress_task.cancel()
                    try:
                        await asyncio.wait_for(progress_task, timeout=1.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

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
        exc_str = str(exc)
        msg = f"OTA flash failed after {elapsed:.1f} s: {exc}"
        _log("error", msg)
        # Provide an actionable hint when the device resets the connection.
        # This can happen for two distinct reasons:
        # 1. The partition table has only one OTA slot (ota_0 only, e.g. the
        #    factory huge_app.csv layout).  esp_ota_begin() then fails with
        #    ESP_ERR_OTA_PARTITION_CONFLICT and the Arduino Update library calls
        #    abort(), crashing the device and resetting the TCP connection.
        #    Fix: flash the latest firmware via serial — the serial flash now
        #    writes the dual-OTA partition table (partitions.bin) at 0x8000,
        #    giving the device both ota_0 and ota_1 slots.  OTA will then write
        #    to ota_1 while running from ota_0.
        # 2. The telemetry task is still holding SSL/TLS heap during the OTA
        #    upload, exhausting available heap.  Fix: the latest firmware
        #    supports cmd=OFF to pause telemetry before flashing (s_ota_active).
        if isinstance(exc, ConnectionResetError) or "[Errno 104]" in exc_str:
            _log(
                "error",
                "The device reset the TCP connection mid-upload. "
                "Most likely cause: the partition table only has one OTA slot "
                "(ota_0), so esp_ota_begin() fails and the device crashes. "
                "Fix: flash the latest firmware via serial — the serial flash "
                "now writes a dual-OTA partition table (ota_0 + ota_1) at "
                "0x8000 so subsequent WiFi OTA updates work correctly.",
            )
        return False, msg, log

    # -----------------------------------------------------------------------
    # Post-OTA: wait for the device to reboot and reconnect, then re-apply
    # LED/beep settings via /api/control.
    #
    # Rationale: the pre-OTA /api/control writes happen while the device is
    # running the *old* firmware.  After flashing, the ESP32 calls
    # esp_restart().  On the very first boot after a firmware upgrade,
    # nvs_flash_init() may return ESP_ERR_NVS_NEW_VERSION_FOUND (if the new
    # firmware was built with a different ESP-IDF version that changed the NVS
    # format) or ESP_ERR_NVS_NO_FREE_PAGES (if the NVS partition was full),
    # causing setup() to erase the entire NVS partition — including the
    # LED_RED_EN=0 we just wrote.  Re-applying the settings after the reboot
    # guarantees the LEDs are off even when NVS was wiped on first boot.
    # -----------------------------------------------------------------------
    if _ota_ok and _setting_cmds:
        _log(
            "info",
            f"OTA complete. Waiting up to {_POST_OTA_WAIT_S} s for device "
            "to reboot and reconnect before re-applying LED/beep settings…",
        )
        uptime_url = (
            f"http://{validated_ip}:{device_port}{CONTROL_PATH}?cmd=UPTIME"
        )
        t_wait = time.monotonic()
        came_back = False
        while time.monotonic() - t_wait < _POST_OTA_WAIT_S:
            await asyncio.sleep(_POST_OTA_POLL_S)
            try:
                async with aiohttp.ClientSession() as poll_sess:
                    async with poll_sess.get(
                        uptime_url,
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as r:
                        if r.status == 200:
                            came_back = True
                            break
            except Exception:  # noqa: BLE001
                pass  # device still rebooting – try again

        if came_back:
            _log("info", "Device is back online; re-applying LED/beep settings…")
            try:
                async with aiohttp.ClientSession() as post_sess:
                    for nvs_key, cmd_str in _setting_cmds:
                        cmd_url = (
                            f"http://{validated_ip}:{device_port}"
                            f"{CONTROL_PATH}?cmd={cmd_str}"
                        )
                        try:
                            async with post_sess.get(
                                cmd_url,
                                timeout=aiohttp.ClientTimeout(total=5),
                            ) as r:
                                body = (await r.text()).strip()
                                if r.status == 200 and body == "OK":
                                    _log(
                                        "info",
                                        f"Post-reboot: re-applied {nvs_key} to device NVS.",
                                    )
                                else:
                                    _log(
                                        "info",
                                        f"Post-reboot: could not apply {nvs_key} "
                                        f"(HTTP {r.status}: {body!r}).",
                                    )
                        except Exception as exc:  # noqa: BLE001
                            _log(
                                "info",
                                f"Post-reboot: could not apply {nvs_key} ({exc}).",
                            )
            except Exception as exc:  # noqa: BLE001
                _log("info", f"Post-reboot settings re-application skipped ({exc}).")
        else:
            _log(
                "info",
                f"Device did not come back online within {_POST_OTA_WAIT_S} s. "
                "LED/beep settings may need to be re-applied on next flash.",
            )

    return _ota_ok, _ota_msg, log


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
