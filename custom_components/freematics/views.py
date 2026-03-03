"""HTTP views for Freematics ONE+ integration.

Serves the following endpoints:
  GET  /api/freematics/flasher       – Browser-based serial flasher (HTML)
  GET  /api/freematics/manifest.json – esp-web-tools firmware manifest
  GET  /api/freematics/firmware.bin  – Bundled pre-compiled firmware binary
  POST /api/freematics/wifi_ota      – Server-side WiFi OTA proxy (panel → HA → device)

The flasher page uses the Web Serial API (Chrome/Edge 89+) so the user can
flash the Freematics ONE+ that is connected to *their own computer's* USB port,
regardless of where Home Assistant is hosted.
"""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"

# esp-web-tools manifest — describes the chip family and flash offsets.
# 0x10000 = 65536 – application partition offset for ESP32.
_MANIFEST = {
    "name": "Freematics ONE+ Telelogger",
    "version": "5.0",
    "new_install_prompt_erase": False,
    "builds": [
        {
            "chipFamily": "ESP32",
            "parts": [
                {"path": "firmware.bin", "offset": 65536},
            ],
        }
    ],
}

_FLASHER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freematics ONE+ Browser Flasher</title>
  <script
    type="module"
    src="https://unpkg.com/esp-web-tools@10/dist/web/install-button.js?module"
  ></script>
  <style>
    *   { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 640px; margin: 2rem auto; padding: 0 1.2rem; color: #333;
    }
    h1  { color: #03a9f4; font-size: 1.5rem; }
    .card {
      border-radius: 8px; padding: 1rem 1.2rem; margin: 1rem 0;
      background: #f5f5f5;
    }
    .info { background: #e3f2fd; border-left: 4px solid #03a9f4; }
    .warn { background: #fff8e1; border-left: 4px solid #ffc107; }
    .ok   { background: #e8f5e9; border-left: 4px solid #4caf50; }
    .err  { background: #ffebee; border-left: 4px solid #f44336; }
    ul, ol { margin: 0.4rem 0; padding-left: 1.4rem; }
    li     { margin: 0.3rem 0; }
    code   { background: #eee; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }
    a      { color: #03a9f4; }
    esp-web-install-button { display: block; margin: 1.4rem 0; }
    esp-web-install-button::part(button) {
      background: #03a9f4; color: #fff; border: none;
      padding: 0.75rem 2rem; font-size: 1.05rem;
      border-radius: 6px; cursor: pointer; width: 100%;
    }
    esp-web-install-button::part(button):hover { background: #0288d1; }
  </style>
</head>
<body>
  <h1>&#9889; Freematics ONE+ Browser Flasher</h1>

  <div class="card ok">
    This page flashes the firmware directly from <strong>your browser</strong>
    to the Freematics ONE+ connected to <strong>your computer's USB port</strong>
    &mdash; your computer does not need to be the Home Assistant server.
  </div>

  <div class="card info">
    <strong>Requirements:</strong>
    <ul>
      <li>Google Chrome or Microsoft Edge (version 89 or newer)</li>
      <li>Freematics ONE+ connected via USB to <em>this computer</em></li>
      <li>
        USB-Serial driver installed for your device's chip:<br>
        &bull; <a href="https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers"
                  target="_blank" rel="noopener">CP210x driver (Silicon Labs)</a><br>
        &bull; <a href="https://www.wch-ic.com/downloads/CH341SER_EXE.html"
                  target="_blank" rel="noopener">CH340 driver (WCH)</a>
      </li>
    </ul>
  </div>

  <div id="no-serial-warn" class="card warn" style="display:none">
    &#9888; <strong>Web Serial API not available.</strong><br>
    Please open this page in <strong>Google Chrome</strong> or
    <strong>Microsoft Edge</strong> (version 89+).<br>
    Alternatively, use the <strong>WiFi OTA</strong> flash button in the
    Home Assistant integration.
  </div>

  <esp-web-install-button manifest="/api/freematics/manifest.json">
    <button slot="activate">&#9889; Connect &amp; Flash Firmware</button>
    <span slot="unsupported">
      <div class="card err">
        &#9888; Web Serial is not supported in this browser.
        Please use Chrome or Edge 89+.
      </div>
    </span>
  </esp-web-install-button>

  <div class="card">
    <strong>Steps:</strong>
    <ol>
      <li>Click <em>Connect &amp; Flash Firmware</em></li>
      <li>
        Select the serial port of the Freematics ONE+ from the browser dialog.<br>
        <small>Look for: <code>CP2102</code>, <code>CH340</code>, or a
        similar USB-Serial device name.</small>
      </li>
      <li>The firmware flashes automatically (takes ~30 s)</li>
      <li>The device restarts and begins sending data to Home Assistant</li>
    </ol>
  </div>

  <div class="card warn">
    <strong>&#128296; If the flash hangs or nothing happens after port selection:</strong>
    <p>Use <strong>esptool.py</strong> from the command line as a fallback:</p>
    <ol>
      <li>Download the firmware:
        <a href="/api/freematics/firmware.bin" download="telelogger.bin">telelogger.bin</a>
      </li>
      <li>Install: <code>pip install esptool</code></li>
      <li>Flash (replace <em>PORT</em> with e.g. <code>COM3</code> or <code>/dev/ttyUSB0</code>):<br>
        <code>esptool.py --chip esp32 --port PORT --baud 921600 write_flash --flash_mode dio --flash_size detect 0x10000 telelogger.bin</code>
      </li>
    </ol>
    <p>See <a href="https://github.com/northpower25/Freematics/blob/master/docs/README.md#method-d-manual-flash-fallback"
       target="_blank" rel="noopener">Method D in the documentation</a> for full details including VS Code + PlatformIO.</p>
  </div>

  <p style="margin-top:2rem">
    <a href="javascript:history.back()">&#8592; Back to Home Assistant</a>
    &nbsp;&nbsp;
    <a href="https://github.com/northpower25/Freematics/blob/master/docs/README.md"
       target="_blank" rel="noopener">Documentation</a>
  </p>

  <script>
    if (!('serial' in navigator)) {
      document.getElementById('no-serial-warn').style.display = 'block';
    }
  </script>
</body>
</html>
"""


class FreematicsFlasherView(HomeAssistantView):
    """Serve the browser-based serial flasher HTML page.

    Accessible at /api/freematics/flasher.

    requires_auth is False so users can open it directly from their browser
    without needing to pass a Bearer token (the page itself is just static HTML).
    The firmware this integration uses is open-source (BSD-licensed), so there
    are no proprietary concerns with serving it without authentication.
    """

    url = "/api/freematics/flasher"
    name = "api:freematics:flasher"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the flasher HTML page."""
        return web.Response(
            body=_FLASHER_HTML.encode("utf-8"),
            content_type="text/html",
            charset="utf-8",
        )


class FreematicsManifestView(HomeAssistantView):
    """Serve the esp-web-tools firmware manifest.

    Accessible at /api/freematics/manifest.json.

    requires_auth is False because esp-web-tools (loaded from CDN) fetches this
    via the browser's native fetch() API and cannot inject a HA Bearer token.
    The manifest is non-sensitive metadata describing the firmware flash offsets.
    """

    url = "/api/freematics/manifest.json"
    name = "api:freematics:manifest"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the firmware manifest JSON."""
        return web.Response(
            body=json.dumps(_MANIFEST).encode("utf-8"),
            content_type="application/json",
        )


class FreematicsFirmwareView(HomeAssistantView):
    """Serve the bundled firmware binary.

    Accessible at /api/freematics/firmware.bin.
    Referenced by the manifest as a relative path.

    requires_auth is False because esp-web-tools (loaded from CDN) fetches this
    via the browser's native fetch() API and cannot inject a HA Bearer token.
    The firmware binary is open-source (BSD-licensed) and ships in the HACS
    download, so it is not sensitive data.

    These views are registered in async_setup() and persist for the lifetime of
    the HA process. There is no standard HA mechanism to unregister aiohttp
    routes; if the integration is removed and re-added, the routes are
    re-registered harmlessly (aiohttp deduplicates them).
    """

    url = "/api/freematics/firmware.bin"
    name = "api:freematics:firmware"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the firmware binary (read in a thread executor)."""
        if not FIRMWARE_PATH.exists():
            return web.Response(status=404, text="Firmware binary not found")
        try:
            hass = request.app["hass"]
            data: bytes = await hass.async_add_executor_job(FIRMWARE_PATH.read_bytes)
        except OSError as exc:
            return web.Response(status=500, text=f"Cannot read firmware: {exc}")
        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=telelogger.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )


class FreematicsProxyOTAView(HomeAssistantView):
    """Proxy a WiFi OTA flash request from the panel browser to the device.

    Accessible at POST /api/freematics/wifi_ota.

    Accepts JSON body: {"device_ip": "192.168.x.x", "device_port": 80}

    The browser panel sends this request (with HA auth token).  This view
    then uses the HA server to push the bundled firmware binary to the device
    via HTTP multipart upload.  The device must be reachable from the HA
    server on the specified IP and port.

    requires_auth is True – only authenticated HA users may trigger a flash.
    """

    url = "/api/freematics/wifi_ota"
    name = "api:freematics:wifi_ota"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Trigger WiFi OTA flash from the HA server to the device."""
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "Invalid JSON body"}).encode(),
                content_type="application/json",
            )

        device_ip = str(data.get("device_ip", "")).strip()
        try:
            device_port = int(data.get("device_port", 80))
        except (TypeError, ValueError):
            device_port = 80

        if not device_ip:
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "device_ip is required"}).encode(),
                content_type="application/json",
            )

        # Validate that device_ip is a well-formed IP address (not a hostname or
        # URL) to mitigate SSRF: ipaddress.ip_address rejects anything that is
        # not a pure IPv4 or IPv6 literal.
        try:
            ipaddress.ip_address(device_ip)
        except ValueError:
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "device_ip must be a valid IPv4 or IPv6 address"}).encode(),
                content_type="application/json",
            )

        from .flash_manager import async_flash_wifi  # noqa: PLC0415

        ok, msg = await async_flash_wifi(device_ip, device_port)
        return web.Response(
            body=json.dumps({"ok": ok, "message": msg}).encode("utf-8"),
            content_type="application/json",
        )
