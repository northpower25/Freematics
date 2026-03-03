"""The Freematics ONE+ integration.

This integration receives telemetry data pushed directly from the Freematics
ONE+ device via HTTPS webhook.  It is compatible with both locally accessible
Home Assistant instances and the Nabu Casa cloud remote UI
(<id>.ui.nabu.casa) so end-users do not need VPN or port-forwarding.

Firmware configuration (build flags in firmware_v5/telelogger/platformio.ini):
  ENABLE_WIFI      = 1
  SERVER_PROTOCOL  = 3  (PROTOCOL_HTTPS_POST)
  SERVER_HOST      – set at runtime via NVS provisioning (config_nvs.bin)
  SERVER_PORT      – set at runtime via NVS provisioning (default: 443)
  WEBHOOK_PATH     – set at runtime via NVS provisioning

Browser-based serial flasher (Web Serial API):
  /api/freematics/flasher       – HTML flasher page (Chrome/Edge 89+)
  /api/freematics/manifest.json – esp-web-tools firmware manifest
  /api/freematics/firmware.bin  – Bundled firmware binary

Sidebar panel:
  Registered automatically at /freematics-dashboard when the integration
  is set up.  Provides a live vehicle telemetry dashboard and a
  browser-based firmware flasher with COM-port detection.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.webhook import (
    async_register,
    async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_WEBHOOK_ID, DOMAIN, PID_MAP
from .views import (
    FreematicsConfigNvsView,
    FreematicsFirmwareView,
    FreematicsFlashImageView,
    FreematicsFlasherView,
    FreematicsPartitionTableView,
    FreematicsPersonalisedManifestView,
    FreematicsProvisioningTokenView,
    FreematicsProxyOTAView,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


def _parse_freematics_payload(body: str) -> dict:
    """Parse the Freematics text telemetry format into a sensor-key → value dict.

    The firmware serialises each data sample as comma-separated ``PID:value``
    tokens, where PID is a hexadecimal string (upper-case, no leading zeros)
    and value is a decimal number.  The message ends with ``*XX`` (checksum).

    Multi-value PIDs (e.g. the 3-axis accelerometer, PID 0x20) use semicolons
    to separate the components: ``20:-0.02;0.01;9.81``.

    OBD-II PIDs are stored by the firmware with the 0x100 bit set so they do
    not collide with GPS/device PIDs that share the same low byte:
      PID_SPEED (0x0D) → stored as 0x10D → hex string ``"10D"``

    Example input: ``"0:17225,24:370,20:0;0;0,82:29*DA"``
    Returns: ``{"ts": 17225.0, "battery": 3.7, "acc_x": 0.0, ..., "device_temp": 29.0}``
    """
    # Strip the trailing *XX checksum.
    star = body.find("*")
    if star != -1:
        body = body[:star]

    result: dict = {}
    for token in body.split(","):
        token = token.strip()
        colon = token.find(":")
        if colon < 0:
            continue
        pid_hex = token[:colon].upper()
        value_str = token[colon + 1:]

        if pid_hex not in PID_MAP:
            continue

        key, scale = PID_MAP[pid_hex]

        if key == "acc":
            # 3-axis accelerometer: expand to individual acc_x / acc_y / acc_z.
            parts = value_str.split(";")
            for i, axis in enumerate(("acc_x", "acc_y", "acc_z")):
                if i < len(parts):
                    try:
                        result[axis] = round(float(parts[i]) * scale, 6)
                    except (ValueError, TypeError):
                        pass
        else:
            # For other multi-value PIDs use only the first component.
            raw = value_str.split(";")[0] if ";" in value_str else value_str
            try:
                val = float(raw) * scale
                result[key] = round(val, 6)
            except (ValueError, TypeError):
                result[key] = raw

    return result


_WWW_DIR = Path(__file__).parent / "www"
_PANEL_URL = "freematics-dashboard"
_STATIC_PATH = "/freematics_static"
# Extract the version declared in the panel JS so the cache-busting query
# parameter is always in sync without any manual maintenance.  Changing the
# PANEL_VERSION constant in freematics-panel.js is all that is needed to force
# browsers to discard their cached copy and fetch the updated file.
_m = re.search(
    rb"""PANEL_VERSION\s*=\s*["']([^"']+)["']""",
    (_WWW_DIR / "freematics-panel.js").read_bytes(),
)
if not _m:
    _LOGGER.warning(
        "Could not extract PANEL_VERSION from freematics-panel.js; "
        "browser cache busting may not work correctly"
    )
_PANEL_JS_VERSION = _m.group(1).decode() if _m else "0"
_PANEL_JS_URL = f"{_STATIC_PATH}/freematics-panel.js?v={_PANEL_JS_VERSION}"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration-wide HTTP views and sidebar panel (called once per HA startup)."""
    hass.http.register_view(FreematicsFlasherView())
    hass.http.register_view(FreematicsPersonalisedManifestView())
    hass.http.register_view(FreematicsFirmwareView())
    hass.http.register_view(FreematicsPartitionTableView())
    hass.http.register_view(FreematicsProxyOTAView())
    hass.http.register_view(FreematicsProvisioningTokenView())
    hass.http.register_view(FreematicsConfigNvsView())
    hass.http.register_view(FreematicsFlashImageView())

    # Serve the www/ directory so the panel JS and custom card are reachable.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(_STATIC_PATH, str(_WWW_DIR), cache_headers=True)]
    )

    # Register the sidebar panel once per HA process startup.
    # HA's ha-panel-custom frontend component reads panel config from
    # panel.config._panel_custom, so the settings must be nested there.
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Freematics ONE+",
        sidebar_icon="mdi:car-connected",
        frontend_url_path=_PANEL_URL,
        config={
            "_panel_custom": {
                "name": "freematics-panel",
                "module_url": _PANEL_JS_URL,
                "embed_iframe": False,
                "trust_external": False,
            }
        },
        require_admin=False,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freematics ONE+ from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def handle_webhook(hass, webhook_id, request):
        """Handle incoming telemetry data from the Freematics device."""
        # The firmware sends data in Freematics text format:
        #   "PID_HEX:value,PID_HEX:value,...*CHECKSUM"
        # Try JSON first for forward compatibility, then fall back to the
        # native Freematics text format.
        data: dict | None = None
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            pass

        if data is None:
            try:
                body = await request.text()
                if body:
                    data = _parse_freematics_payload(body)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Freematics webhook: failed to parse payload")

        if not data:
            _LOGGER.debug("Freematics webhook received empty or unparseable payload")
            return

        _LOGGER.debug("Freematics webhook received: %s", data)
        async_dispatcher_send(hass, f"{DOMAIN}_{webhook_id}", data)

    async_register(
        hass,
        DOMAIN,
        "Freematics ONE+",
        webhook_id,
        handle_webhook,
        local_only=False,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_WEBHOOK_ID: webhook_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    async_unregister(hass, webhook_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
