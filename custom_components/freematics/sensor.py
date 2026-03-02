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

    sensors: dict[str, FreematicsSensor] = {}

    @callback
    def handle_data(data: dict) -> None:
        """Process incoming webhook data and update / create sensors."""
        new_entities = []
        device_id = data.get("device_id", "unknown")

        for key, value in data.items():
            if key in ("device_id", "ts", "gps_time"):
                # Skip non-sensor fields
                continue
            if key not in SENSOR_DEFINITIONS:
                _LOGGER.debug("Unknown telemetry key '%s' – skipping", key)
                continue

            sensor_uid = f"{webhook_id}_{key}"
            if sensor_uid not in sensors:
                sensor = FreematicsSensor(
                    webhook_id=webhook_id,
                    device_id=device_id,
                    key=key,
                )
                sensors[sensor_uid] = sensor
                new_entities.append(sensor)

            sensors[sensor_uid].update_state(value)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{webhook_id}",
            handle_data,
        )
    )


class FreematicsSensor(SensorEntity):
    """A sensor entity representing a single telemetry data point."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, webhook_id: str, device_id: str, key: str) -> None:
        """Initialise the sensor."""
        name, unit, device_class, state_class = SENSOR_DEFINITIONS[key]

        self._webhook_id = webhook_id
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"freematics_{webhook_id}_{key}"

        # Map device class string to enum (or None)
        if device_class:
            try:
                self._attr_device_class = SensorDeviceClass(device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        # Map state class string to enum (or None)
        if state_class:
            try:
                self._attr_state_class = SensorStateClass(state_class)
            except ValueError:
                self._attr_state_class = None
        else:
            self._attr_state_class = None

        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_id})",
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
