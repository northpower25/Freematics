"""Config flow for Freematics ONE+ integration."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.network import get_url

_LOGGER = logging.getLogger(__name__)

from .const import (
    CONF_CELL_APN,
    CONF_CELL_DEBUG,
    CONF_CLOUD_HOOK_URL,
    CONF_CONNECTION_TYPE,
    CONF_DATA_INTERVAL_MS,
    CONF_DEVICE_IP,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_PORT,
    CONF_ENABLE_BLE,
    CONF_FLASH_METHOD,
    CONF_OPERATING_MODE,
    CONF_SERIAL_PORT,
    CONF_SIM_PIN,
    CONF_SYNC_INTERVAL_S,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    CONN_TYPE_BOTH,
    CONN_TYPE_CELLULAR,
    CONN_TYPE_WIFI,
    DEFAULT_DATA_INTERVAL_MS,
    DEFAULT_DEVICE_PORT,
    DEFAULT_OPERATING_MODE,
    DEFAULT_SYNC_INTERVAL_S,
    DEVICE_MODEL_A,
    DEVICE_MODEL_B,
    DEVICE_MODEL_H,
    DOMAIN,
    FLASH_METHOD_SERIAL,
    FLASH_METHOD_WIFI,
    OPERATING_MODE_DATALOGGER,
    OPERATING_MODE_TELELOGGER,
)


class FreematicsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freematics ONE+.

    Step order:
      1. user        – choose connection type
      2. wifi        – WiFi credentials (if wifi/both)
      3. cellular    – APN / SIM PIN (if cellular/both)
      4. webhook     – review auto-generated webhook URL / firmware settings
      5. device      – select device model (A / B / H)
      6. advanced    – operating mode (Telelogger vs Datalogger), BLE, intervals
      7. flash       – choose flash method and device address
    """

    VERSION = 2

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
            return await self.async_step_device()

        # Resolve the correct webhook URL.
        # When HA Cloud (Nabu Casa) is active, the dedicated Cloud Webhook
        # endpoint (hooks.nabu.casa) must be used instead of the Remote UI URL
        # (*.ui.nabu.casa).  The Remote UI is a browser-only proxy; IoT devices
        # cannot POST directly to it.  hooks.nabu.casa is the publicly-reachable
        # HTTPS webhook endpoint intended for machine-to-machine requests.
        webhook_url = None
        try:
            from homeassistant.components import cloud  # noqa: PLC0415
            if cloud.async_is_logged_in(self.hass):
                cloud_hook_url = await cloud.async_create_cloudhook(
                    self.hass, self._webhook_id
                )
                webhook_url = cloud_hook_url
                # Persist the cloud hook URL in entry.data so NVS provisioning
                # can use it even when Nabu Casa cloud is temporarily offline.
                self._data[CONF_CLOUD_HOOK_URL] = cloud_hook_url
                parsed = urlparse(cloud_hook_url)
                self._ha_host = parsed.netloc or cloud_hook_url
                self._base_url = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Freematics: could not create Nabu Casa cloud webhook "
                "(cloud not connected or no active subscription); "
                "falling back to the HA external URL",
                exc_info=True,
            )

        if webhook_url is None:
            # No cloud or cloud check failed – use the HA external URL.
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
    # Step 5 – Device model
    # ------------------------------------------------------------------
    async def async_step_device(self, user_input=None):
        """Select the Freematics ONE+ hardware model."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_MODEL, default=DEVICE_MODEL_A): vol.In(
                        {
                            DEVICE_MODEL_A: "Model A – WiFi + Bluetooth (no cellular)",
                            DEVICE_MODEL_B: "Model B – WiFi + Bluetooth + 4G cellular",
                            DEVICE_MODEL_H: "Model H – WiFi only (no BT/cellular)",
                        }
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 6 – Advanced firmware settings
    # ------------------------------------------------------------------
    async def async_step_advanced(self, user_input=None):
        """Select operating mode and optional firmware tuning."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_flash()

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OPERATING_MODE, default=DEFAULT_OPERATING_MODE
                    ): vol.In(
                        {
                            OPERATING_MODE_TELELOGGER: "Telelogger – Webhook → Home Assistant (recommended)",
                            OPERATING_MODE_DATALOGGER: "Datalogger – Local HTTP API (HTTPD on port 80)",
                        }
                    ),
                    vol.Optional(CONF_ENABLE_BLE, default=False): bool,
                    vol.Optional(CONF_CELL_DEBUG, default=False): bool,
                    vol.Optional(
                        CONF_DATA_INTERVAL_MS, default=DEFAULT_DATA_INTERVAL_MS
                    ): vol.All(int, vol.Range(min=0, max=60000)),
                    vol.Optional(
                        CONF_SYNC_INTERVAL_S, default=DEFAULT_SYNC_INTERVAL_S
                    ): vol.All(int, vol.Range(min=0, max=3600)),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 7 – Flash method
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

        # Derive current operating mode with backwards-compat fallback.
        # Entries created before the operating_mode field was added have an
        # enable_httpd boolean instead; infer the mode from that.
        # CONF_ENABLE_HTTPD is imported locally (not at module level) because it
        # is only needed for this legacy fallback path and should not be used in
        # new config-flow steps.
        stored_mode = current.get(CONF_OPERATING_MODE)
        if stored_mode is None:
            from .const import CONF_ENABLE_HTTPD  # noqa: PLC0415 – legacy compat only
            stored_mode = (
                OPERATING_MODE_DATALOGGER
                if current.get(CONF_ENABLE_HTTPD, False)
                else OPERATING_MODE_TELELOGGER
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WIFI_SSID, default=current.get(CONF_WIFI_SSID, "")): str,
                    vol.Optional(CONF_WIFI_PASSWORD, default=current.get(CONF_WIFI_PASSWORD, "")): str,
                    vol.Optional(CONF_CELL_APN, default=current.get(CONF_CELL_APN, "")): str,
                    vol.Optional(CONF_SIM_PIN, default=current.get(CONF_SIM_PIN, "")): str,
                    vol.Optional(
                        CONF_DEVICE_MODEL,
                        default=current.get(CONF_DEVICE_MODEL, DEVICE_MODEL_A),
                    ): vol.In(
                        {
                            DEVICE_MODEL_A: "Model A – WiFi + Bluetooth",
                            DEVICE_MODEL_B: "Model B – WiFi + Bluetooth + 4G cellular",
                            DEVICE_MODEL_H: "Model H – WiFi only",
                        }
                    ),
                    vol.Required(
                        CONF_OPERATING_MODE,
                        default=stored_mode,
                    ): vol.In(
                        {
                            OPERATING_MODE_TELELOGGER: "Telelogger – Webhook → Home Assistant (recommended)",
                            OPERATING_MODE_DATALOGGER: "Datalogger – Local HTTP API (HTTPD on port 80)",
                        }
                    ),
                    vol.Optional(
                        CONF_ENABLE_BLE,
                        default=current.get(CONF_ENABLE_BLE, False),
                    ): bool,
                    vol.Optional(
                        CONF_CELL_DEBUG,
                        default=current.get(CONF_CELL_DEBUG, False),
                    ): bool,
                    vol.Optional(
                        CONF_DATA_INTERVAL_MS,
                        default=current.get(CONF_DATA_INTERVAL_MS, DEFAULT_DATA_INTERVAL_MS),
                    ): vol.All(int, vol.Range(min=0, max=60000)),
                    vol.Optional(
                        CONF_SYNC_INTERVAL_S,
                        default=current.get(CONF_SYNC_INTERVAL_S, DEFAULT_SYNC_INTERVAL_S),
                    ): vol.All(int, vol.Range(min=0, max=3600)),
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
