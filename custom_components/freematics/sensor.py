"""Sensor platform for Freematics ONE+ integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_WEBHOOK_ID, DOMAIN, SENSOR_DEFINITIONS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Freematics sensor entities from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    conn_label = entry_data.get("connection_type", "WiFi")

    # Pre-create one sensor for every key in SENSOR_DEFINITIONS so all
    # potential entities are visible in HA immediately after setup – even
    # before the first webhook packet arrives.  Entities whose data has not
    # yet been received will show as "unavailable" until updated.
    sensors: dict[str, FreematicsSensor] = {}
    initial_entities: list[SensorEntity] = []
    for key in SENSOR_DEFINITIONS:
        sensor_uid = f"{webhook_id}_{key}"
        sensor = FreematicsSensor(
            webhook_id=webhook_id,
            key=key,
        )
        sensors[sensor_uid] = sensor
        initial_entities.append(sensor)

    # Debug sensor – shows connection type as state; raw webhook history and
    # error log as attributes.
    initial_debug = entry_data.get("initial_debug", {})
    debug_sensor = FreematicsDebugSensor(
        webhook_id=webhook_id,
        initial_connection_type=conn_label,
        initial_debug=initial_debug,
    )
    initial_entities.append(debug_sensor)

    # CAN Bus Debug sensor – shows CAN active state; raw CAN frames as attributes.
    initial_can_debug = entry_data.get("initial_can_debug", {})
    can_debug_sensor = FreematicsCanDebugSensor(
        webhook_id=webhook_id,
        initial_can_debug=initial_can_debug,
    )
    initial_entities.append(can_debug_sensor)

    async_add_entities(initial_entities)

    @callback
    def handle_data(data: dict) -> None:
        """Process incoming webhook data and update sensors."""
        for key, value in data.items():
            if key not in SENSOR_DEFINITIONS:
                _LOGGER.debug("Unknown telemetry key '%s' - skipping", key)
                continue

            sensor_uid = f"{webhook_id}_{key}"
            if sensor_uid in sensors:
                sensors[sensor_uid].update_state(value)

    @callback
    def handle_debug(debug_data: dict) -> None:
        """Forward debug / history data to the debug sensor."""
        debug_sensor.update_debug(debug_data)

    @callback
    def handle_can_debug(can_data: dict) -> None:
        """Forward CAN debug data to the CAN debug sensor."""
        can_debug_sensor.update_can_data(can_data)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{webhook_id}",
            handle_data,
        )
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{webhook_id}_debug",
            handle_debug,
        )
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{webhook_id}_can_debug",
            handle_can_debug,
        )
    )


class FreematicsSensor(RestoreEntity, SensorEntity):
    """A sensor entity representing a single telemetry data point."""

    _attr_should_poll = False
    # has_entity_name=True: HA prepends the device name when displaying the
    # entity, producing e.g. "Freematics ONE+ (b1af617d) Speed" instead of
    # just "Speed".  This makes it easy to identify which device each sensor
    # belongs to, especially when multiple Freematics ONE+ devices are
    # managed in the same Home Assistant instance.
    # _attr_suggested_object_id still controls the entity_id, so the entity
    # IDs (e.g. sensor.freematics_b1af617d_speed) are not affected and the
    # dashboard JS discovery pattern continues to work unchanged.
    _attr_has_entity_name = True

    def __init__(self, webhook_id: str, key: str) -> None:
        """Initialise the sensor."""
        name, unit, device_class, state_class = SENSOR_DEFINITIONS[key]

        device_slug = webhook_id[:8]
        self._webhook_id = webhook_id
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"freematics_{webhook_id}_{key}"
        # Suggest an entity_id of the form sensor.freematics_<id8>_<key>
        # (e.g. sensor.freematics_b1af617d_battery).  The JS dashboard
        # discovers devices by scanning for *_speed entities and then reads
        # all other sensors as prefix + "_" + key. _attr_suggested_object_id
        # is the hint HA uses when generating the entity_id for new entities;
        # once stored in the entity registry the registry value takes precedence.
        self._attr_suggested_object_id = f"freematics_{device_slug}_{key}"

        if device_class:
            try:
                self._attr_device_class = SensorDeviceClass(device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        if state_class:
            try:
                self._attr_state_class = SensorStateClass(state_class)
            except ValueError:
                self._attr_state_class = None
        else:
            self._attr_state_class = None

        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

    @callback
    def update_state(self, value) -> None:
        """Receive a new value from the webhook handler.

        Empty / None values are ignored so the last persisted state is
        preserved rather than being overwritten with nothing.
        """
        if value is None or value == "":
            return
        try:
            self._attr_native_value = float(value)
        except (TypeError, ValueError):
            self._attr_native_value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value after a Home Assistant restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            "unavailable",
            "unknown",
            None,
        ):
            try:
                self._attr_native_value = float(last_state.state)
            except (TypeError, ValueError):
                self._attr_native_value = last_state.state


class FreematicsDebugSensor(SensorEntity):
    """Debug sensor that exposes detailed device diagnostics as attributes.

    The state value shows the active connection type (WiFi / LTE).  All
    diagnostic fields that cannot be determined from the webhook payload alone
    are initialised to "Unbekannt" (unknown) and remain so until the device
    sends data that allows them to be inferred.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:bug"

    _UNK = "Unbekannt"

    def __init__(
        self,
        webhook_id: str,
        initial_connection_type: str,
        initial_debug: dict | None = None,
    ) -> None:
        """Initialise the debug sensor."""
        device_slug = webhook_id[:8]
        self._webhook_id = webhook_id
        self._attr_name = "Debug"
        self._attr_unique_id = f"freematics_{webhook_id}_debug"
        self._attr_suggested_object_id = f"freematics_{device_slug}_debug"
        self._attr_native_value = initial_connection_type
        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

        # Initialise all diagnostic attributes to "Unbekannt".
        _u = self._UNK
        self._debug: dict = {
            # Firmware binary version (e.g. "5.1")
            "fw_version": _u,
            # Target NVS version HA expects on device: "<fw>.<settings_ts>" or just "<fw>"
            "fw_version_configured": _u,
            # Actual NVS version on the device (from NVS_VER key via api/info or NVS_VER? cmd)
            "fw_version_device": _u,
            "connection_mode": _u,
            "connection_errors": 0,
            "last_wifi_connection": _u,
            "last_lte_connection": _u,
            "last_packet_time": _u,
            "gps_configured": _u,
            "gps_active": _u,
            "gps_satellites": _u,
            "gps_errors": 0,
            "last_gps_connection": _u,
            "obd_configured": _u,
            "obd_active": _u,
            "obd_services": _u,
            "obd_errors": 0,
            "last_obd_connection": _u,
            "sd_configured": _u,
            "sd_present": _u,
            "sd_storage": _u,
            "httpd_configured": _u,
            "httpd_active": _u,
            "httpd_port": _u,
            "httpd_errors": _u,
            "ble_configured": _u,
            "ble_active": _u,
            # White LED and beep tone (configured via HA options flow)
            "led_white_configured": _u,
            "beep_configured": _u,
            # White LED and beep tone live device state (reported by firmware via PID 0x84/0x85)
            "led_white_device": _u,
            "beep_device": _u,
            # OBD / CAN / standby – Konfig (from HA config entry) and IST (from device PIDs)
            "obd_enable_configured": _u,
            "obd_state_device": _u,
            "can_enable_configured": _u,
            "can_state_device": _u,
            "standby_time_configured": _u,
            "standby_time_device": _u,
            # WiFi SSID – configured value (from HA setup/config flow) and live
            # device value (queried via /api/control?cmd=SSID? when device IP is set).
            "wifi_ssid_configured": _u,
            "wifi_ssid_device": _u,
            # OTA configuration (from HA config entry)
            "ota_mode": _u,
            "ota_token_set": _u,
            "ota_interval_s": _u,
            # Full OTA meta.json URL the device uses (incl. token) – debug only
            "ota_meta_url": _u,
            # OTA pull status – updated by FreematicsOtaPullView after each OTA event
            "ota_last_success": _u,   # ISO timestamp of last successful OTA flash
            "ota_last_error": _u,     # Error message from the last failed OTA attempt
            "ota_last_version": _u,   # Firmware version applied in the last OTA flash
            "raw_data": [],
            "errors": [],
        }

        # Apply known-at-setup values so the sensor is informative even before
        # the first webhook arrives (e.g. FW version, connection mode, HTTPD/BLE).
        if initial_debug:
            for key in self._debug:
                if key in initial_debug:
                    self._debug[key] = initial_debug[key]

    @property
    def extra_state_attributes(self) -> dict:
        """Return all diagnostic attributes."""
        d = self._debug
        return {
            # Firmware
            "FW Version": d["fw_version"],
            "NVS Version (Konfig)": d["fw_version_configured"],
            "NVS Version (IST)": d["fw_version_device"],
            # Connection
            "Verbindungsmodus": d["connection_mode"],
            "Verbindungsfehler": d["connection_errors"],
            "WiFi letzte Verbindung": d["last_wifi_connection"],
            "LTE letzte Verbindung": d["last_lte_connection"],
            "Letztes Paket": d["last_packet_time"],
            # WiFi SSID – what is configured in HA and what the device currently has
            "WiFi SSID (Konfig)": d["wifi_ssid_configured"],
            "WiFi SSID (IST)": d["wifi_ssid_device"],
            # GPS
            "GPS eingestellt": d["gps_configured"],
            "GPS aktiv": d["gps_active"],
            "GPS Anzahl Satelliten": d["gps_satellites"],
            "GPS Anzahl Fehler": d["gps_errors"],
            "GPS letzte Verbindung": d["last_gps_connection"],
            # OBD2
            "OBD2 Verbindung eingestellt": d["obd_configured"],
            "OBD2 aktiv": d["obd_active"],
            "OBD2 Dienste": d["obd_services"],
            "OBD2 Anzahl Fehler": d["obd_errors"],
            "OBD2 letzte Verbindung": d["last_obd_connection"],
            # SD card
            "SD Karte eingestellt": d["sd_configured"],
            "SD Karte vorhanden": d["sd_present"],
            "SD Speicherplatz": d["sd_storage"],
            # HTTPD
            "HTTPD eingestellt": d["httpd_configured"],
            "HTTPD aktiv": d["httpd_active"],
            "HTTPD PORT": d["httpd_port"],
            "HTTPD Anzahl Fehler": d["httpd_errors"],
            # BLE
            "BLE eingestellt": d["ble_configured"],
            "BLE aktiv": d["ble_active"],
            # White LED and beep tone – what was provisioned into device NVS.
            "Weiße LED (Konfig)": d["led_white_configured"],
            "Beep Ton (Konfig)": d["beep_configured"],
            # White LED and beep tone – live device state reported via telemetry webhook.
            # "Unbekannt" until the device sends its first telemetry packet with PID 0x84/0x85.
            "Weiße LED (IST)": d["led_white_device"],
            "Beep Ton (IST)": d["beep_device"],
            # OBD / CAN / standby-time – configured value and live device state
            "OBD aktiviert (Konfig)": d["obd_enable_configured"],
            "OBD aktiviert (IST)": d["obd_state_device"],
            "CAN aktiviert (Konfig)": d["can_enable_configured"],
            "CAN aktiviert (IST)": d["can_state_device"],
            "Standby Zeit (Konfig)": d["standby_time_configured"],
            "Standby Zeit (IST)": d["standby_time_device"],
            # OTA configuration (from HA config entry – what was provisioned at last flash)
            "OTA Modus": d["ota_mode"],
            "OTA Token gesetzt": d["ota_token_set"],
            "OTA Prüfintervall (s)": d["ota_interval_s"],
            # Full meta.json URL used by the device for OTA checks (incl. token).
            # Paste this into a browser to manually verify the OTA endpoint.
            "OTA Meta URL": d["ota_meta_url"],
            # OTA pull update status
            # Records firmware transmission time, not confirmed device application
            # (device may still fail SD write after HA serves the binary).
            "OTA letzte Übertragung": d["ota_last_success"],
            "OTA letzter Fehler": d["ota_last_error"],
            "OTA letzte Version": d["ota_last_version"],
            # Raw debug data
            "raw_data": d["raw_data"],
            "errors": d["errors"],
        }

    @callback
    def update_debug(self, debug_data: dict) -> None:
        """Receive updated debug info from the webhook handler."""
        conn_type = debug_data.get("connection_type")
        if conn_type:
            self._attr_native_value = conn_type

        # Merge all incoming fields into the stored debug dict.
        for key in self._debug:
            if key in debug_data:
                self._debug[key] = debug_data[key]

        self.async_write_ha_state()


