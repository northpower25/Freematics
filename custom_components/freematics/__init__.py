"""The Freematics ONE+ integration.

This integration receives telemetry data pushed directly from the Freematics
ONE+ device via HTTPS webhook.  It is compatible with both locally accessible
Home Assistant instances and the Nabu Casa cloud remote UI
(<id>.ui.nabu.casa) so end-users do not need VPN or port-forwarding.

Firmware configuration (config.h / Kconfig):
  SERVER_PROTOCOL  = PROTOCOL_HA_WEBHOOK (4)
  SERVER_HOST      = <your-ha-host>  (e.g. abc123.ui.nabu.casa)
  SERVER_PORT      = 443
  HA_WEBHOOK_ID    = <webhook-id shown during integration setup>
"""

from __future__ import annotations

import logging

from homeassistant.components.webhook import (
    async_register,
    async_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_WEBHOOK_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freematics ONE+ from a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def handle_webhook(hass, webhook_id, request):
        """Handle incoming telemetry data from the Freematics device."""
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Freematics webhook received non-JSON payload")
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
