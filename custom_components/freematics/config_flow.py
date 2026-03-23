"""Config flow for Freematics ONE+ integration."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.network import get_url

_LOGGER = logging.getLogger(__name__)

from .const import (
    CONF_BEEP_EN,
    CONF_CAN_EN,
    CONF_CELL_APN,
    CONF_CELL_DEBUG,
    CONF_CLOUD_HOOK_URL,
    CONF_CONNECTION_TYPE,
    CONF_DATA_INTERVAL_MS,
    CONF_DEEP_STANDBY,
    CONF_DEVICE_IP,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_PORT,
    CONF_ENABLE_BLE,
    CONF_FLASH_METHOD,
    CONF_LED_RED_EN,
    CONF_LED_WHITE_EN,
    CONF_OBD_EN,
    CONF_OPERATING_MODE,
    CONF_OTA_CHECK_INTERVAL_S,
    CONF_OTA_MODE,
    CONF_OTA_TOKEN,
    CONF_SERIAL_PORT,
    CONF_SETTINGS_VERSION,
    CONF_SIM_PIN,
    CONF_STANDBY_TIME_S,
    CONF_SYNC_INTERVAL_S,
    CONF_VEHICLE_MAKE,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_YEAR_RANGE,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    CONN_TYPE_BOTH,
    CONN_TYPE_CELLULAR,
    CONN_TYPE_WIFI,
    DEFAULT_DATA_INTERVAL_MS,
    DEFAULT_DEEP_STANDBY,
    DEFAULT_DEVICE_PORT,
    DEFAULT_OTA_CHECK_INTERVAL_S,
    DEFAULT_OTA_MODE,
    DEFAULT_OPERATING_MODE,
    DEFAULT_STANDBY_TIME_S,
    DEFAULT_SYNC_INTERVAL_S,
    DEVICE_MODEL_A,
    DEVICE_MODEL_B,
    DEVICE_MODEL_H,
    DOMAIN,
    FLASH_METHOD_SERIAL,
    OPERATING_MODE_DATALOGGER,
    OPERATING_MODE_TELELOGGER,
    OTA_MODE_CLOUD,
    OTA_MODE_DISABLED,
    OTA_MODE_PULL,
)

# Dropdown options for the OTA mode selector.  Defined once here so the same
# labels appear in both the initial config flow (advanced step) and the options
# flow without duplication.
_OTA_MODE_OPTIONS: dict[str, str] = {
    OTA_MODE_DISABLED: "Disabled – no automatic firmware updates",
    OTA_MODE_PULL: "Variant 1 – Pull-OTA: device polls HA; HA always serves latest firmware",
    OTA_MODE_CLOUD: "Variant 2 – Cloud OTA: device polls HA; firmware served only after you press 'Publish'",
}

# Keys whose values are written into the NVS partition flashed to the device.
# When any of these change, the settings_version timestamp is bumped so that
# PULL-OTA knows to re-serve the firmware + NVS to the device.
_NVS_RELEVANT_KEYS = frozenset({
    CONF_WIFI_SSID,
    CONF_WIFI_PASSWORD,
    CONF_CELL_APN,
    CONF_SIM_PIN,
    CONF_ENABLE_BLE,
    CONF_CELL_DEBUG,
    CONF_LED_RED_EN,
    CONF_LED_WHITE_EN,
    CONF_BEEP_EN,
    CONF_OBD_EN,
    CONF_CAN_EN,
    CONF_STANDBY_TIME_S,
    CONF_DEEP_STANDBY,
    CONF_DATA_INTERVAL_MS,
    CONF_SYNC_INTERVAL_S,
    CONF_OTA_MODE,
    CONF_OTA_CHECK_INTERVAL_S,
    CONF_OPERATING_MODE,
    CONF_VEHICLE_MAKE,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_YEAR_RANGE,
})


def _nvs_settings_hash(settings: dict) -> str:
    """Return a short hex digest of the NVS-relevant subset of *settings*.

    Two settings dicts that differ only in keys not listed in
    ``_NVS_RELEVANT_KEYS`` (e.g. device IP, serial port, flash method) will
    produce the same hash, so only genuine NVS changes trigger a version bump.
    """
    subset = {k: settings.get(k) for k in _NVS_RELEVANT_KEYS}
    return hashlib.sha256(
        json.dumps(subset, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


class FreematicsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Freematics ONE+.

    Step order:
      1. user        – choose connection type
      2. wifi        – WiFi credentials (if wifi/both)
      3. cellular    – APN / SIM PIN (if cellular/both)
      4. webhook     – review auto-generated webhook URL / firmware settings
      5. device      – select device model (A / B / H)
      6. vehicle     – select vehicle make / model / year for vehicle-specific PIDs
      7. advanced    – operating mode (Telelogger vs Datalogger), BLE, intervals
      8. flash       – choose flash method and device address
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
            return await self.async_step_vehicle()

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
    # Step 5b – Vehicle selection
    # ------------------------------------------------------------------
    async def async_step_vehicle(self, user_input=None):
        """Select vehicle manufacturer, model and year range for vehicle-specific PIDs."""
        from .vehicle_profiles import get_makes, get_models, get_year_ranges, get_vehicle_pids  # noqa: PLC0415

        if user_input is not None:
            self._data.update(user_input)
            make  = user_input.get(CONF_VEHICLE_MAKE, "")
            model = user_input.get(CONF_VEHICLE_MODEL, "")
            year  = user_input.get(CONF_VEHICLE_YEAR_RANGE, "")
            if make and model and year:
                # Populate vehicle-specific PIDs string so it gets written to NVS
                pids = get_vehicle_pids(make, model, year)
                self._data["vehicle_pids"] = pids
            return await self.async_step_advanced()

        makes = get_makes()
        current_make = self._data.get(CONF_VEHICLE_MAKE, "")
        models = get_models(current_make) if current_make else []
        current_model = self._data.get(CONF_VEHICLE_MODEL, "")
        year_ranges = get_year_ranges(current_make, current_model) if current_make and current_model else []

        make_options: dict[str, str] = {"": "— Not specified —"}
        make_options.update({m: m for m in makes})

        model_options: dict[str, str] = {"": "— Not specified —"}
        model_options.update({m: m for m in models})

        year_options: dict[str, str] = {"": "— Not specified —"}
        year_options.update({y: y for y in year_ranges})

        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_VEHICLE_MAKE,       default=current_make):  vol.In(make_options),
                    vol.Optional(CONF_VEHICLE_MODEL,      default=current_model): vol.In(model_options),
                    vol.Optional(CONF_VEHICLE_YEAR_RANGE, default=""):            vol.In(year_options),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 6 – Advanced firmware settings
    # ------------------------------------------------------------------
    async def async_step_advanced(self, user_input=None):
        """Select operating mode and optional firmware tuning."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Enforce OBD → CAN dependency:
            # CAN bus sniffing requires the OBD stack to be active because the
            # firmware initialises the CAN controller as part of the OBD setup.
            # Reject the invalid combination with a descriptive field-level error
            # so the user knows to enable OBD first before enabling CAN.
            obd_en = user_input.get(CONF_OBD_EN, True)
            can_en = user_input.get(CONF_CAN_EN, False)
            if can_en and not obd_en:
                errors[CONF_CAN_EN] = "can_requires_obd"

            if not errors:
                self._data.update(user_input)
                # Auto-generate a persistent OTA token when the user enables
                # pull-OTA or cloud-OTA, so it is embedded in NVS during the
                # first flash without requiring a separate provisioning step.
                ota_mode = user_input.get(CONF_OTA_MODE, OTA_MODE_DISABLED)
                if ota_mode != OTA_MODE_DISABLED and not self._data.get(CONF_OTA_TOKEN):
                    self._data[CONF_OTA_TOKEN] = secrets.token_hex(32)
                return await self.async_step_flash()

        return self.async_show_form(
            step_id="advanced",
            errors=errors,
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
                    vol.Optional(CONF_LED_RED_EN, default=True): bool,
                    vol.Optional(CONF_LED_WHITE_EN, default=True): bool,
                    vol.Optional(CONF_BEEP_EN, default=True): bool,
                    vol.Optional(CONF_OBD_EN, default=True): bool,
                    vol.Optional(CONF_CAN_EN, default=False): bool,
                    vol.Optional(
                        CONF_STANDBY_TIME_S, default=DEFAULT_STANDBY_TIME_S
                    ): vol.All(int, vol.Range(min=5, max=900)),
                    vol.Optional(
                        CONF_DEEP_STANDBY, default=DEFAULT_DEEP_STANDBY
                    ): bool,
                    vol.Optional(
                        CONF_DATA_INTERVAL_MS, default=DEFAULT_DATA_INTERVAL_MS
                    ): vol.All(int, vol.Range(min=0, max=60000)),
                    vol.Optional(
                        CONF_SYNC_INTERVAL_S, default=DEFAULT_SYNC_INTERVAL_S
                    ): vol.All(int, vol.Range(min=0, max=3600)),
                    vol.Required(
                        CONF_OTA_MODE, default=DEFAULT_OTA_MODE
                    ): vol.In(_OTA_MODE_OPTIONS),
                    vol.Optional(
                        CONF_OTA_CHECK_INTERVAL_S, default=DEFAULT_OTA_CHECK_INTERVAL_S
                    ): vol.All(int, vol.Range(min=0, max=86400)),
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

            # Record the initial settings version so PULL-OTA can detect future
            # changes.  This timestamp represents "settings as of initial flash".
            self._data[CONF_SETTINGS_VERSION] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )

            return self.async_create_entry(
                title="Freematics ONE+",
                data=self._data,
            )

        return self.async_show_form(
            step_id="flash",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FLASH_METHOD, default=FLASH_METHOD_SERIAL): vol.In(
                        {
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
        current = {**self._config_entry.data, **self._config_entry.options}
        errors: dict[str, str] = {}

        if user_input is not None:
            # Enforce OBD → CAN dependency (same rule as in the initial setup flow).
            obd_en = user_input.get(CONF_OBD_EN, True)
            can_en = user_input.get(CONF_CAN_EN, False)
            if can_en and not obd_en:
                errors[CONF_CAN_EN] = "can_requires_obd"

            if not errors:
                # Auto-generate an OTA token when the user enables OTA for the
                # first time (switches away from disabled without a stored token).
                ota_mode = user_input.get(CONF_OTA_MODE, OTA_MODE_DISABLED)
                current_token = (
                    self._config_entry.options.get(CONF_OTA_TOKEN)
                    or self._config_entry.data.get(CONF_OTA_TOKEN, "")
                )
                user_input = dict(user_input)
                if ota_mode != OTA_MODE_DISABLED:
                    if current_token:
                        # Preserve the existing token – the options form does not
                        # have a token field, so user_input never carries it.
                        # Without this the token is silently dropped from
                        # entry.options on every save, breaking pull-OTA.
                        user_input[CONF_OTA_TOKEN] = current_token
                    else:
                        user_input[CONF_OTA_TOKEN] = secrets.token_hex(32)

                # Recalculate vehicle-specific PIDs when vehicle selection changes
                from .vehicle_profiles import get_vehicle_pids  # noqa: PLC0415
                v_make  = user_input.get(CONF_VEHICLE_MAKE, "")
                v_model = user_input.get(CONF_VEHICLE_MODEL, "")
                v_year  = user_input.get(CONF_VEHICLE_YEAR_RANGE, "")
                if v_make and v_model and v_year:
                    user_input["vehicle_pids"] = get_vehicle_pids(v_make, v_model, v_year)

                # Bump settings_version only when NVS-relevant settings actually
                # changed so the device is not triggered to re-flash on every save.
                if _nvs_settings_hash(user_input) != _nvs_settings_hash(current):
                    user_input[CONF_SETTINGS_VERSION] = datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00"
                    )
                else:
                    # Preserve the existing version (no NVS change = no re-flash needed).
                    user_input[CONF_SETTINGS_VERSION] = current.get(CONF_SETTINGS_VERSION, "")

                return self.async_create_entry(title="", data=user_input)

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
            errors=errors,
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
                    vol.Optional(
                        CONF_VEHICLE_MAKE,
                        default=current.get(CONF_VEHICLE_MAKE, ""),
                    ): str,
                    vol.Optional(
                        CONF_VEHICLE_MODEL,
                        default=current.get(CONF_VEHICLE_MODEL, ""),
                    ): str,
                    vol.Optional(
                        CONF_VEHICLE_YEAR_RANGE,
                        default=current.get(CONF_VEHICLE_YEAR_RANGE, ""),
                    ): str,
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
                        CONF_LED_RED_EN,
                        default=current.get(CONF_LED_RED_EN, True),
                    ): bool,
                    vol.Optional(
                        CONF_LED_WHITE_EN,
                        default=current.get(CONF_LED_WHITE_EN, True),
                    ): bool,
                    vol.Optional(
                        CONF_BEEP_EN,
                        default=current.get(CONF_BEEP_EN, True),
                    ): bool,
                    vol.Optional(
                        CONF_OBD_EN,
                        default=current.get(CONF_OBD_EN, True),
                    ): bool,
                    vol.Optional(
                        CONF_CAN_EN,
                        default=current.get(CONF_CAN_EN, False),
                    ): bool,
                    vol.Optional(
                        CONF_STANDBY_TIME_S,
                        default=current.get(CONF_STANDBY_TIME_S, DEFAULT_STANDBY_TIME_S),
                    ): vol.All(int, vol.Range(min=5, max=900)),
                    vol.Optional(
                        CONF_DEEP_STANDBY,
                        default=current.get(CONF_DEEP_STANDBY, DEFAULT_DEEP_STANDBY),
                    ): bool,
                    vol.Optional(
                        CONF_DATA_INTERVAL_MS,
                        default=current.get(CONF_DATA_INTERVAL_MS, DEFAULT_DATA_INTERVAL_MS),
                    ): vol.All(int, vol.Range(min=0, max=60000)),
                    vol.Optional(
                        CONF_SYNC_INTERVAL_S,
                        default=current.get(CONF_SYNC_INTERVAL_S, DEFAULT_SYNC_INTERVAL_S),
                    ): vol.All(int, vol.Range(min=0, max=3600)),
                    vol.Required(
                        CONF_OTA_MODE,
                        default=current.get(CONF_OTA_MODE, DEFAULT_OTA_MODE),
                    ): vol.In(_OTA_MODE_OPTIONS),
                    vol.Optional(
                        CONF_OTA_CHECK_INTERVAL_S,
                        default=current.get(CONF_OTA_CHECK_INTERVAL_S, DEFAULT_OTA_CHECK_INTERVAL_S),
                    ): vol.All(int, vol.Range(min=0, max=86400)),
                    vol.Optional(CONF_DEVICE_IP, default=current.get(CONF_DEVICE_IP, "")): str,
                    vol.Optional(CONF_DEVICE_PORT, default=current.get(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT)): int,
                    vol.Optional(CONF_FLASH_METHOD, default=current.get(CONF_FLASH_METHOD, FLASH_METHOD_SERIAL)): vol.In(
                        {
                            FLASH_METHOD_SERIAL: "Serial USB",
                        }
                    ),
                    vol.Optional(CONF_SERIAL_PORT, default=current.get(CONF_SERIAL_PORT, "")): str,
                }
            ),
        )
