"""Button platform for Freematics ONE+ integration.

Provides the following button entities:
- Flash Firmware via Serial   – triggers esptool serial flash
- Send Config to Device       – pushes stored WiFi/APN settings to running device
- Restart Device              – sends RESET command via device HTTP API
- Publish Firmware for Cloud OTA – copies firmware to /config/www/FreematicsONE/{id}/
                                   (Variant 2: accessible via /local/ NabuCasa path)
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BEEP_EN,
    CONF_CELL_APN,
    CONF_DEVICE_IP,
    CONF_DEVICE_PORT,
    CONF_LED_RED_EN,
    CONF_LED_WHITE_EN,
    CONF_OTA_CHECK_INTERVAL_S,
    CONF_OTA_TOKEN,
    CONF_SERIAL_PORT,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    DEFAULT_DEVICE_PORT,
    DOMAIN,
    FIRMWARE_VERSION,
)
from .flash_manager import (
    CONTROL_PATH,
    FIRMWARE_PATH,
    async_flash_serial,
    async_send_config,
)

_LOGGER = logging.getLogger(__name__)

# Base directory under /config/www where Cloud OTA firmware files are published.
# Each device gets its own sub-directory keyed by the first 8 characters of
# its webhook_id to avoid collisions when multiple devices are registered.
_CLOUD_OTA_WWW_BASE = "FreematicsONE"

# Filenames published into the /local/ directory for Variant 2 Cloud OTA.
_CLOUD_OTA_FIRMWARE_FILENAME = "firmware.bin"
_CLOUD_OTA_VERSION_FILENAME = "version.json"


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
        SendConfigButton(entry, webhook_id),
        RestartDeviceButton(entry, webhook_id),
        PublishCloudOtaButton(entry, webhook_id),
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

        hass: HomeAssistant = self.hass  # type: ignore[attr-defined]

        # Generate an NVS partition from the current config entry using the
        # same full settings as the browser flasher (WiFi, APN, server, webhook,
        # OTA token/host/interval, LED/beep, etc.).  This ensures the device has
        # all necessary NVS keys — including OTA_TOKEN and OTA_INTERVAL — after
        # a serial flash.
        nvs_data: bytes | None = None
        try:
            from .nvs_helper import generate_nvs_partition  # noqa: PLC0415
            from .views import _build_nvs_kwargs  # noqa: PLC0415
            nvs_kwargs = await _build_nvs_kwargs(hass, self._entry)
            nvs_data = generate_nvs_partition(**nvs_kwargs)
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
            # Update the debug sensor so the FW version and OTA last-flash
            # timestamp are immediately visible in Home Assistant.
            await self._record_serial_flash(hass)
        else:
            _LOGGER.error(
                "Freematics serial flash failed: %s  |  "
                "If the device is on your computer's USB port, use the Browser Flasher: "
                "/api/freematics/flasher",
                msg,
            )

    async def _record_serial_flash(self, hass: HomeAssistant) -> None:
        """Update diagnostic state and clean up published OTA files after a serial flash."""
        from datetime import datetime, timezone  # noqa: PLC0415
        import re  # noqa: PLC0415

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        webhook_id = self._webhook_id

        # Update the in-memory diag dict so the debug sensor reflects the flash.
        entry_data = hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        diag = entry_data.get("diag")
        if diag is not None:
            diag["fw_version"] = FIRMWARE_VERSION
            diag["ota_last_success"] = now_iso
            diag["ota_last_version"] = FIRMWARE_VERSION
            diag["ota_last_error"] = None
            async_dispatcher_send(
                hass,
                f"{DOMAIN}_{webhook_id}_debug",
                {
                    "fw_version": FIRMWARE_VERSION,
                    "ota_last_success": now_iso,
                    "ota_last_version": FIRMWARE_VERSION,
                    "ota_last_error": "No error",
                },
            )

        # Mark any published Cloud OTA firmware as no longer available so the
        # device (which now has the latest firmware) does not re-download it on
        # the next OTA check interval.
        device_id = re.sub(r"[^A-Za-z0-9_-]", "", webhook_id[:8])
        if device_id:
            version_json = (
                Path(hass.config.config_dir)
                / "www"
                / _CLOUD_OTA_WWW_BASE
                / device_id
                / _CLOUD_OTA_VERSION_FILENAME
            )

            def _mark_not_available() -> None:
                if not version_json.exists():
                    return
                try:
                    import json  # noqa: PLC0415
                    data = json.loads(version_json.read_text(encoding="utf-8"))
                    data["available"] = False
                    data["flashed_via_serial_at"] = now_iso
                    version_json.write_text(
                        json.dumps(data, indent=2), encoding="utf-8"
                    )
                except OSError:
                    pass

            await hass.async_add_executor_job(_mark_not_available)


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


class PublishCloudOtaButton(_FreematicsButton):
    """Button that publishes the firmware to /config/www/FreematicsONE/{id}/.

    Implements Variant 2 of the Cloud OTA update mechanism: the firmware binary
    and a version.json metadata file are written to the HA www/ directory so
    that the device can fetch them via the NabuCasa Remote URL or any external
    HA URL at the well-known /local/ path:

      https://<ha-external-url>/local/FreematicsONE/<device_id>/version.json
      https://<ha-external-url>/local/FreematicsONE/<device_id>/firmware.bin

    The device stores the OTA check path in NVS (OTA_PATH) and periodically
    polls version.json.  When a newer version is reported it downloads
    firmware.bin and flashes it over-the-air.

    The files are placed under the HA configuration directory:
      <config_dir>/www/FreematicsONE/<device_id>/version.json
      <config_dir>/www/FreematicsONE/<device_id>/firmware.bin
    """

    _attr_name = "Publish Firmware for Cloud OTA"
    _attr_icon = "mdi:cloud-upload"

    def __init__(self, entry: ConfigEntry, webhook_id: str) -> None:
        super().__init__(entry, webhook_id)
        self._attr_unique_id = f"freematics_{webhook_id}_publish_cloud_ota"

    async def async_press(self) -> None:
        """Copy firmware binary and version metadata to /config/www/FreematicsONE/{id}/."""
        from datetime import datetime, timezone  # noqa: PLC0415
        from homeassistant.core import HomeAssistant  # noqa: PLC0415

        # Resolve the HA config directory at runtime via the hass object stored
        # by the button platform during entity registration.  We use self.hass
        # which is set by HA's entity infrastructure before async_press() runs.
        hass: HomeAssistant = self.hass  # type: ignore[attr-defined]
        config_dir = hass.config.config_dir

        device_id = self._webhook_id[:8]
        # Sanitize: keep only alphanumeric, hyphen and underscore characters so
        # the derived path component can never contain ".." or other traversal
        # sequences regardless of how webhook_id was generated.
        import re as _re  # noqa: PLC0415
        device_id = _re.sub(r"[^A-Za-z0-9_-]", "", device_id)
        if not device_id:
            _LOGGER.error("Freematics Cloud OTA: could not derive a safe device ID")
            return
        target_dir = Path(config_dir) / "www" / _CLOUD_OTA_WWW_BASE / device_id

        if not FIRMWARE_PATH.exists():
            _LOGGER.error(
                "Freematics Cloud OTA publish: firmware binary not found at %s",
                FIRMWARE_PATH,
            )
            return

        def _publish() -> tuple[bool, str]:
            """Blocking file I/O – runs in a thread executor."""
            try:
                target_dir.mkdir(parents=True, exist_ok=True)

                fw_data = FIRMWARE_PATH.read_bytes()
                fw_size = len(fw_data)
                fw_sha256 = hashlib.sha256(fw_data).hexdigest()

                # Write firmware binary.
                fw_dest = target_dir / _CLOUD_OTA_FIRMWARE_FILENAME
                fw_dest.write_bytes(fw_data)

                # Each press generates a new publish_id (UTC timestamp) so the
                # OTA endpoint can distinguish this publish from any previous one.
                # This allows the user to force a fresh download by pressing
                # "Publish" again, even when the firmware version hasn't changed
                # (e.g., to re-apply updated NVS settings after a failed download).
                publish_id = (
                    f"{FIRMWARE_VERSION}+"
                    f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
                )

                # Write version metadata with available=true.
                # The Pull-OTA endpoint reads this file to determine whether a
                # new firmware is waiting for download.  "available" stays true;
                # the endpoint uses ota_pull_state.json (keyed by publish_id) to
                # prevent re-download loops without consuming this flag eagerly.
                version_meta = {
                    "available": True,
                    "version": FIRMWARE_VERSION,
                    "publish_id": publish_id,
                    "size": fw_size,
                    "sha256": fw_sha256,
                    # Relative filename within the same /local/ directory.
                    "filename": _CLOUD_OTA_FIRMWARE_FILENAME,
                }
                version_dest = target_dir / _CLOUD_OTA_VERSION_FILENAME
                version_dest.write_text(
                    json.dumps(version_meta, indent=2), encoding="utf-8"
                )

                return True, (
                    f"Published firmware v{FIRMWARE_VERSION} ({fw_size} bytes) "
                    f"to {target_dir} — "
                    f"accessible at /local/{_CLOUD_OTA_WWW_BASE}/{device_id}/"
                )
            except OSError as exc:
                return False, f"Failed to publish firmware: {exc}"

        ok, msg = await hass.async_add_executor_job(_publish)
        if ok:
            _LOGGER.info("Freematics Cloud OTA: %s", msg)

            # Check whether the OTA pull feature is configured on the device.
            ota_token = self._cfg(CONF_OTA_TOKEN, "")
            ota_interval = int(self._cfg(CONF_OTA_CHECK_INTERVAL_S, 0))

            if not ota_token:
                _LOGGER.warning(
                    "Freematics Cloud OTA: firmware published, but the device has no "
                    "OTA token configured (OTA_TOKEN missing from NVS). "
                    "The device cannot check for updates until you re-flash NVS via "
                    "the serial flasher or browser provisioning. "
                    "Set a non-zero OTA check interval in the integration settings first."
                )
            elif ota_interval == 0:
                _LOGGER.warning(
                    "Freematics Cloud OTA: firmware published, but the OTA check "
                    "interval is 0 (disabled). The device will not poll for updates. "
                    "Set a non-zero OTA check interval in Settings → Integrations → "
                    "Freematics ONE+ → Configure, then re-provision the device "
                    "(re-flash NVS) to apply the new interval."
                )
            else:
                _LOGGER.info(
                    "Freematics Cloud OTA: firmware v%s is now available for the device. "
                    "Pull-OTA endpoint: /api/freematics/ota_pull/%s…/meta.json "
                    "(token masked). The device will check every %d seconds.",
                    FIRMWARE_VERSION,
                    ota_token[:8],
                    ota_interval,
                )
        else:
            _LOGGER.error("Freematics Cloud OTA: %s", msg)
