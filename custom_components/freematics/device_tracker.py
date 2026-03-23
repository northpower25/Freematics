"""Device tracker platform for Freematics ONE+.

Creates a ``device_tracker.freematics_one_<id8>_standort`` entity that combines
GPS latitude, longitude, altitude, and accuracy into a single tracker entity
compatible with Home Assistant's map card and zone automation.

The tracker entity always derives its position from the GPS sensor entities
``sensor.freematics_one_<id8>_gps_latitude`` and
``sensor.freematics_one_<id8>_gps_longitude``.  It subscribes to state-change
events of those two sensors so that any update to either sensor is immediately
reflected in the tracker, including state restored by ``RestoreEntity`` on
Home Assistant restart.
"""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_WEBHOOK_ID, DEVICE_TRACKER_METADATA, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Freematics device tracker from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    tracker = FreematicsDeviceTracker(webhook_id=webhook_id)
    async_add_entities([tracker])

    @callback
    def handle_data(data: dict) -> None:
        """Forward GPS data to the tracker entity."""
        tracker.update_location(data)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{webhook_id}",
            handle_data,
        )
    )


class FreematicsDeviceTracker(RestoreEntity, TrackerEntity):
    """GPS tracker entity that merges lat/lon/alt from the webhook payload.

    Entity ID: ``device_tracker.freematics_one_<id8>_standort``

    Position is derived from the GPS sensor entities
    ``sensor.freematics_one_<id8>_gps_latitude`` and
    ``sensor.freematics_one_<id8>_gps_longitude``.  The tracker subscribes to
    their state-change events so it is always kept in sync.

    Attributes exposed (visible in the entity detail card):
        source_type  – always "gps"
        latitude     – decimal degrees (°)
        longitude    – decimal degrees (°)
        altitude     – metres above sea level
        gps_accuracy – horizontal accuracy derived from HDOP (0 if unknown)
    """

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(self, webhook_id: str) -> None:
        """Initialise the tracker."""
        device_slug = webhook_id[:8]
        self._webhook_id = webhook_id
        self._attr_name = "Standort"
        self._attr_unique_id = f"freematics_{webhook_id}_standort"
        self._attr_suggested_object_id = f"freematics_one_{device_slug}_standort"
        self._latitude: float | None = None
        self._longitude: float | None = None
        self._altitude: float | None = None
        self._gps_accuracy: int = 0
        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore the last known GPS position after a Home Assistant restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unavailable", "unknown"):
            # No valid last state – try reading from the GPS sensor entities so
            # the tracker is populated immediately rather than staying "unknown".
            self._sync_from_gps_sensors()
        else:
            attrs = last_state.attributes
            try:
                lat = attrs.get("latitude")
                lng = attrs.get("longitude")
                if lat is not None and lng is not None:
                    self._latitude = float(lat)
                    self._longitude = float(lng)
            except (TypeError, ValueError):
                _LOGGER.debug("Could not restore GPS coordinates from last state")
                return
            try:
                alt = attrs.get("altitude")
                if alt is not None:
                    self._altitude = float(alt)
            except (TypeError, ValueError):
                pass
            try:
                acc = attrs.get("gps_accuracy")
                if acc is not None:
                    self._gps_accuracy = max(0, int(acc))
            except (TypeError, ValueError):
                pass

        # Subscribe to state-change events of the GPS sensor entities so that
        # any update to either sensor is immediately reflected here.
        lat_entity_id, lng_entity_id = self._get_gps_sensor_entity_ids()
        tracked = [eid for eid in (lat_entity_id, lng_entity_id) if eid]
        if tracked:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, tracked, self._handle_gps_sensor_state_change
                )
            )

    # ------------------------------------------------------------------
    # GPS sensor helpers
    # ------------------------------------------------------------------

    def _get_gps_sensor_entity_ids(self) -> tuple[str | None, str | None]:
        """Return the entity_ids of the GPS latitude and longitude sensors.

        Looks up by unique_id in the entity registry so the result is correct
        regardless of whether the sensors were registered before or after
        ``_attr_suggested_object_id`` was introduced.
        """
        registry = er.async_get(self.hass)
        lat_entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"freematics_{self._webhook_id}_lat"
        )
        lng_entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"freematics_{self._webhook_id}_lng"
        )
        return lat_entity_id, lng_entity_id

    @callback
    def _sync_from_gps_sensors(self) -> None:
        """Populate lat/lon from the current state of the GPS sensor entities.

        This is called on startup when there is no valid last state to restore
        from, ensuring the tracker shows the last known position stored by the
        GPS sensor entities rather than remaining "unknown".
        """
        lat_entity_id, lng_entity_id = self._get_gps_sensor_entity_ids()
        if lat_entity_id:
            state = self.hass.states.get(lat_entity_id)
            if state and state.state not in ("unavailable", "unknown", ""):
                try:
                    self._latitude = float(state.state)
                except (TypeError, ValueError):
                    pass
        if lng_entity_id:
            state = self.hass.states.get(lng_entity_id)
            if state and state.state not in ("unavailable", "unknown", ""):
                try:
                    self._longitude = float(state.state)
                except (TypeError, ValueError):
                    pass

    @callback
    def _handle_gps_sensor_state_change(self, event: Event) -> None:
        """Handle state-change events from the GPS lat/lng sensor entities."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unavailable", "unknown", ""):
            return
        try:
            value = float(new_state.state)
        except (TypeError, ValueError):
            return

        lat_entity_id, lng_entity_id = self._get_gps_sensor_entity_ids()

        entity_id = event.data.get("entity_id")
        if entity_id == lat_entity_id:
            self._latitude = value
        elif entity_id == lng_entity_id:
            self._longitude = value
        else:
            return

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # TrackerEntity required properties
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the tracker."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return the current latitude."""
        return self._latitude

    @property
    def longitude(self) -> float | None:
        """Return the current longitude."""
        return self._longitude

    @property
    def location_accuracy(self) -> int:
        """Return GPS accuracy in metres (derived from HDOP)."""
        return self._gps_accuracy

    @property
    def extra_state_attributes(self) -> dict:
        """Return altitude, vertical accuracy and entity metadata as extra attributes."""
        attrs: dict = {}
        if self._altitude is not None:
            attrs["altitude"] = self._altitude
        attrs["vertical_accuracy"] = None
        attrs["purpose"] = DEVICE_TRACKER_METADATA["purpose"]
        attrs["data_source"] = DEVICE_TRACKER_METADATA["data_source"]
        attrs["dependencies"] = DEVICE_TRACKER_METADATA["dependencies"]
        attrs["documentation_url"] = DEVICE_TRACKER_METADATA["documentation_url"]
        return attrs

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    @callback
    def update_location(self, data: dict) -> None:
        """Update position from parsed webhook data.

        Only writes state when at least latitude **and** longitude are
        present in the payload – partial updates are ignored to avoid
        publishing a location with only one valid coordinate.
        """
        lat = data.get("lat")
        lng = data.get("lng")
        if lat is None or lng is None:
            return

        try:
            self._latitude = float(lat)
            self._longitude = float(lng)
        except (TypeError, ValueError):
            return

        if "alt" in data:
            try:
                self._altitude = float(data["alt"])
            except (TypeError, ValueError):
                pass

        if "hdop" in data:
            try:
                # HDOP × 5 metres is a rough but practical accuracy estimate.
                self._gps_accuracy = max(0, int(float(data["hdop"]) * 5))
            except (TypeError, ValueError):
                pass

        self.async_write_ha_state()
