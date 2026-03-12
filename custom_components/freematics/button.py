"""Button platform for Freematics ONE+ integration.

Provides the following button entities:
- Flash Firmware via Serial   – triggers esptool serial flash
- Flash Firmware via WiFi OTA – triggers HTTP OTA upload to device
- Send Config to Device       – pushes stored WiFi/APN settings to running device
- Restart Device              – sends RESET command via device HTTP API
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BEEP_EN,
    CONF_CELL_APN,
    CONF_DEVICE_IP,
    CONF_DEVICE_PORT,
    CONF_FLASH_METHOD,
    CONF_LED_RED_EN,
    CONF_LED_WHITE_EN,
    CONF_SERIAL_PORT,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    DEFAULT_DEVICE_PORT,
    DOMAIN,
    FLASH_METHOD_SERIAL,
    FLASH_METHOD_WIFI,
)
from .flash_manager import (
    CONTROL_PATH,
    async_flash_serial,
    async_flash_wifi,
    async_send_config,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create button entities for the config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    device_id_str = f"freematics_{webhook_id}"

    buttons: list[ButtonEntity] = [
        FlashSerialButton(entry, webhook_id),
        FlashWifiButton(entry, webhook_id),
        SendConfigButton(entry, webhook_id),
        RestartDeviceButton(entry, webhook_id),
    ]
    async_add_entities(buttons)


class _FreematicsButton(ButtonEntity):
    """Base class for Freematics button entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        """Initialise shared attributes."""
        self._entry = entry
        self._webhook_id = webhook_id
        device_slug = webhook_id[:8]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, webhook_id)},
            "name": f"Freematics ONE+ ({device_slug})",
            "manufacturer": "Freematics",
            "model": "ONE+",
        }

    def _cfg(self, key: str, default: Any = None) -> Any:
        """Return a value from data or options, with options taking precedence."""
        return self._entry.options.get(key, self._entry.data.get(key, default))


class FlashSerialButton(_FreematicsButton):
    """Button that flashes the firmware via serial (USB)."""

    _attr_name = "Flash Firmware via Serial"
    _attr_icon = "mdi:usb-flash-drive"

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        super().__init__(entry, webhook_id)
        self._attr_unique_id = f"freematics_{webhook_id}_flash_serial"

    async def async_press(self) -> None:
        """Execute serial flash on the HA server.

        NOTE: This runs esptool on the Home Assistant server and requires the
        Freematics ONE+ to be connected via USB to the HA server itself.
        If your device is connected to the computer running your browser,
        open /api/freematics/flasher for browser-based flashing instead.
        """
        serial_port = self._cfg(CONF_SERIAL_PORT, "")
        if not serial_port:
            _LOGGER.error(
                "Freematics: no serial port configured. "
                "IMPORTANT: This button uses esptool on the Home Assistant server. "
                "If the Freematics ONE+ is connected to your own computer (not the HA server), "
                "use the Browser Flasher instead: /api/freematics/flasher "
                "(requires Chrome or Edge 89+). "
                "To configure the serial port for HA-server flashing: "
                "Settings → Integrations → Freematics ONE+ → Configure"
            )
            return
        _LOGGER.info(
            "Freematics: starting serial flash on %s (running on HA server)",
            serial_port,
        )

        # Generate an NVS partition from the current config entry so that
        # LED/beep/server settings are applied alongside the firmware flash.
        # If NVS generation fails (e.g. esp_idf_nvs_partition_gen not installed),
        # the flash proceeds with firmware-only (NVS settings must be applied
        # separately via the browser flasher or /api/freematics/config_nvs.bin).
        nvs_data: bytes | None = None
        try:
            from .nvs_helper import generate_nvs_partition  # noqa: PLC0415
            cfg = {**self._entry.data, **self._entry.options}
            nvs_data = generate_nvs_partition(
                wifi_ssid=cfg.get(CONF_WIFI_SSID, ""),
                wifi_password=cfg.get(CONF_WIFI_PASSWORD, ""),
                led_red_en=bool(cfg.get(CONF_LED_RED_EN, True)),
                led_white_en=bool(cfg.get(CONF_LED_WHITE_EN, True)),
                beep_en=bool(cfg.get(CONF_BEEP_EN, True)),
                enable_httpd=True,
            )
            if nvs_data:
                _LOGGER.info("Freematics: NVS partition generated (%d bytes)", len(nvs_data))
            else:
                _LOGGER.warning(
                    "Freematics: NVS partition generation returned None "
                    "(esp_idf_nvs_partition_gen not installed?). "
                    "Flashing firmware only; apply NVS settings separately."
                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Freematics: could not generate NVS partition (%s). "
                "Flashing firmware only.",
                exc,
            )

        ok, msg = await async_flash_serial(serial_port, nvs_data=nvs_data)
        if ok:
            _LOGGER.info("Freematics serial flash: %s", msg)
        else:
            _LOGGER.error(
                "Freematics serial flash failed: %s  |  "
                "If the device is on your computer's USB port, use the Browser Flasher: "
                "/api/freematics/flasher",
                msg,
            )


class FlashWifiButton(_FreematicsButton):
    """Button that flashes the firmware via WiFi OTA."""

    _attr_name = "Flash Firmware via WiFi OTA"
    _attr_icon = "mdi:wifi-arrow-up-down"

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        super().__init__(entry, webhook_id)
        self._attr_unique_id = f"freematics_{webhook_id}_flash_wifi"

    async def async_press(self) -> None:
        """Execute WiFi OTA flash."""
        device_ip = self._cfg(CONF_DEVICE_IP, "")
        device_port = self._cfg(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT)
        if not device_ip:
            _LOGGER.error(
                "Freematics: no device IP configured. "
                "Go to Settings → Integrations → Freematics ONE+ → Configure to set it. "
                "If the device is in AP mode, connect to 'TELELOGGER' WiFi and use IP 192.168.4.1."
            )
            return
        _LOGGER.info("Freematics: starting WiFi OTA flash to %s:%s", device_ip, device_port)
        cfg = {**self._entry.data, **self._entry.options}
        # WiFi OTA preserves the NVS partition, so we must NOT actively send
        # LED_RED=1/LED_WHITE=1/BEEP=1 commands.  Doing so would overwrite a
        # user's manually-disabled setting (LED_RED_EN=0 set via /api/control
        # or a previous serial flash) with the HA default (True = on).
        # Only send the "disable" command (=False) when the HA config explicitly
        # disables the setting; leave NVS untouched when the setting is True.
        ok, msg, _log_lines = await async_flash_wifi(
            device_ip,
            device_port,
            led_red_en=None if bool(cfg.get(CONF_LED_RED_EN, True)) else False,
            led_white_en=None if bool(cfg.get(CONF_LED_WHITE_EN, True)) else False,
            beep_en=None if bool(cfg.get(CONF_BEEP_EN, True)) else False,
        )
        if ok:
            _LOGGER.info("Freematics WiFi OTA flash: %s", msg)
        else:
            _LOGGER.error("Freematics WiFi OTA flash failed: %s", msg)


class SendConfigButton(_FreematicsButton):
    """Button that pushes WiFi / APN settings to a running device."""

    _attr_name = "Send Config to Device"
    _attr_icon = "mdi:cog-transfer"

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        super().__init__(entry, webhook_id)
        self._attr_unique_id = f"freematics_{webhook_id}_send_config"

    async def async_press(self) -> None:
        """Push stored config to device via /api/control."""
        device_ip = self._cfg(CONF_DEVICE_IP, "")
        device_port = self._cfg(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT)
        if not device_ip:
            _LOGGER.error(
                "Freematics: no device IP configured for config push. "
                "Set the device IP in the integration options."
            )
            return

        cfg = {}
        if self._cfg(CONF_WIFI_SSID):
            cfg["wifi_ssid"] = self._cfg(CONF_WIFI_SSID)
        if self._cfg(CONF_WIFI_PASSWORD):
            cfg["wifi_password"] = self._cfg(CONF_WIFI_PASSWORD)
        if self._cfg(CONF_CELL_APN):
            cfg["cell_apn"] = self._cfg(CONF_CELL_APN)

        if not cfg:
            _LOGGER.warning("Freematics: no config values to send.")
            return

        _LOGGER.info("Freematics: sending config to %s:%s", device_ip, device_port)
        ok, results = await async_send_config(device_ip, device_port, cfg)
        for line in results:
            if ok:
                _LOGGER.info("Freematics config push: %s", line)
            else:
                _LOGGER.error("Freematics config push error: %s", line)


class RestartDeviceButton(_FreematicsButton):
    """Button that sends a RESET command to the device."""

    _attr_name = "Restart Device"
    _attr_icon = "mdi:restart"

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        super().__init__(entry, webhook_id)
        self._attr_unique_id = f"freematics_{webhook_id}_restart"

    async def async_press(self) -> None:
        """Send RESET command to device via /api/control."""
        device_ip = self._cfg(CONF_DEVICE_IP, "")
        device_port = self._cfg(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT)
        if not device_ip:
            _LOGGER.error(
                "Freematics: no device IP configured. "
                "Set the device IP in the integration options."
            )
            return

        try:
            import aiohttp  # noqa: PLC0415
            url = f"http://{device_ip}:{device_port}{CONTROL_PATH}?cmd=RESET"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    _LOGGER.info("Freematics restart sent, HTTP %s", resp.status)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Freematics restart command error (device may have restarted): %s", exc)