class FreematicsCanDebugSensor(SensorEntity):
    """Dedicated CAN Bus Debug sensor.

    Exposes the live CAN bus state and a snapshot of raw CAN frames captured by
    the device.  The entity state reflects whether CAN sniffing is currently
    active on the device; the attributes contain the last known raw frame data
    queried via ``/api/control?cmd=CAN_DATA?`` and the configured / device
    CAN enable states.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:can-bus"

    _UNK = "Unbekannt"

    def __init__(
        self,
        webhook_id: str,
        initial_can_debug: dict | None = None,
    ) -> None:
        """Initialise the CAN debug sensor."""
        device_slug = webhook_id[:8]
        self._webhook_id = webhook_id
        self._attr_name = "CAN Debug"
        self._attr_unique_id = f"freematics_{webhook_id}_can_debug"
        self._attr_suggested_object_id = f"freematics_{device_slug}_can_debug"
        self._attr_native_value = self._UNK
        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

        _u = self._UNK
        self._can_data: dict = {
            # Whether CAN sniffing is enabled in the HA config entry (NVS provisioned).
            "can_enable_configured": _u,
            # Live device CAN state (from PID 0x8a or CAN? query).
            "can_state_device": _u,
            # Raw CAN frames from CAN_DATA? device query (list of strings).
            "can_frames": [],
            # ISO timestamp of the last CAN data update.
            "last_update": _u,
        }

        # Apply initial values provided at setup time.
        if initial_can_debug:
            for key in self._can_data:
                if key in initial_can_debug:
                    self._can_data[key] = initial_can_debug[key]
            # Set initial state from configured CAN enable flag.
            self._attr_native_value = initial_can_debug.get(
                "can_state_device", self._UNK
            )

    @property
    def extra_state_attributes(self) -> dict:
        """Return CAN bus diagnostic attributes."""
        d = self._can_data
        return {
            "CAN aktiviert (Konfig)": d["can_enable_configured"],
            "CAN Zustand (IST)": d["can_state_device"],
            "CAN Frames (letzter Abruf)": d["can_frames"],
            "Letzte Aktualisierung": d["last_update"],
        }

    @callback
    def update_can_data(self, can_data: dict) -> None:
        """Receive updated CAN debug info from the webhook handler or device query."""
        # Merge all incoming fields into the stored CAN data dict.
        for key in self._can_data:
            if key in can_data:
                self._can_data[key] = can_data[key]

        # Update entity state to reflect the live CAN device state.
        self._attr_native_value = self._can_data.get("can_state_device", self._UNK)
        self.async_write_ha_state()

