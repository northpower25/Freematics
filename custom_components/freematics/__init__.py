"""The Freematics ONE+ integration.

This integration receives telemetry data pushed directly from the Freematics
ONE+ device via HTTPS webhook.  It is compatible with both locally accessible
Home Assistant instances and the Nabu Casa cloud
(hooks.nabu.casa) so end-users do not need VPN or port-forwarding.

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

import asyncio
import logging
import re
import time
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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_WEBHOOK_ID, DOMAIN, PID_MAP
from .const import (
    CONF_CAN_EN,
    CONF_CLOUD_HOOK_URL,
    CONF_CONNECTION_TYPE,
    CONF_DEEP_STANDBY,
    CONF_DEVICE_IP,
    CONF_DEVICE_PORT,
    CONF_ENABLE_BLE,
    CONF_BEEP_EN,
    CONF_LED_WHITE_EN,
    CONF_OBD_EN,
    CONF_OPERATING_MODE,
    CONF_OTA_CHECK_INTERVAL_S,
    CONF_OTA_MODE,
    CONF_OTA_TOKEN,
    CONF_SETTINGS_VERSION,
    CONF_STANDBY_TIME_S,
    CONF_WIFI_SSID,
    CONN_TYPE_CELLULAR,
    CONN_TYPE_WIFI,
    DEBUG_HISTORY_SIZE,
    DEFAULT_DEVICE_PORT,
    DEFAULT_DEEP_STANDBY,
    DEFAULT_STANDBY_TIME_S,
    FIRMWARE_VERSION,
    OPERATING_MODE_DATALOGGER,
    OTA_MODE_DISABLED,
    PID_CONN_TYPE_CELLULAR,
    PID_CONN_TYPE_WIFI,
    SENSOR_DEFINITIONS,
)
from .views import (
    FreematicsBootloaderView,
    FreematicsConfigNvsView,
    FreematicsFirmwareView,
    FreematicsFlashImageView,
    FreematicsFlasherView,
    FreematicsOtaPullView,
    FreematicsOtaTokenView,
    FreematicsPartitionTableView,
    FreematicsPersonalisedManifestView,
    FreematicsProvisioningTokenView,
    FreematicsSerialConsoleView,
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
    hass.http.register_view(FreematicsSerialConsoleView())
    hass.http.register_view(FreematicsPersonalisedManifestView())
    hass.http.register_view(FreematicsFirmwareView())
    hass.http.register_view(FreematicsBootloaderView())
    hass.http.register_view(FreematicsPartitionTableView())
    hass.http.register_view(FreematicsProvisioningTokenView())
    hass.http.register_view(FreematicsConfigNvsView())
    hass.http.register_view(FreematicsFlashImageView())
    hass.http.register_view(FreematicsOtaTokenView())
    hass.http.register_view(FreematicsOtaPullView())

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

    # Determine configured device features from the config entry so the debug
    # sensor can show accurate "configured" state for HTTPD, BLE, etc.
    _cfg = {**(entry.data or {}), **(entry.options or {})}
    # HTTPD is always enabled in the NVS (see views.py enable_httpd = True).
    # Port 80 is the firmware default; CONF_DEVICE_PORT overrides it.
    _httpd_port: int = int(_cfg.get(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT))
    _ble_enabled: bool = bool(_cfg.get(CONF_ENABLE_BLE, False))
    _led_white_en: bool = bool(_cfg.get(CONF_LED_WHITE_EN, True))
    _beep_en: bool = bool(_cfg.get(CONF_BEEP_EN, True))
    _obd_en: bool = bool(_cfg.get(CONF_OBD_EN, True))
    _can_en: bool = bool(_cfg.get(CONF_CAN_EN, False))
    _standby_time_s: int = int(_cfg.get(CONF_STANDBY_TIME_S, DEFAULT_STANDBY_TIME_S))
    _deep_standby: bool = bool(_cfg.get(CONF_DEEP_STANDBY, DEFAULT_DEEP_STANDBY))
    # WiFi SSID from config — shown in the debug entity as the "configured" SSID
    # so the user can confirm which credentials were last provisioned to the device.
    _wifi_ssid_configured: str = _cfg.get(CONF_WIFI_SSID, "")
    # OTA configuration (for displaying in the debug entity so users can
    # quickly verify that OTA is provisioned correctly in the config entry).
    _ota_mode: str = _cfg.get(CONF_OTA_MODE, OTA_MODE_DISABLED)
    _ota_token_set: bool = bool(_cfg.get(CONF_OTA_TOKEN, ""))
    _ota_interval_s: int = int(_cfg.get(CONF_OTA_CHECK_INTERVAL_S, 0))
    # Effective firmware + NVS version expected on the device.
    # Format: "<FIRMWARE_VERSION>.<settings_version>" (e.g. "5.1.2026-03-17T16:32:29+00:00")
    # or just FIRMWARE_VERSION when no settings_version is set.
    _settings_version: str = _cfg.get(CONF_SETTINGS_VERSION, "")
    _effective_version: str = (
        f"{FIRMWARE_VERSION}.{_settings_version}" if _settings_version else FIRMWARE_VERSION
    )
    # Build the full OTA meta.json URL as the device uses it.
    # Priority: Nabu Casa Remote UI (*.ui.nabu.casa) > generic external URL.
    # Shown in the debug sensor so the user can paste it into a browser for
    # quick manual testing of the OTA endpoint.
    _ota_token: str = _cfg.get(CONF_OTA_TOKEN, "")
    _ota_meta_url: str = ""
    if _ota_token:
        _ota_base: str = ""
        try:
            from homeassistant.components import cloud as _ota_cloud  # noqa: PLC0415
            if _ota_cloud.async_is_logged_in(hass):
                _ota_base = _ota_cloud.async_remote_ui_url(hass)
        except Exception as _exc:  # noqa: BLE001
            _LOGGER.debug(
                "Freematics: Nabu Casa Remote UI not available for OTA meta URL (%s); "
                "falling back to get_url().",
                _exc,
            )
        if not _ota_base:
            try:
                from homeassistant.helpers.network import (  # noqa: PLC0415
                    get_url,
                    NoURLAvailableError,
                )
                _ota_base = get_url(hass, prefer_external=True)
            except Exception as _exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Freematics: could not resolve HA external URL for OTA meta URL (%s); "
                    "'OTA Meta URL' attribute will show 'Unbekannt'.",
                    _exc,
                )
        if _ota_base:
            _ota_meta_url = (
                f"{_ota_base.rstrip('/')}/api/freematics/ota_pull"
                f"/{_ota_token}/meta.json"
            )
    # Device IP for querying /api/info (SD card info).  May be empty.
    _device_ip: str = _cfg.get(CONF_DEVICE_IP, "")
    # Datalogger mode: HTTPD is the primary API; telelogger mode: HTTPD is still
    # running (for OTA and /api/control) but not the primary data path.
    _operating_mode = _cfg.get(CONF_OPERATING_MODE)
    if _operating_mode is not None:
        _is_datalogger = (_operating_mode == OPERATING_MODE_DATALOGGER)
    else:
        from .const import CONF_ENABLE_HTTPD  # noqa: PLC0415 - legacy compat
        _is_datalogger = bool(_cfg.get(CONF_ENABLE_HTTPD, False))

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
        # SD card – updated by periodic /api/info query when CONF_DEVICE_IP is set
        "sd_present": None,
        "sd_storage": None,
        "_last_info_query_t": 0.0,  # monotonic timestamp of last /api/info fetch
        # OTA pull – updated by FreematicsOtaPullView when an OTA event occurs
        "ota_last_success": None,
        "ota_last_error": None,
        "ota_last_version": None,
        # Firmware version – initialised to the bundled FIRMWARE_VERSION.
        # This reflects the version known to be running on the device after a
        # serial flash.  It is NOT updated from the OTA serve path because the
        # HA server cannot confirm whether the device successfully applied the
        # transmitted firmware (the device may fail to write it to its SD
        # staging area).
        "fw_version": FIRMWARE_VERSION,
        # NVS settings version reported by the device via /api/control?cmd=NVS_VER?
        # or /api/info.  Corresponds to the NVS_VER key in the device NVS.
        # None means not yet queried or device returned "-" (NVS never applied via OTA).
        "fw_version_device": None,
        # Live device state for white LED and beep – updated when the device reports
        # PID_LED_WHITE_STATE (0x84) / PID_BEEP_STATE (0x85) in its telemetry.
        # None means "not yet reported by device".
        "led_white_device": None,
        "beep_device": None,
        # OBD state (PID 0x89), CAN state (PID 0x8a), standby time (PID 0x8b),
        # deep standby (PID 0x8c) – live device state reported in telemetry.
        # None means "not yet received".
        "obd_state_device": None,
        "can_state_device": None,
        "standby_time_device": None,
        "deep_standby_device": None,
        # Raw CAN frames from CAN_DATA? query (list of strings, refreshed every 60 s).
        "can_frames": [],
        # WiFi SSID reported by the device via /api/control?cmd=SSID? query.
        # Queried at most once per minute alongside SD info (rate-limited via
        # _last_info_query_t).  None means not yet queried or no device IP.
        "wifi_ssid_device": None,
    }

    # OBD-II sensor keys (those that require an active OBD2 connection)
    _OBD_KEYS = {
        "speed", "rpm", "throttle", "engine_load", "coolant_temp",
        "intake_temp", "fuel_pressure", "timing_advance",
        "short_fuel_trim_1", "long_fuel_trim_1",
        "short_fuel_trim_2", "long_fuel_trim_2",
    }

    async def handle_webhook(hass, webhook_id, request):
        """Handle incoming telemetry data from the Freematics device.

        POST requests carry telemetry data in Freematics text format wrapped in
        a JSON body (firmware cloud-webhook mode) or as plain text (direct HA).
        """
        from aiohttp import web as _web  # noqa: PLC0415

        # ── Telemetry POST ───────────────────────────────────────────────────
        # The firmware sends telemetry in Freematics text format:
        #   "PID_HEX:value,PID_HEX:value,...*CHECKSUM"
        # Cloud webhook gateways (e.g. hooks.nabu.casa) require a valid JSON
        # body, so the firmware wraps the text in {"data":"<payload>"}.
        # Handle all three variants:
        #   1. JSON {"data": "<freematics_text>"} – firmware cloud-webhook mode
        #   2. Any other JSON dict                – future native-JSON support
        #   3. Plain text                         – direct HA / local delivery
        data: dict | None = None
        raw_body: str = ""
        try:
            json_body = await request.json()
            if (
                isinstance(json_body, dict)
                and "data" in json_body
                and isinstance(json_body["data"], str)
            ):
                # Firmware wrapped the Freematics text in {"data": "..."}.
                raw_body = json_body["data"]
                data = _parse_freematics_payload(raw_body)
            else:
                data = json_body
                raw_body = str(json_body)
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

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        if not data:
            _LOGGER.debug("Freematics webhook received empty or unparseable payload")
            diag["conn_errors"] += 1
            # Still notify debug sensor so errors / raw history are visible.
            # Also update last_packet_time so the user can tell the device IS
            # talking to HA even when the payload cannot be parsed (e.g. during
            # a firmware format change or a connectivity test POST).
            if raw_body:
                diag["last_packet_time"] = now_iso
                async_dispatcher_send(
                    hass,
                    f"{DOMAIN}_{webhook_id}_debug",
                    _build_debug_payload(
                        conn_label, conn_mode, diag, raw_history, error_log, now_iso,
                        _httpd_port, _ble_enabled,
                        _ota_mode, _ota_token_set, _ota_interval_s,
                        _led_white_en, _beep_en,
                        _ota_meta_url,
                        _wifi_ssid_configured,
                        _effective_version,
                        _obd_en, _can_en, _standby_time_s, _deep_standby,
                    ),
                )
            return

        _LOGGER.debug("Freematics webhook received: %s", data)

        # ── Update diagnostic state from received data ─────────────────
        diag["last_packet_time"] = now_iso

        # Determine which transport was used for this packet.
        # Priority 1: firmware-reported PID_CONN_TYPE (0x88): 1.0 = WiFi, 2.0 = Cellular.
        #   Available in firmware built from this source; not in older binaries.
        # Priority 2: fall back to the configured conn_mode when the PID is absent.
        #   - conn_mode 1 (pure LTE) → always cellular
        #   - conn_mode 2 (pure WiFi) → always WiFi
        #   - conn_mode 3 (WiFi+LTE) without PID: update both timestamps so
        #     neither shows "Unbekannt" forever (we can't distinguish the transport
        #     at the HTTP level when both WiFi and cellular use the same cloud hook).
        reported_conn_type = data.get("conn_type")  # PID 0x88 value (float or None)
        if reported_conn_type == PID_CONN_TYPE_CELLULAR:
            # Firmware explicitly reports cellular transport.
            diag["last_lte_connection"] = now_iso
        elif reported_conn_type == PID_CONN_TYPE_WIFI:
            # Firmware explicitly reports WiFi transport.
            diag["last_wifi_connection"] = now_iso
        elif conn_mode == 1:
            # Configured as pure cellular; no PID_CONN_TYPE from firmware.
            diag["last_lte_connection"] = now_iso
        elif conn_mode == 2:
            # Configured as pure WiFi; no PID_CONN_TYPE from firmware.
            diag["last_wifi_connection"] = now_iso
        else:
            # WiFi+LTE mode (conn_mode == 3) without PID_CONN_TYPE: update both so
            # neither timestamp stays "Unbekannt" indefinitely.  Once the device is
            # flashed with a build that includes PID_CONN_TYPE the timestamps will
            # be updated accurately per transport.
            diag["last_wifi_connection"] = now_iso
            diag["last_lte_connection"] = now_iso

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

        # Live LED/beep device state – firmware sends PID 0x84 (led_white_state)
        # and 0x85 (beep_state) on first packet and whenever they change.
        # Values are 1.0 (enabled) or 0.0 (disabled) after PID_MAP scale.
        if "led_white_state" in data:
            diag["led_white_device"] = bool(data["led_white_state"])
        if "beep_state" in data:
            diag["beep_device"] = bool(data["beep_state"])

        # OBD state (PID 0x89), CAN state (PID 0x8a), standby time (PID 0x8b),
        # deep standby (PID 0x8c) – firmware reports these so HA can show the
        # live device configuration.
        # Values arrive as floats after PID_MAP scale (1.0 = active, 0.0 = disabled).
        if "obd_state" in data:
            diag["obd_state_device"] = bool(data["obd_state"])
        if "can_state" in data:
            diag["can_state_device"] = bool(data["can_state"])
        if "standby_time_device" in data:
            # Store as integer seconds; 0 means "use firmware default".
            diag["standby_time_device"] = int(data["standby_time_device"])
        if "deep_standby_device" in data:
            diag["deep_standby_device"] = bool(data["deep_standby_device"])

        # Live SD card status – firmware sends PID 0x86 (sd_total_mb) and
        # 0x87 (sd_free_mb) once per minute.  sd_total_mb == 0 means no card.
        # Both PIDs are always transmitted together in the same buffer, but
        # we guard on both being present to avoid showing stale free-space
        # data if a single packet arrives that only contains one of them.
        if "sd_total_mb" in data and "sd_free_mb" in data:
            _sd_total = int(data["sd_total_mb"])
            _sd_free = int(data["sd_free_mb"])
            if _sd_total > 0:
                _sd_used = max(0, _sd_total - _sd_free)
                diag["sd_present"] = "Ja"
                diag["sd_storage"] = f"{_sd_total} MB total, {_sd_used} MB verwendet"
            else:
                diag["sd_present"] = "Nein"
                diag["sd_storage"] = "0 MB"
        elif "sd_total_mb" in data:
            # Only sd_total_mb received (sd_free_mb missing): update presence only.
            _sd_total = int(data["sd_total_mb"])
            diag["sd_present"] = "Ja" if _sd_total > 0 else "Nein"

        # Rate-limited device info refresh (SD card stats) via /api/info.
        # Only runs when CONF_DEVICE_IP is configured in the integration.
        # Uses a 60-second cooldown so every webhook does not trigger an
        # extra outbound HTTP request to the device.
        _now_t = time.monotonic()
        if _device_ip and (_now_t - diag["_last_info_query_t"]) >= 60:
            diag["_last_info_query_t"] = _now_t
            hass.async_create_task(_refresh_device_info())

        async_dispatcher_send(hass, f"{DOMAIN}_{webhook_id}", data)

        # Notify the debug sensor of the current diagnostic state.
        async_dispatcher_send(
            hass,
            f"{DOMAIN}_{webhook_id}_debug",
            _build_debug_payload(
                conn_label, conn_mode, diag, raw_history, error_log, now_iso,
                _httpd_port, _ble_enabled,
                _ota_mode, _ota_token_set, _ota_interval_s,
                _led_white_en, _beep_en,
                _ota_meta_url,
                _wifi_ssid_configured,
                _effective_version,
                _obd_en, _can_en, _standby_time_s, _deep_standby,
            ),
        )
        # Notify the CAN debug sensor with the latest CAN state and frames.
        async_dispatcher_send(
            hass,
            f"{DOMAIN}_{webhook_id}_can_debug",
            _build_can_debug_payload(diag, _can_en, now_iso),
        )

    async def _refresh_device_info() -> None:
        """Query the device's /api/info and /api/control endpoints for live state.

        Called at most once per 60 s (rate-limited via diag["_last_info_query_t"])
        when CONF_DEVICE_IP is configured.  Failures are logged at DEBUG level so
        they never disrupt normal telemetry processing.

        Queries:
          - /api/info                    → SD card total/used bytes, fw/nvs_ver
          - /api/control?cmd=SSID?       → WiFi SSID currently in NVS on the device
          - /api/control?cmd=NVS_VER?    → NVS settings version currently in NVS
          - /api/control?cmd=OBD?        → OBD polling enabled state (1/0)
          - /api/control?cmd=CAN?        → CAN sniffing enabled state (1/0)
          - /api/control?cmd=STANDBY_TIME? → standby timeout in seconds
          - /api/control?cmd=CAN_DATA?   → raw CAN frames snapshot (newline-separated)
        """
        url = f"http://{_device_ip}:{_httpd_port}/api/info"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(url) as resp:
                    if resp.status == 200:
                        info = await resp.json(content_type=None)
                        _sd = info.get("sd") or {}
                        total_b = int(_sd.get("total", 0))
                        used_b = int(_sd.get("used", 0))
                        if total_b > 0:
                            total_mb = total_b >> 20  # bytes → MiB
                            used_mb = used_b >> 20
                            diag["sd_present"] = "Ja"
                            diag["sd_storage"] = (
                                f"{total_mb} MB total, {used_mb} MB verwendet"
                            )
                        else:
                            diag["sd_present"] = "Nein"
                            diag["sd_storage"] = "0 MB"
                        # Update the live firmware version from the device report so
                        # the "FW Version" attribute reflects what is actually running.
                        _fw_ver_info = info.get("fw", "")
                        if _fw_ver_info:
                            diag["fw_version"] = _fw_ver_info
                        # NVS settings version (firmware >= PR #147 includes
                        # this in api/info as "nvs_ver").  Absent in older FW.
                        _nvs_ver_info = info.get("nvs_ver", "")
                        if _nvs_ver_info:
                            diag["fw_version_device"] = _nvs_ver_info
                        elif not diag.get("fw_version_device"):
                            # Fall back to showing the firmware binary version +
                            # build date when NVS_VER has never been applied
                            # (e.g. after a serial flash without OTA NVS update).
                            _fw_build_info = info.get("fw_build", "")
                            if _fw_ver_info:
                                diag["fw_version_device"] = (
                                    f"{_fw_ver_info} Built:{_fw_build_info}"
                                    if _fw_build_info
                                    else _fw_ver_info
                                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Freematics /api/info query to %s failed: %s", url, exc)

        # Also query the device's current WiFi SSID from NVS via /api/control.
        # This gives the IST SSID (what the device actually has stored and uses
        # for WiFi connections) so the user can verify it matches the configured
        # value without needing serial access.
        ssid_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=SSID?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(ssid_url) as resp:
                    if resp.status == 200:
                        ssid_raw = (await resp.text()).strip()
                        # Device returns "-" when SSID is not set; older
                        # firmware (without the SSID? handler) returns "ERR"
                        # for unrecognised commands — treat both as unknown.
                        diag["wifi_ssid_device"] = ssid_raw if ssid_raw and ssid_raw not in ("-", "ERR") else ""
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Freematics SSID? query to %s failed: %s", ssid_url, exc)

        # Query the device's NVS settings version via /api/control.
        # Gives the IST NVS version so the user can verify settings are current.
        # Absent in older firmware (returns "ERR") — treated as unknown.
        nvs_ver_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=NVS_VER?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(nvs_ver_url) as resp:
                    if resp.status == 200:
                        nvs_ver_raw = (await resp.text()).strip()
                        # Device returns "-" when NVS was never applied via OTA;
                        # older firmware returns "ERR" — treat both as unknown.
                        if nvs_ver_raw and nvs_ver_raw not in ("-", "ERR"):
                            diag["fw_version_device"] = nvs_ver_raw
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Freematics NVS_VER? query to %s failed: %s", nvs_ver_url, exc)

        # Query live OBD polling state from device NVS (OBD?).
        # "1" = OBD active, "0" = OBD disabled.  "ERR" / "-" = not supported.
        obd_state_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=OBD?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(obd_state_url) as resp:
                    if resp.status == 200:
                        obd_raw = (await resp.text()).strip()
                        if obd_raw and obd_raw not in ("ERR", "-"):
                            diag["obd_state_device"] = obd_raw == "1"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Freematics OBD? query to %s failed: %s", obd_state_url, exc)

        # Query live CAN sniffing state from device NVS (CAN?).
        # "1" = CAN active, "0" = CAN disabled.  "ERR" / "-" = not supported.
        can_state_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=CAN?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(can_state_url) as resp:
                    if resp.status == 200:
                        can_raw = (await resp.text()).strip()
                        if can_raw and can_raw not in ("ERR", "-"):
                            diag["can_state_device"] = can_raw == "1"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Freematics CAN? query to %s failed: %s", can_state_url, exc)

        # Query live standby timeout from device NVS (STANDBY_TIME?).
        # Returns the current standby time in seconds (e.g. "180").
        standby_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=STANDBY_TIME?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(standby_url) as resp:
                    if resp.status == 200:
                        standby_raw = (await resp.text()).strip()
                        if standby_raw and standby_raw not in ("ERR", "-"):
                            try:
                                diag["standby_time_device"] = int(standby_raw)
                            except ValueError:
                                pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Freematics STANDBY_TIME? query to %s failed: %s", standby_url, exc
            )

        # Query live deep-standby state from device NVS (DEEP_STANDBY?).
        # "1" = deep standby enabled, "0" = disabled.  "ERR" / "-" = not supported.
        deep_standby_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=DEEP_STANDBY?"
        try:
            session = async_get_clientsession(hass)
            async with asyncio.timeout(5):
                async with session.get(deep_standby_url) as resp:
                    if resp.status == 200:
                        ds_raw = (await resp.text()).strip()
                        if ds_raw and ds_raw not in ("ERR", "-"):
                            diag["deep_standby_device"] = ds_raw == "1"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Freematics DEEP_STANDBY? query to %s failed: %s", deep_standby_url, exc
            )

        # Query raw CAN frame snapshot from the device (CAN_DATA?).
        # Returns newline-separated CAN frame strings (e.g. "0x123:DE AD BE EF\n...").
        # Only queried when CAN sniffing is configured to be enabled.
        if _can_en:
            can_data_url = f"http://{_device_ip}:{_httpd_port}/api/control?cmd=CAN_DATA?"
            try:
                session = async_get_clientsession(hass)
                async with asyncio.timeout(5):
                    async with session.get(can_data_url) as resp:
                        if resp.status == 200:
                            can_data_raw = (await resp.text()).strip()
                            if can_data_raw and can_data_raw not in ("ERR", "-"):
                                # Split into individual frame strings; trim blank lines.
                                diag["can_frames"] = [
                                    line for line in can_data_raw.splitlines() if line.strip()
                                ]
                            else:
                                diag["can_frames"] = []
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Freematics CAN_DATA? query to %s failed: %s", can_data_url, exc
                )

    async_register(
        hass,
        DOMAIN,
        "Freematics ONE+",
        webhook_id,
        handle_webhook,
        local_only=False,
        # POST is the only method used: the firmware sends telemetry via HTTPS
        # POST to the webhook URL.  OTA firmware updates are WiFi-only and use
        # the dedicated /api/freematics/ota_pull/{token}/ endpoint, not this
        # webhook.  GET is not needed here.
        allowed_methods=["POST"],
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_WEBHOOK_ID: webhook_id,
        "connection_type": conn_label,
        "raw_history": raw_history,
        "error_log": error_log,
        # Mutable diag dict shared with views so OTA events can update sensor state.
        "diag": diag,
        # Initial debug payload so the debug sensor shows known values immediately
        # (e.g. FW version, connection mode, HTTPD/BLE config) before the first
        # webhook arrives.
        "initial_debug": _build_debug_payload(
            conn_label, conn_mode, diag, raw_history, error_log, "",
            _httpd_port, _ble_enabled,
            _ota_mode, _ota_token_set, _ota_interval_s,
            _led_white_en, _beep_en,
            _ota_meta_url,
            _wifi_ssid_configured,
            _effective_version,
            _obd_en, _can_en, _standby_time_s, _deep_standby,
        ),
        # Initial CAN debug payload so FreematicsCanDebugSensor is informative
        # immediately (before any webhook or device query arrives).
        "initial_can_debug": _build_can_debug_payload(diag, _can_en, ""),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the config entry whenever the user saves new options so that the
    # webhook handler closure (which captures _led_white_en, _beep_en and all
    # other config-derived values at setup time) picks up the updated values.
    # Without this, changes made via the Options Flow would not be reflected in
    # the debug entity until the next full HA restart.
    async def _async_reload_on_options_update(
        hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options_update))

    return True


def _build_debug_payload(
    conn_label: str,
    conn_mode: int,
    diag: dict,
    raw_history: deque,
    error_log: deque,
    now_iso: str,
    httpd_port: int = 80,
    ble_enabled: bool = False,
    ota_mode: str = OTA_MODE_DISABLED,
    ota_token_set: bool = False,
    ota_interval_s: int = 0,
    led_white_en: bool = True,
    beep_en: bool = True,
    ota_meta_url: str = "",
    wifi_ssid_configured: str = "",
    fw_version_config: str = "",
    obd_en: bool = True,
    can_en: bool = False,
    standby_time_s: int = DEFAULT_STANDBY_TIME_S,
    deep_standby: bool = DEFAULT_DEEP_STANDBY,
) -> dict:
    """Assemble the debug dispatcher payload from current diagnostic state."""
    _UNK = "Unbekannt"
    _JA = "Ja"
    _NEIN = "Nein"

    def _opt_bool(value) -> str:
        """Convert a bool-or-None diag value to Ja/Nein/Unbekannt."""
        if value is None:
            return _UNK
        return _JA if value else _NEIN

    # SD card presence/storage – populated by _refresh_device_info() when
    # CONF_DEVICE_IP is configured; stays "Unbekannt" otherwise.
    _sd_present = diag.get("sd_present") or _UNK
    _sd_storage = diag.get("sd_storage") or _UNK

    # OTA mode label for display
    _ota_mode_labels = {
        "pull": "Variant 1 (Pull-OTA)",
        "cloud": "Variant 2 (Cloud-OTA)",
        "disabled": "Deaktiviert",
    }
    _ota_mode_label = _ota_mode_labels.get(ota_mode, ota_mode or "Deaktiviert")

    # Standby-time display: show seconds or "Firmware-Standard" when 0.
    _standby_time_conf = (
        f"{standby_time_s} s" if standby_time_s > 0 else "Firmware-Standard (180 s)"
    )
    _standby_time_raw = diag.get("standby_time_device")
    _standby_time_dev = (
        f"{_standby_time_raw} s"
        if _standby_time_raw is not None and _standby_time_raw > 0
        else ("Firmware-Standard (180 s)" if _standby_time_raw == 0 else _UNK)
    )

    return {
        "connection_type": conn_label,
        # Show human-readable connection mode text, not the raw integer.
        "connection_mode": conn_label,
        "connection_errors": diag["conn_errors"],
        "last_wifi_connection": diag["last_wifi_connection"] or _UNK,
        "last_lte_connection": diag["last_lte_connection"] or _UNK,
        "last_packet_time": diag["last_packet_time"] or _UNK,
        # GPS – "configured" is always Ja (GPS is compiled into every firmware build).
        "gps_configured": _JA,
        "gps_active": 1 if diag["gps_active"] else 0,
        "gps_satellites": diag["gps_satellites"] if diag["gps_satellites"] is not None else _UNK,
        "gps_errors": diag["gps_errors"],
        "last_gps_connection": diag["last_gps_connection"] or _UNK,
        # OBD2 – "configured" is always Ja (OBD2 polling is compiled in).
        "obd_configured": _JA,
        "obd_active": 1 if diag["obd_active"] else 0,
        "obd_services": sorted(diag["obd_services_seen"]) if diag["obd_services_seen"] else _UNK,
        "obd_errors": diag["obd_errors"],
        "last_obd_connection": diag["last_obd_connection"] or _UNK,
        # SD card – "configured" is always Ja (SD logging is compiled in).
        # Presence/storage populated by /api/info query when CONF_DEVICE_IP is set.
        "sd_configured": _JA,
        "sd_present": _sd_present,
        "sd_storage": _sd_storage,
        # HTTPD – always enabled in NVS (the firmware starts the HTTP server on every boot).
        "httpd_configured": _JA,
        "httpd_active": _JA,
        "httpd_port": httpd_port,
        "httpd_errors": _UNK,
        # BLE – enabled/disabled via NVS; read from the config entry.
        "ble_configured": _JA if ble_enabled else _NEIN,
        "ble_active": _JA if ble_enabled else _NEIN,
        # WiFi SSID – configured value (from HA config entry / NVS) and live
        # device value (queried via /api/control?cmd=SSID? when device IP is set).
        # "configured" reflects what was last provisioned into NVS; "device"
        # reflects what is currently stored in NVS on the running device.
        # Both stay "Unbekannt" until the relevant data is available.
        # Note: changing the WiFi SSID/password takes effect after the next
        # device reconnect (OTA NVS update or serial re-flash); the device
        # stays on the old WiFi session until the current session ends.
        "wifi_ssid_configured": wifi_ssid_configured or _UNK,
        "wifi_ssid_device": diag.get("wifi_ssid_device") or _UNK,
        # White LED and beep tone – configured via HA options flow; provisioned
        # into device NVS at last flash.  Reflects the desired/provisioned state,
        # not necessarily what the device is currently doing (no runtime feedback
        # is available via webhook for these settings).
        "led_white_configured": _JA if led_white_en else _NEIN,
        "beep_configured": _JA if beep_en else _NEIN,
        # Live device state – reported by the device in its telemetry webhook via
        # PID 0x84 (PID_LED_WHITE_STATE) and 0x85 (PID_BEEP_STATE).
        # Stays "Unbekannt" until the device sends its first telemetry packet.
        "led_white_device": _opt_bool(diag.get("led_white_device")),
        "beep_device": _opt_bool(diag.get("beep_device")),
        # OBD / CAN / standby-time / deep-standby – configured value (from HA config
        # entry) and live device state (from telemetry PID 0x89/0x8a/0x8b/0x8c or
        # device query).
        "obd_enable_configured": _JA if obd_en else _NEIN,
        "obd_state_device": _opt_bool(diag.get("obd_state_device")),
        "can_enable_configured": _JA if can_en else _NEIN,
        "can_state_device": _opt_bool(diag.get("can_state_device")),
        "standby_time_configured": _standby_time_conf,
        "standby_time_device": _standby_time_dev,
        "deep_standby_configured": _JA if deep_standby else _NEIN,
        "deep_standby_device": _opt_bool(diag.get("deep_standby_device")),
        # FW version (config) – the effective version HA expects the device to have.
        # Format: "<FIRMWARE_VERSION>.<settings_timestamp>" (e.g. "5.1.2026-03-17T16:32:29+00:00")
        # or just FIRMWARE_VERSION when no NVS settings version is set.
        # Updated whenever the user changes settings in the options flow.
        "fw_version_configured": fw_version_config or diag.get("fw_version") or _UNK,
        # FW version (device) – NVS settings version string read from the device
        # via /api/control?cmd=NVS_VER? or /api/info (nvs_ver field).
        # Shows what settings timestamp the device's NVS currently contains.
        # "Unbekannt" until the device is queried (requires CONF_DEVICE_IP) or
        # NVS was never applied via OTA (device was only serial-flashed).
        "fw_version_device": diag.get("fw_version_device") or _UNK,
        # Legacy single-value FW version (firmware binary version only).
        "fw_version": diag.get("fw_version") or _UNK,
        # OTA configuration (from HA config entry – reflects what was provisioned
        # into device NVS at last flash).  Shows the user immediately whether OTA
        # is set up correctly without needing to check the serial console.
        "ota_mode": _ota_mode_label,
        "ota_token_set": _JA if ota_token_set else _NEIN,
        "ota_interval_s": ota_interval_s if ota_interval_s > 0 else _UNK,
        # Full meta.json URL that the device uses for OTA checks (incl. token).
        # The host is the Nabu Casa Remote UI URL when available so the device
        # can reach HA from any network (WiFi or LTE).  Useful for manual testing.
        "ota_meta_url": ota_meta_url or _UNK,
        # OTA pull runtime status (updated by FreematicsOtaPullView on OTA events)
        "ota_last_success": diag.get("ota_last_success") or _UNK,
        "ota_last_error": diag.get("ota_last_error") or _UNK,
        "ota_last_version": diag.get("ota_last_version") or _UNK,
        # Raw data for advanced debugging
        "raw_data": list(raw_history),
        "errors": list(error_log),
    }


def _build_can_debug_payload(
    diag: dict,
    can_en: bool,
    now_iso: str,
) -> dict:
    """Assemble the CAN debug dispatcher payload from current diagnostic state."""
    _UNK = "Unbekannt"
    _JA = "Ja"
    _NEIN = "Nein"
    can_state = diag.get("can_state_device")
    return {
        "can_enable_configured": _JA if can_en else _NEIN,
        "can_state_device": (
            _JA if can_state is True else (_NEIN if can_state is False else _UNK)
        ),
        "can_frames": list(diag.get("can_frames") or []),
        "last_update": now_iso or _UNK,
    }

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    async_unregister(hass, webhook_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
