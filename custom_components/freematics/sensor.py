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
    debug_sensor = FreematicsDebugSensor(
        webhook_id=webhook_id,
        initial_connection_type=conn_label,
    )
    initial_entities.append(debug_sensor)

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


class FreematicsSensor(SensorEntity):
    """A sensor entity representing a single telemetry data point."""

    _attr_should_poll = False
    # has_entity_name=False: HA does NOT prepend the device name when generating
    # the entity_id, so _attr_suggested_object_id fully controls the entity_id
    # suffix. This is required so the dashboard JS can look up entities using
    # the SENSOR_DEFINITIONS key directly (e.g. prefix + "_battery").
    _attr_has_entity_name = False

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
        """Receive a new value from the webhook handler."""
        try:
            self._attr_native_value = float(value)
        except (TypeError, ValueError):
            self._attr_native_value = value
        self.async_write_ha_state()


class FreematicsDebugSensor(SensorEntity):
    """Debug sensor that exposes connection type and raw webhook history."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_icon = "mdi:bug"

    def __init__(self, webhook_id: str, initial_connection_type: str) -> None:
        """Initialise the debug sensor."""
        device_slug = webhook_id[:8]
        self._webhook_id = webhook_id
        self._attr_name = "Debug"
        self._attr_unique_id = f"freematics_{webhook_id}_debug"
        self._attr_suggested_object_id = f"freematics_{device_slug}_debug"
        self._attr_native_value = initial_connection_type
        self._raw_data: list[str] = []
        self._errors: list[str] = []
        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return raw webhook history and error log as attributes."""
        return {
            "raw_data": self._raw_data,
            "errors": self._errors,
        }

    @callback
    def update_debug(self, debug_data: dict) -> None:
        """Receive updated debug info from the webhook handler."""
        self._attr_native_value = debug_data.get("connection_type", self._attr_native_value)
        self._raw_data = debug_data.get("raw_data", self._raw_data)
        self._errors = debug_data.get("errors", self._errors)
        self.async_write_ha_state()
