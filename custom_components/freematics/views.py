"""HTTP views for Freematics ONE+ integration.

Serves the following endpoints:
  GET  /api/freematics/flasher          – Browser-based serial flasher (HTML)
  GET  /api/freematics/manifest.json    – esp-web-tools firmware manifest
                                          Accepts optional ?token=<tok> to return a
                                          personalised manifest with NVS settings part.
  GET  /api/freematics/firmware.bin     – Bundled pre-compiled firmware binary
  GET  /api/freematics/config_nvs.bin   – NVS partition image with device settings
                                          Requires ?token=<tok> issued by
                                          /api/freematics/provisioning_token.
  GET  /api/freematics/provisioning_token – (auth required) Issue a short-lived token
                                          that ties the NVS / manifest endpoints to
                                          the caller's config-entry settings.
  POST /api/freematics/wifi_ota         – Server-side WiFi OTA proxy (panel → HA → device)

The flasher page uses the Web Serial API (Chrome/Edge 89+) so the user can
flash the Freematics ONE+ that is connected to *their own computer's* USB port,
regardless of where Home Assistant is hosted.

NVS provisioning flow
─────────────────────
1. Panel JS calls GET /api/freematics/provisioning_token (HA auth required).
   Response: {"token": "…", "manifest_url": "…", "nvs_url": "…"}
2. Panel passes manifest_url to <esp-web-install-button>.
   esp-web-tools fetches the manifest and discovers the NVS part URL.
3. During flash, esp-web-tools writes firmware.bin at 0x10000 and
   config_nvs.bin at 0x9000 in one pass.
4. Device reboots with WiFi SSID/password, APN, and server settings
   already stored in NVS — no post-flash manual configuration needed.
"""

from __future__ import annotations

import ipaddress
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import (
    CONF_CELL_APN,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    DOMAIN,
)

# Token time-to-live in seconds (5 minutes).  After expiry the token is
# rejected so the window during which the unprotected NVS endpoint could
# serve WiFi credentials is minimised.
_TOKEN_TTL = 300

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"

