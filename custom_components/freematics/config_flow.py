"""Config flow for Freematics ONE+ integration."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.network import get_url

from .const import (
    CONF_CELL_APN,
    CONF_CONNECTION_TYPE,
    CONF_DEVICE_IP,
    CONF_DEVICE_PORT,
    CONF_FLASH_METHOD,
    CONF_SERIAL_PORT,
    CONF_SIM_PIN,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    CONN_TYPE_BOTH,
    CONN_TYPE_CELLULAR,
    CONN_TYPE_WIFI,
    DEFAULT_DEVICE_PORT,
    DOMAIN,
    FLASH_METHOD_SERIAL,
    FLASH_METHOD_WIFI,
)


class FreematicsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freematics ONE+.

    Step order:
      1. user        – choose connection type
      2. wifi        – WiFi credentials (if wifi/both)
      3. cellular    – APN / SIM PIN (if cellular/both)
      4. webhook     – review auto-generated webhook URL / firmware settings
      5. flash       – choose flash method and device address
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._data: dict = {}
        self._webhook_id: str = secrets.token_hex(16)
        self._ha_host: str = ""
        self._base_url: str = ""

    # ------------------------------------------------------------------
    # Step 1 – connection type
    # ------------------------------------------------------------------
    async def async_step_user(self, user_input=None):
        """First step: choose how the device connects to the internet."""
        if user_input is not None:
            self._data.update(user_input)
            conn = user_input[CONF_CONNECTION_TYPE]
            if conn in (CONN_TYPE_WIFI, CONN_TYPE_BOTH):
                return await self.async_step_wifi()
            return await self.async_step_cellular()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_TYPE, default=CONN_TYPE_WIFI): vol.In(
                        {
                            CONN_TYPE_WIFI: "WiFi only",
                            CONN_TYPE_CELLULAR: "Cellular / SIM only",
                            CONN_TYPE_BOTH: "WiFi + Cellular fallback",
                        }
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 2 – WiFi credentials
    # ------------------------------------------------------------------
    async def async_step_wifi(self, user_input=None):
        """WiFi credentials step."""
        if user_input is not None:
            self._data.update(user_input)
            conn = self._data[CONF_CONNECTION_TYPE]
            if conn == CONN_TYPE_BOTH:
                return await self.async_step_cellular()
            return await self.async_step_webhook()

        return self.async_show_form(
            step_id="wifi",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WIFI_SSID): str,
                    vol.Required(CONF_WIFI_PASSWORD): str,
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 3 – Cellular / APN
    # ------------------------------------------------------------------
    async def async_step_cellular(self, user_input=None):
        """Cellular / APN step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_webhook()

        return self.async_show_form(
            step_id="cellular",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CELL_APN, default=""): str,
                    vol.Optional(CONF_SIM_PIN, default=""): str,
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 4 – Webhook / firmware settings review
    # ------------------------------------------------------------------
    async def async_step_webhook(self, user_input=None):
        """Generate and display webhook URL / firmware configuration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_flash()

        # Webhook ID is generated once in __init__; resolve HA base URL here
        try:
            self._base_url = get_url(self.hass, prefer_external=True)
            parsed = urlparse(self._base_url)
            self._ha_host = parsed.netloc or self._base_url
        except Exception:  # noqa: BLE001
            self._base_url = "https://homeassistant.local:8123"
            self._ha_host = "homeassistant.local:8123"

        webhook_url = f"{self._base_url}/api/webhook/{self._webhook_id}"

        return self.async_show_form(
            step_id="webhook",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WEBHOOK_ID, default=self._webhook_id): str,
                }
            ),
            description_placeholders={
                "webhook_url": webhook_url,
                "ha_host": self._ha_host,
                "webhook_id": self._webhook_id,
            },
        )

    # ------------------------------------------------------------------
    # Step 5 – Flash method
    # ------------------------------------------------------------------
    async def async_step_flash(self, user_input=None):
        """Choose flash method: serial USB or WiFi OTA."""
        if user_input is not None:
            self._data.update(user_input)

            # Finalise webhook id (user may have edited it in step 4)
            webhook_id = self._data.get(CONF_WEBHOOK_ID) or self._webhook_id
            self._data[CONF_WEBHOOK_ID] = webhook_id

            await self.async_set_unique_id(webhook_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Freematics ONE+",
                data=self._data,
            )

        return self.async_show_form(
            step_id="flash",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FLASH_METHOD, default=FLASH_METHOD_WIFI): vol.In(
                        {
                            FLASH_METHOD_WIFI: "WiFi OTA (device on same network / AP mode)",
                            FLASH_METHOD_SERIAL: "Serial USB (device connected to HA host)",
                        }
                    ),
                    vol.Optional(CONF_DEVICE_IP, default=""): str,
                    vol.Optional(CONF_DEVICE_PORT, default=DEFAULT_DEVICE_PORT): int,
                    vol.Optional(CONF_SERIAL_PORT, default=""): str,
                }
            ),
            description_placeholders={
                "ap_ssid": "TELELOGGER",
                "ap_password": "PASSWORD",
                "flasher_url": f"{self._base_url}/api/freematics/flasher",
            },
        )

    # ------------------------------------------------------------------
    # Options flow (re-configure without removing integration)
    # ------------------------------------------------------------------
    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return FreematicsOptionsFlow(config_entry)


class FreematicsOptionsFlow(config_entries.OptionsFlow):
    """Allow the user to update connection / flash settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store entry for later use."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WIFI_SSID, default=current.get(CONF_WIFI_SSID, "")): str,
                    vol.Optional(CONF_WIFI_PASSWORD, default=current.get(CONF_WIFI_PASSWORD, "")): str,
                    vol.Optional(CONF_CELL_APN, default=current.get(CONF_CELL_APN, "")): str,
                    vol.Optional(CONF_DEVICE_IP, default=current.get(CONF_DEVICE_IP, "")): str,
                    vol.Optional(CONF_DEVICE_PORT, default=current.get(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT)): int,
                    vol.Optional(CONF_FLASH_METHOD, default=current.get(CONF_FLASH_METHOD, FLASH_METHOD_WIFI)): vol.In(
                        {
                            FLASH_METHOD_WIFI: "WiFi OTA",
                            FLASH_METHOD_SERIAL: "Serial USB",
                        }
                    ),
                    vol.Optional(CONF_SERIAL_PORT, default=current.get(CONF_SERIAL_PORT, "")): str,
                }
            ),
        )
