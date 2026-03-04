"""Device tracker platform for Freematics ONE+.

Creates a ``device_tracker.freematics_<id8>_standort`` entity that combines
GPS latitude, longitude, altitude, and accuracy into a single tracker entity
compatible with Home Assistant's map card and zone automation.
"""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_WEBHOOK_ID, DOMAIN

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


class FreematicsDeviceTracker(TrackerEntity):
    """GPS tracker entity that merges lat/lon/alt from the webhook payload.

    Entity ID: ``device_tracker.freematics_<id8>_standort``

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
        self._attr_suggested_object_id = f"freematics_{device_slug}_standort"
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
        """Return altitude and vertical accuracy as extra attributes."""
        attrs: dict = {}
        if self._altitude is not None:
            attrs["altitude"] = self._altitude
        attrs["vertical_accuracy"] = None
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
