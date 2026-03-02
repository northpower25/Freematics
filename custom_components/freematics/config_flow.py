"""Config flow for Freematics ONE+ integration."""

from __future__ import annotations

import secrets

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.helpers.network import get_url

from .const import CONF_WEBHOOK_ID, DOMAIN


class FreematicsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freematics ONE+."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            webhook_id = user_input.get(CONF_WEBHOOK_ID) or secrets.token_hex(16)
            await self.async_set_unique_id(webhook_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Freematics ONE+",
                data={CONF_WEBHOOK_ID: webhook_id},
            )

        # Generate a suggested webhook ID so the user can copy it directly
        suggested_id = secrets.token_hex(16)

        # Show HA base URL hint so user can configure the firmware
        try:
            base_url = get_url(self.hass, prefer_external=True)
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            ha_host = parsed.netloc or base_url
        except Exception:  # noqa: BLE001
            base_url = "https://homeassistant.local:8123"
            ha_host = "homeassistant.local:8123"

        description_placeholders = {
            "webhook_url": f"{base_url}/api/webhook/{suggested_id}",
            "ha_host": ha_host,
            "suggested_id": suggested_id,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WEBHOOK_ID, default=suggested_id): str,
                }
            ),
            description_placeholders=description_placeholders,
        )