# esp-web-tools manifest — describes the chip family and flash offsets.
# 0x10000 = 65536 – application partition offset for ESP32.
# 0x9000  = 36864 – NVS partition offset (huge_app partition scheme).
_MANIFEST_BASE = {
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


# ---------------------------------------------------------------------------
# Provisioning token + NVS partition endpoints
# ---------------------------------------------------------------------------

class FreematicsProvisioningTokenView(HomeAssistantView):
    """Issue a short-lived provisioning token tied to the caller's config entry.

    Accessible at GET /api/freematics/provisioning_token.

    Requires HA authentication (requires_auth = True).  The returned token is
    embedded in the manifest URL and the NVS endpoint URL so that esp-web-tools
    (running in the browser without a Bearer token) can download the
    personalised NVS partition image.

    Response JSON:
      {
        "token": "<hex token>",
        "manifest_url": "/api/freematics/manifest.json?token=<token>",
        "nvs_url": "/api/freematics/config_nvs.bin?token=<token>",
        "nvs_offset": 36864,
        "expires_in": 300
      }
    """

    url = "/api/freematics/provisioning_token"
    name = "api:freematics:provisioning_token"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Issue a provisioning token for the authenticated user's config entry."""
        hass = request.app["hass"]
        token = secrets.token_hex(32)
        expiry = time.monotonic() + _TOKEN_TTL

        entries = hass.config_entries.async_entries(DOMAIN)
        entry_id = entries[0].entry_id if entries else None

        token_store = hass.data.setdefault(DOMAIN, {}).setdefault("_tokens", {})
        token_store[token] = (entry_id, expiry)

        now = time.monotonic()
        expired = [t for t, (_, exp) in list(token_store.items()) if exp < now]
        for t in expired:
            token_store.pop(t, None)

        from .nvs_helper import NVS_PARTITION_OFFSET  # noqa: PLC0415

        return web.Response(
            body=json.dumps({
                "token": token,
                "manifest_url": f"/api/freematics/manifest.json?token={token}",
                "nvs_url": f"/api/freematics/config_nvs.bin?token={token}",
                "nvs_offset": NVS_PARTITION_OFFSET,
                "expires_in": _TOKEN_TTL,
            }).encode("utf-8"),
            content_type="application/json",
        )


class FreematicsPersonalisedManifestView(HomeAssistantView):
    """Serve the esp-web-tools manifest, optionally with a personalised NVS part.

    Accessible at GET /api/freematics/manifest.json?token=<token>.

    requires_auth is False because esp-web-tools fetches this via the browser
    native fetch() API without a HA Bearer token.

    Without a token the response is the standard manifest (firmware only).
    With a valid token a second part is appended pointing to the NVS partition
    image so the device boots with pre-configured settings.
    """

    url = "/api/freematics/manifest.json"
    name = "api:freematics:manifest"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the firmware manifest JSON."""
        import copy  # noqa: PLC0415

        token = request.rel_url.query.get("token", "")
        manifest = copy.deepcopy(_MANIFEST_BASE)

        if token:
            hass = request.app["hass"]
            token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
            entry_id, expiry = token_store.get(token, (None, 0))
            if expiry > time.monotonic() and entry_id is not None:
                from .nvs_helper import NVS_PARTITION_OFFSET  # noqa: PLC0415
                manifest["builds"][0]["parts"].append(
                    {
                        "path": f"config_nvs.bin?token={token}",
                        "offset": NVS_PARTITION_OFFSET,
                    }
                )

        return web.Response(
            body=json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
        )


class FreematicsConfigNvsView(HomeAssistantView):
    """Serve a personalised NVS partition image for initial device provisioning.

    Accessible at GET /api/freematics/config_nvs.bin?token=<token>.

    requires_auth is False because esp-web-tools fetches this directly from
    the browser using the URL embedded in the manifest (no Bearer token).
    A valid provisioning token is required; tokens are issued by
    /api/freematics/provisioning_token (auth required) and expire after
    _TOKEN_TTL seconds.

    The NVS image encodes:
      - WiFi SSID / password (so the device connects on first boot)
      - Cellular APN (cellular fallback)
      - Server host / port / webhook path (firmware v5.1+ with NVS server settings)
    """

    url = "/api/freematics/config_nvs.bin"
    name = "api:freematics:config_nvs"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the NVS partition binary for the token's config entry."""
        token = request.rel_url.query.get("token", "")
        if not token:
            return web.Response(status=400, text="token parameter required")

        hass = request.app["hass"]
        token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
        entry_id, expiry = token_store.get(token, (None, 0))
        if expiry <= time.monotonic() or entry_id is None:
            return web.Response(status=403, text="Invalid or expired token")

        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return web.Response(status=404, text="Config entry not found")

        cfg = {**entry.data, **entry.options}
        wifi_ssid = cfg.get(CONF_WIFI_SSID, "")
        wifi_password = cfg.get(CONF_WIFI_PASSWORD, "")
        cell_apn = cfg.get(CONF_CELL_APN, "")
        webhook_id = cfg.get(CONF_WEBHOOK_ID, "")

        server_host = ""
        server_port = 443
        webhook_path = ""
        try:
            from homeassistant.helpers.network import get_url  # noqa: PLC0415
            base_url = get_url(hass, prefer_external=True)
            parsed = urlparse(base_url)
            server_host = parsed.hostname or ""
            if parsed.port:
                server_port = parsed.port
            elif parsed.scheme == "https":
                server_port = 443
            else:
                server_port = 80
        except Exception:  # noqa: BLE001
            # get_url() can raise NoURLAvailableError or other network-related
            # errors when no external URL is configured; silently skip server
            # settings in that case — the device will use compile-time defaults.
            pass

        if webhook_id:
            webhook_path = f"/api/webhook/{webhook_id}"

        from .nvs_helper import generate_nvs_partition  # noqa: PLC0415

        nvs_data = await hass.async_add_executor_job(
            generate_nvs_partition,
            wifi_ssid,
            wifi_password,
            cell_apn,
            server_host,
            server_port,
            webhook_path,
            True,  # enable_httpd: activate built-in HTTP server on first boot
        )

        if nvs_data is None:
            return web.Response(
                status=503,
                text=(
                    "NVS partition generation failed. "
                    "Install esp-idf-nvs-partition-gen: pip install esp-idf-nvs-partition-gen"
                ),
            )

        return web.Response(
            body=nvs_data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=config_nvs.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )
