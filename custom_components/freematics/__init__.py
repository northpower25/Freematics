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
from collections import deque
from datetime import datetime, timezone
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
from .const import (
    CONF_CONNECTION_TYPE,
    CONN_TYPE_CELLULAR,
    CONN_TYPE_WIFI,
    DEBUG_HISTORY_SIZE,
    SENSOR_DEFINITIONS,
)
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

PLATFORMS = ["sensor", "button", "device_tracker"]


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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current version.

    Version 1 → 2
    ~~~~~~~~~~~~~~
    Entity IDs were previously derived from the human-readable sensor name
    (e.g. ``sensor.accelerometer_x``) because no ``suggested_object_id`` was
    set.  Version 2 enforces the ``sensor.freematics_{id8}_{key}`` scheme
    that matches the dashboard discovery regex and multi-device naming
    conventions introduced in PR #39.  The migration looks up each entity by
    its stable unique_id and renames it to the canonical form.
    """
    _LOGGER.info(
        "Migrating Freematics config entry from version %s", config_entry.version
    )

    if config_entry.version < 2:
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        registry = er.async_get(hass)
        webhook_id = config_entry.data[CONF_WEBHOOK_ID]
        device_slug = webhook_id[:8]

        # ── Sensor entities ────────────────────────────────────────────
        for key in SENSOR_DEFINITIONS:
            unique_id = f"freematics_{webhook_id}_{key}"
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is None:
                continue
            new_entity_id = f"sensor.freematics_{device_slug}_{key}"
            if entity_id != new_entity_id:
                try:
                    registry.async_update_entity(entity_id, new_entity_id=new_entity_id)
                    _LOGGER.debug("Renamed %s → %s", entity_id, new_entity_id)
                except Exception as exc:  # noqa: BLE001 – migration must not abort on rename failure
                    _LOGGER.warning(
                        "Could not rename %s → %s: %s", entity_id, new_entity_id, exc
                    )

        # ── Debug sensor ───────────────────────────────────────────────
        debug_unique_id = f"freematics_{webhook_id}_debug"
        debug_entity_id = registry.async_get_entity_id("sensor", DOMAIN, debug_unique_id)
        if debug_entity_id is not None:
            new_debug_id = f"sensor.freematics_{device_slug}_debug"
            if debug_entity_id != new_debug_id:
                try:
                    registry.async_update_entity(debug_entity_id, new_entity_id=new_debug_id)
                    _LOGGER.debug("Renamed %s → %s", debug_entity_id, new_debug_id)
                except Exception as exc:  # noqa: BLE001 – migration must not abort on rename failure
                    _LOGGER.warning(
                        "Could not rename %s → %s: %s", debug_entity_id, new_debug_id, exc
                    )

        # ── Device tracker ─────────────────────────────────────────────
        # "standort" is the established suffix used by device_tracker.py and
        # must match the unique_id / suggested_object_id set there.
        tracker_unique_id = f"freematics_{webhook_id}_standort"
        tracker_entity_id = registry.async_get_entity_id(
            "device_tracker", DOMAIN, tracker_unique_id
        )
        if tracker_entity_id is not None:
            new_tracker_id = f"device_tracker.freematics_{device_slug}_standort"
            if tracker_entity_id != new_tracker_id:
                try:
                    registry.async_update_entity(
                        tracker_entity_id, new_entity_id=new_tracker_id
                    )
                    _LOGGER.debug("Renamed %s → %s", tracker_entity_id, new_tracker_id)
                except Exception as exc:  # noqa: BLE001 – migration must not abort on rename failure
                    _LOGGER.warning(
                        "Could not rename %s → %s: %s",
                        tracker_entity_id,
                        new_tracker_id,
                        exc,
                    )

        hass.config_entries.async_update_entry(config_entry, version=2)
        _LOGGER.info("Migration to version 2 complete")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freematics ONE+ from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # Determine display label for the configured connection type.
    conn_type = entry.data.get(CONF_CONNECTION_TYPE, CONN_TYPE_WIFI)
    if conn_type == CONN_TYPE_CELLULAR:
        conn_label = "LTE"
        conn_mode = 1
    elif conn_type == CONN_TYPE_WIFI:
        conn_label = "WiFi"
        conn_mode = 2
    else:
        conn_label = "WiFi+LTE"
        conn_mode = 3

    # Per-device debug state: rolling history of raw payloads and error log.
    raw_history: deque[str] = deque(maxlen=DEBUG_HISTORY_SIZE)
    error_log: deque[str] = deque(maxlen=DEBUG_HISTORY_SIZE)

    # Diagnostic tracking state – updated on every incoming webhook.
    diag: dict = {
        "conn_errors": 0,
        "last_wifi_connection": None,
        "last_lte_connection": None,
        "last_packet_time": None,
        # GPS
        "gps_active": False,
        "gps_satellites": None,
        "gps_errors": 0,
        "last_gps_connection": None,
        # OBD2
        "obd_active": False,
        "obd_errors": 0,
        "last_obd_connection": None,
        "obd_services_seen": set(),
    }

    # OBD-II sensor keys (those that require an active OBD2 connection)
    _OBD_KEYS = {
        "speed", "rpm", "throttle", "engine_load", "coolant_temp",
        "intake_temp", "fuel_pressure", "timing_advance",
        "short_fuel_trim_1", "long_fuel_trim_1",
        "short_fuel_trim_2", "long_fuel_trim_2",
    }

    async def handle_webhook(hass, webhook_id, request):
        """Handle incoming telemetry data from the Freematics device."""
        # The firmware sends data in Freematics text format:
        #   "PID_HEX:value,PID_HEX:value,...*CHECKSUM"
        # Try JSON first for forward compatibility, then fall back to the
        # native Freematics text format.
        data: dict | None = None
        raw_body: str = ""
        try:
            data = await request.json()
            raw_body = str(data)
        except Exception:  # noqa: BLE001
            pass

        if data is None:
            try:
                raw_body = await request.text()
                if raw_body:
                    data = _parse_freematics_payload(raw_body)
            except Exception:  # noqa: BLE001
                msg = "Freematics webhook: failed to parse payload"
                _LOGGER.warning(msg)
                error_log.append(msg)
                diag["conn_errors"] += 1

        # Store raw payload in rolling history for the debug entity.
        if raw_body:
            raw_history.appendleft(raw_body)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if not data:
            _LOGGER.debug("Freematics webhook received empty or unparseable payload")
            diag["conn_errors"] += 1
            # Still notify debug sensor so errors / raw history are visible.
            if raw_body:
                async_dispatcher_send(
                    hass,
                    f"{DOMAIN}_{webhook_id}_debug",
                    _build_debug_payload(conn_label, conn_mode, diag, raw_history, error_log, now_iso),
                )
            return

        _LOGGER.debug("Freematics webhook received: %s", data)

        # ── Update diagnostic state from received data ─────────────────
        diag["last_packet_time"] = now_iso
        if conn_mode == 1:
            diag["last_lte_connection"] = now_iso
        else:
            diag["last_wifi_connection"] = now_iso

        # GPS: mark active when valid lat/lng coordinates arrive; do NOT reset
        # to False on packets without GPS data because not every telemetry
        # packet carries a GPS fix (the firmware only transmits GPS when a new
        # fix is available).  last_gps_connection already tells the user when
        # GPS last delivered a valid position.
        has_gps = "lat" in data and "lng" in data
        if has_gps:
            diag["gps_active"] = True
            diag["last_gps_connection"] = now_iso

        # GPS satellite count (sent even without a full position fix)
        if "satellites" in data:
            diag["gps_satellites"] = data["satellites"]

        # OBD2: mark active when any OBD2-specific key arrives; do NOT reset to
        # False on packets without OBD data – the firmware does not include OBD
        # PIDs in every telemetry frame (they are skipped when the ECU is slow),
        # so absence in a single packet does not imply OBD is disconnected.
        obd_keys_present = {k for k in data if k in _OBD_KEYS}
        if obd_keys_present:
            diag["obd_active"] = True
            diag["last_obd_connection"] = now_iso
            diag["obd_services_seen"].update(obd_keys_present)

        async_dispatcher_send(hass, f"{DOMAIN}_{webhook_id}", data)

        # Notify the debug sensor of the current diagnostic state.
        async_dispatcher_send(
            hass,
            f"{DOMAIN}_{webhook_id}_debug",
            _build_debug_payload(conn_label, conn_mode, diag, raw_history, error_log, now_iso),
        )

    async_register(
        hass,
        DOMAIN,
        "Freematics ONE+",
        webhook_id,
        handle_webhook,
        local_only=False,
        allowed_methods=["POST"],
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_WEBHOOK_ID: webhook_id,
        "connection_type": conn_label,
        "raw_history": raw_history,
        "error_log": error_log,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _build_debug_payload(
    conn_label: str,
    conn_mode: int,
    diag: dict,
    raw_history: deque,
    error_log: deque,
    now_iso: str,
) -> dict:
    """Assemble the debug dispatcher payload from current diagnostic state."""
    _UNK = "Unbekannt"

    return {
        "connection_type": conn_label,
        "connection_mode": conn_mode,
        "connection_errors": diag["conn_errors"],
        "last_wifi_connection": diag["last_wifi_connection"] or _UNK,
        "last_lte_connection": diag["last_lte_connection"] or _UNK,
        "last_packet_time": diag["last_packet_time"] or _UNK,
        # GPS
        "gps_configured": "Unbekannt",
        "gps_active": 1 if diag["gps_active"] else 0,
        "gps_satellites": diag["gps_satellites"] if diag["gps_satellites"] is not None else _UNK,
        "gps_errors": diag["gps_errors"],
        "last_gps_connection": diag["last_gps_connection"] or _UNK,
        # OBD2
        "obd_configured": "Unbekannt",
        "obd_active": 1 if diag["obd_active"] else 0,
        "obd_services": sorted(diag["obd_services_seen"]) if diag["obd_services_seen"] else _UNK,
        "obd_errors": diag["obd_errors"],
        "last_obd_connection": diag["last_obd_connection"] or _UNK,
        # SD card – not determinable from webhook alone
        "sd_configured": _UNK,
        "sd_present": _UNK,
        "sd_storage": _UNK,
        # HTTPD – not determinable from webhook alone
        "httpd_configured": _UNK,
        "httpd_active": _UNK,
        "httpd_port": _UNK,
        "httpd_errors": _UNK,
        # BLE – not determinable from webhook alone
        "ble_configured": _UNK,
        "ble_active": _UNK,
        # FW version – not transmitted in webhook payloads
        "fw_version": _UNK,
        # Raw data for advanced debugging
        "raw_data": list(raw_history),
        "errors": list(error_log),
    }


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    async_unregister(hass, webhook_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
