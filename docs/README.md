# Freematics ONE+ Home Assistant Integration

A HACS-compatible Home Assistant integration for the **Freematics ONE+** OBD-II telematics device. The device pushes real-time vehicle telemetry data (speed, RPM, GPS, engine sensors, etc.) directly to Home Assistant via a secure HTTPS webhook — no VPN, port forwarding, or public IP required (works with Nabu Casa too).

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation via HACS](#installation-via-hacs)
3. [Integration Setup (Config Flow)](#integration-setup-config-flow)
4. [When Are Settings Applied to the Device?](#when-are-settings-applied-to-the-device)
5. [Firmware Flashing](#firmware-flashing)
   - [Which method should I choose?](#which-method-should-i-choose)
   - [Method A: WiFi OTA (Recommended)](#method-a-wifi-ota-recommended)
   - [Method B: Browser Serial (Web Serial API)](#method-b-browser-serial-web-serial-api)
   - [Method C: Serial USB via HA Server](#method-c-serial-usb-via-ha-server)
6. [Sending Configuration to a Running Device](#sending-configuration-to-a-running-device)
7. [Lovelace Dashboard & Card](#lovelace-dashboard--card)
8. [Updating the Firmware](#updating-the-firmware)
9. [Changing Settings After Initial Setup](#changing-settings-after-initial-setup)
10. [Entities Reference](#entities-reference)
11. [Troubleshooting](#troubleshooting)
12. [Technical Background](#technical-background)

---

## Requirements

- **Home Assistant** 2023.1 or newer
- **HACS** installed ([see HACS docs](https://hacs.xyz/docs/setup/download))
- Freematics ONE+ Model A or Model B
- WiFi network, SIM card, or both for device internet connectivity
- (Optional) USB cable to flash the device from the HA host

---

## Installation via HACS

1. Open Home Assistant and navigate to **HACS** → **Integrations**
2. Click the **⋮ (three dots)** menu → **Custom repositories**
3. Add the repository URL:
   ```
   https://github.com/northpower25/Freematics
   ```
   Category: **Integration**
4. Click **Add**
5. Search for **Freematics ONE+** in HACS and click **Download**
6. **Restart Home Assistant** (Settings → System → Restart)

> **Note:** After restarting, the integration will be available to configure.

---

## Integration Setup (Config Flow)

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Freematics ONE+** and click it
3. Follow the 5-step wizard:

### Step 1 – Connection Type

Choose how your device connects to the internet:

| Option | Description |
|---|---|
| **WiFi only** | Device uses a WiFi network (hotspot, home router) |
| **Cellular / SIM only** | Device uses a mobile SIM card |
| **WiFi + Cellular fallback** | WiFi preferred; cellular used when WiFi unavailable |

### Step 2 – WiFi Credentials *(shown for WiFi/Both)*

Enter the **SSID** and **Password** of the WiFi network the device should connect to.

> This can be a mobile hotspot on your phone.

### Step 3 – Cellular / SIM *(shown for Cellular/Both)*

- **APN**: Your mobile provider's APN (e.g. `internet`, `data.t-mobile.com`). Leave empty to use the provider default.
- **SIM PIN**: Only required if your SIM card has a PIN lock.

### Step 4 – Webhook / Firmware Settings

A unique webhook ID is auto-generated. **Copy these values** — you will need them when flashing:

| Firmware Setting | Value |
|---|---|
| `SERVER_PROTOCOL` | `4` (PROTOCOL_HA_WEBHOOK) |
| `SERVER_HOST` | Shown in the setup form |
| `SERVER_PORT` | `443` |
| `HA_WEBHOOK_ID` | Shown in the setup form |

You can edit the Webhook ID if you want a custom value, or leave the auto-generated one.

### Step 5 – Flash Method

Choose how to flash the firmware:

| Method | Description |
|---|---|
| **WiFi OTA** | Upload firmware over WiFi to a device on the network or in AP mode |
| **Serial USB** | Flash via USB cable connected to the HA host |

- **Device IP**: IP address of the running device (or `192.168.4.1` for AP mode)
- **Device HTTP port**: Usually `80`
- **Serial port**: e.g. `/dev/ttyUSB0` or `/dev/ttyACM0` (Linux), `COM3` (Windows)

Click **Submit** to finish setup. The integration is now configured. Use the **Flash Firmware** buttons to start the flash process.

---

## When Are Settings Applied to the Device?

> **Short answer:** Settings are stored in Home Assistant first. They are only written to the device when you flash the firmware.

### Settings lifecycle

```
Config Flow / Options Flow
        │
        ▼
 HA config entry       ← settings live here (HA persistent storage)
 (SSID, password,
  APN, webhook ID,
  server host …)
        │
        │  on every flash request, HA generates:
        ▼
 flash_image.bin       ← combined file built on-demand from current settings
 (NVS partition        ← your WiFi / server / webhook data, freshly embedded
  + firmware binary)
        │
        ▼
  Device flash         ← settings take effect after the device reboots
```

### Key points

1. **Saving the Config Flow or Options Flow alone does NOT update the device.**  
   Clicking *Submit* / *Save* only stores the values in Home Assistant's database. The physical device is untouched until you flash it.

2. **Settings are baked into `flash_image.bin` at download time.**  
   Every time you open the Freematics panel and the download link becomes active, the integration generates a fresh `flash_image.bin` from the *current* settings. If you change a setting and then re-download and re-flash, the device will boot with the new values.

3. **The firmware binary itself never changes between flashes.**  
   Only the settings portion (NVS partition, offset `0x9000`) is regenerated. The application firmware at offset `0x10000` is always the version bundled with the current integration release.

4. **Exception – push WiFi/APN without re-flashing.**  
   If the device is already running firmware with `ENABLE_HTTPD=1`, you can push WiFi SSID, WiFi password, and APN via the **Send Config to Device** button without flashing. Settings are written to the device's NVS over HTTP and take effect after a restart. See [Sending Configuration to a Running Device](#sending-configuration-to-a-running-device).

---

## Firmware Flashing

> **Architecture note:** In a typical setup, Home Assistant runs on a dedicated server (e.g. Raspberry Pi, NAS, or a VM), while you access the HA frontend from your regular computer's browser. The Freematics ONE+ is connected via USB to **your computer**, not to the HA server. This is important when choosing a flash method.

### Which method should I choose?

| Situation | Recommended method |
|---|---|
| Device in your car / at your desk, HA on a server | [Method A: WiFi OTA](#method-a-wifi-ota-recommended) ✅ |
| Device connected via USB to your computer (browser machine) | [Method B: Browser Serial](#method-b-browser-serial-web-serial-api) ✅ |
| HA runs on the same machine as your browser | [Method C: Serial USB via HA Server](#method-c-serial-usb-via-ha-server) |

---

### Method A: WiFi OTA (Recommended)

This method connects to the device over WiFi and uploads the firmware binary. **Works regardless of where HA is hosted.**

**Step 1: Prepare the device**

Option 1 – *AP mode (factory device or device without WiFi config)*:
1. Power on the Freematics ONE+
2. The device starts in AP mode broadcasting SSID **`TELELOGGER`** (password: `PASSWORD`)
3. Connect your computer or phone to this WiFi network
4. The device IP is `192.168.4.1`

Option 2 – *Device on local network*:
1. Find the device IP from your router's DHCP table
2. Make sure the device is running firmware with `ENABLE_HTTPD=1`

**Step 2: Set device IP in integration**

1. Go to **Settings → Integrations → Freematics ONE+ → Configure**
2. Enter the device IP (e.g. `192.168.4.1`)
3. Click **Submit**

**Step 3: Flash**

1. Navigate to **Settings → Integrations → Freematics ONE+**
2. Click on the integration's devices/entities
3. Find **Flash Firmware via WiFi OTA** button and press it
4. Check **Home Assistant logs** (Settings → System → Logs) for progress

> The firmware binary is bundled with the integration at `custom_components/freematics/firmware/telelogger.bin`.

---

### Method B: Browser Serial (Web Serial API)

This method flashes directly from your **browser** to the device connected to **your computer's USB port**. No software installation required.

**Requirements:**
- Google Chrome or Microsoft Edge (version 89 or newer)
- USB cable between the Freematics ONE+ and your computer
- USB-Serial driver installed on your computer:
  - [CP210x driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) (Silicon Labs)
  - [CH340 driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html) (WCH)

**Steps:**

1. Connect the Freematics ONE+ to your computer via USB
2. Open the **Browser Flasher** in your browser:  
   `http://<your-ha-address>/api/freematics/flasher`  
   *(replace `<your-ha-address>` with your HA URL, e.g. `http://homeassistant.local:8123`)*
3. Click **Connect & Flash Firmware**
4. Select the correct serial port from the browser dialog  
   *(look for: `CP2102`, `CH340`, or a similar USB-Serial chip name)*
5. The firmware flashes automatically (~30 s) and the device restarts

> **Port identification:**
> - **Windows**: Open Device Manager → Ports (COM & LPT) — the device appears as `Silicon Labs CP210x USB to UART Bridge (COM3)` or similar
> - **macOS**: Look for `/dev/tty.usbserial-*` or `/dev/tty.SLAB_USBtoUART` in a terminal
> - **Linux**: Look for `/dev/ttyUSB0` or `/dev/ttyACM0` (`dmesg | tail` after plugging in)

---

### Method C: Serial USB via HA Server

This method uses `esptool` running on the **Home Assistant server** via the **Flash Firmware via Serial** button.

> ⚠️ **This only works if the Freematics ONE+ is physically connected via USB to the machine running Home Assistant.** If your HA runs on a separate server, use [Method A (WiFi OTA)](#method-a-wifi-ota-recommended) or [Method B (Browser Serial)](#method-b-browser-serial-web-serial-api) instead.

> **`esptool` is automatically installed** when you install this integration via HACS. No separate installation is required.

**Requirements:**
- USB cable between the Freematics ONE+ and the HA host machine
- Correct serial port permissions (Linux: `sudo usermod -aG dialout homeassistant`)

**Steps:**

1. Connect the Freematics ONE+ to the HA host via USB
2. Find the serial port: `dmesg | tail` or `ls /dev/ttyUSB*` on the HA host
3. Set the serial port in integration settings: **Settings → Integrations → Freematics ONE+ → Configure**
4. Press **Flash Firmware via Serial USB** button
5. Check logs for progress

**Manual flash command** (if the button fails):
```bash
python3 -m esptool --chip esp32 --port /dev/ttyUSB0 --baud 921600 \
  write-flash --flash_mode dio --flash_size detect \
  0x10000 custom_components/freematics/firmware/telelogger.bin
```

---

## Sending Configuration to a Running Device

If the device is already running firmware with `ENABLE_HTTPD=1`, you can push WiFi/APN settings without re-flashing:

1. Make sure the device is on the same network as HA and its IP is set in integration settings
2. Press the **Send Config to Device** button
3. Check logs for the result

This sends commands to the device's `/api/control` HTTP endpoint:
- `SSID=<wifi_ssid>` — updates WiFi SSID
- `WPWD=<wifi_password>` — updates WiFi password
- `APN=<cell_apn>` — updates cellular APN

Settings are written to the device's NVS (non-volatile storage) and take effect after restarting.

You can also **Restart Device** using the corresponding button, which sends the `RESET` command.

---

## Lovelace Dashboard & Card

### Using the Pre-built Dashboard

1. Copy `lovelace/freematics-dashboard.yaml` from this repository
2. In Home Assistant go to **Settings → Dashboards → Add Dashboard**
3. Select **YAML mode** and paste the contents (or use the Import from file option)
4. Replace `WEBHOOK_ID_SHORT` with the first 8 characters of your webhook ID

### Using the Custom Lovelace Card

The integration includes a custom Lovelace card (`freematics-vehicle-card.js`) that is automatically registered.

Add it to any dashboard:

```yaml
type: custom:freematics-vehicle-card
title: My Car
entity_prefix: sensor.freematics_one_WEBHOOK_ID_SHORT
```

The card displays:
- Live speed (large, color-coded)
- RPM, engine load, throttle, coolant temperature (with progress bars)
- Fuel pressure, GPS satellites, accelerometer data
- Battery voltage with status indicator
- GPS location with OpenStreetMap link
- Signal strength

---

## Updating the Firmware

When a new version of this integration is released:

1. Open **HACS → Integrations → Freematics ONE+**
2. Click **Update** (the new firmware binary is included)
3. After the update, **restart Home Assistant**
4. Press the **Flash Firmware** button (WiFi OTA or Serial, using your already-saved settings)

> Your device settings (WiFi credentials, webhook ID, etc.) are preserved in Home Assistant and will be re-applied automatically during the next flash.

---

## Changing Settings After Initial Setup

If you need to update your WiFi credentials, APN, or any other setting after the initial setup, follow these steps:

### Step 1 – Update the settings in Home Assistant

1. Go to **Settings → Devices & Services → Freematics ONE+**
2. Click **Configure** (the ⚙ icon or the "Configure" link next to the integration)
3. Edit the fields you want to change (WiFi SSID, password, APN, device IP, flash method, etc.)
4. Click **Submit** — the new values are now saved in Home Assistant

> **Nothing has changed on the device yet.** The physical device still uses the old settings until you flash it.

### Step 2 – Apply the new settings to the device

Choose the method that suits your situation:

#### Option A – Re-flash (recommended, applies all settings)

Open the **Freematics panel** (sidebar → *Freematics ONE+*) and flash using the Browser Flash or Manual Flash method. The panel always generates `flash_image.bin` from the *current* integration settings, so the newly saved values will be baked in automatically.

- **Browser Flash (Chrome/Edge):** the panel will use the updated manifest automatically — just click the flash button again.
- **Manual flash (esptool / Freematics Builder):** click the download link in the panel again to get a freshly generated `flash_image.bin`, then flash at offset `0x9000` as usual.

#### Option B – Push WiFi/APN without re-flashing (running device only)

If the device is already running and reachable on the network, and the firmware was compiled with `ENABLE_HTTPD=1`:

1. Make sure the device IP is entered in the integration settings
2. Press the **Send Config to Device** button
3. The new WiFi SSID, WiFi password, and APN are written to the device's NVS over HTTP
4. Restart the device (use the **Restart Device** button, or unplug and re-plug the OBD connector)

> ⚠️ This method only updates WiFi and APN. **Server host, webhook path, and port are not updated this way** — for those, a full re-flash is required.

---

## Entities Reference

### Sensor Entities

| Entity | Description | Unit |
|---|---|---|
| `sensor.…_speed` | Vehicle speed (OBD) | km/h |
| `sensor.…_rpm` | Engine RPM | rpm |
| `sensor.…_throttle` | Throttle position | % |
| `sensor.…_engine_load` | Engine load | % |
| `sensor.…_coolant_temp` | Coolant temperature | °C |
| `sensor.…_intake_temp` | Intake air temperature | °C |
| `sensor.…_fuel_pressure` | Fuel pressure | kPa |
| `sensor.…_timing_advance` | Ignition timing advance | ° |
| `sensor.…_lat` | GPS latitude | ° |
| `sensor.…_lng` | GPS longitude | ° |
| `sensor.…_alt` | GPS altitude | m |
| `sensor.…_gps_speed` | GPS speed | km/h |
| `sensor.…_heading` | GPS heading | ° |
| `sensor.…_satellites` | GPS satellite count | — |
| `sensor.…_hdop` | GPS HDOP | — |
| `sensor.…_acc_x` | Accelerometer X | m/s² |
| `sensor.…_acc_y` | Accelerometer Y | m/s² |
| `sensor.…_acc_z` | Accelerometer Z | m/s² |
| `sensor.…_battery` | Battery voltage | V |
| `sensor.…_signal` | Signal strength | dBm |
| `sensor.…_device_temp` | Device temperature | °C |

### Button Entities

| Entity | Description |
|---|---|
| `button.…_flash_firmware_via_serial` | Flash firmware via USB serial |
| `button.…_flash_firmware_via_wifi_ota` | Flash firmware via WiFi OTA |
| `button.…_send_config_to_device` | Push WiFi/APN config to device |
| `button.…_restart_device` | Restart the device |

---

## Troubleshooting

### No sensor data arriving

- Check that the device is powered on and connected to the internet
- Verify the `HA_WEBHOOK_ID` in the firmware matches the webhook ID in the integration
- Verify `SERVER_HOST` in the firmware matches your HA host (use external URL for cloud access)
- Check HA logs for webhook errors
- Verify `SERVER_PROTOCOL = 4` (PROTOCOL_HA_WEBHOOK) in the firmware

### WiFi OTA flash fails

- Ensure the device is reachable at the configured IP
- If using AP mode, ensure your computer is connected to the `TELELOGGER` WiFi network
- Check that `ENABLE_HTTPD=1` is set in the firmware
- Try pinging the device IP
- Check HA logs for error details
- If you see **"Connection reset by peer"**: the device restarted while receiving the firmware (normal after a successful flash). Verify the device rebooted with new firmware by checking its serial output or waiting for it to reconnect to HA.

### Serial flash fails

**Browser Flasher (Method B — Web Serial in Chrome/Edge):**
- Use Chrome or Edge 89+ — Firefox does not support Web Serial API
- Install the USB-Serial driver for your device (CP210x or CH340)
- Try a different USB port or cable
- The Web Serial API requires a **trusted HTTPS connection**; it will not work over plain HTTP on a local IP. Use Nabu Casa or a self-signed cert setup, or use the Manual Flash Fallback (esptool) method below.
- If the progress bar stays stuck with no messages after selecting the COM port, the browser may have failed to connect silently. Try the Manual Flash Fallback method below.

**Serial via HA Server (Method C):**
- Verify the device is connected to the HA server, not your own computer
- Check the serial port path (`dmesg | tail` after plugging in USB on the HA host)
- Ensure correct permissions: `sudo chmod 666 /dev/ttyUSB0`
- Try reducing baud rate (edit `flash_manager.py` to use `115200`)
- `esptool` is automatically installed by this integration. If it's still missing, run: `pip install esptool`

### Manual Flash Fallback (esptool)

If all automated methods fail, you can flash the firmware manually from **your own computer** using `esptool`.

**Step 1 – Install Python**

Download and install Python from [https://www.python.org/downloads/](https://www.python.org/downloads/).

> **Windows**: During installation, check **"Add Python to PATH"** so that `python` is available in the Command Prompt.

**Step 2 – Install esptool**

Open a terminal (Windows: Command Prompt or PowerShell) and run:

```bash
pip install esptool
```

**Step 3 – Download `flash_image.bin`**

Open the **Freematics panel** in Home Assistant (sidebar → *Freematics ONE+*) and download the `flash_image.bin` link. This file contains your NVS settings and the firmware merged into a single binary, ready to flash at offset `0x9000`.

**Step 4 – Find the COM port**

- **Windows**: Open *Device Manager → Ports (COM & LPT)* — the device appears as `Silicon Labs CP210x USB to UART Bridge (COM3)` or `USB-Serial CH340 (COM4)`.
- **Linux**: `dmesg | tail` after plugging in USB — look for `/dev/ttyUSB0` or `/dev/ttyACM0`.
- **macOS**: `ls /dev/tty.usbserial*` or `ls /dev/tty.SLAB_USBtoUART*`.

**Step 5 – Flash**

```bash
python -m esptool --chip esp32 --port COM3 --baud 921600 write-flash 0x9000 flash_image.bin
```

*(Replace `COM3` with your port, e.g. `/dev/ttyUSB0` on Linux/macOS)*

> **Note:** Both `write-flash` (hyphen) and `write_flash` (underscore) are accepted by esptool. On Windows, always use `python -m esptool` instead of `esptool.py` directly.

After flashing the device will reboot and connect to WiFi using the credentials baked into `flash_image.bin`.

**Alternative: PlatformIO / VS Code**

If you prefer an IDE workflow:
1. Install [Visual Studio Code](https://code.visualstudio.com/) and the [PlatformIO IDE extension](https://platformio.org/install/ide?install=vscode).
2. Open the folder `firmware_v5/telelogger/` in VS Code.
3. Configure your settings in `config.h` (WiFi credentials, webhook ID, etc.).
4. Click **Upload** (the arrow icon in the PlatformIO toolbar) — PlatformIO will compile and flash automatically.

### Device not connecting to WiFi

- Double-check SSID and password (case-sensitive)
- Use **Send Config to Device** to update credentials without re-flashing
- Or re-flash with the correct credentials

---

## Technical Background

### Data Flow

```
Freematics ONE+  ──HTTPS POST──►  HA Webhook  ──dispatcher──►  Sensor entities
     (ESP32)          (WiFi/Cell)    /api/webhook/<id>              (auto-created)
```

### Firmware Protocol

The integration uses `PROTOCOL_HA_WEBHOOK` (value `4`) which POSTs JSON telemetry to the HA webhook endpoint:

```json
{
  "device_id": "ABCD1234",
  "ts": 12345,
  "speed": 75,
  "rpm": 1500,
  "lat": 48.8566,
  "lng": 2.3522,
  "battery": 12.50,
  "signal": -75
}
```

### OTA Flash Architecture

The integration bundles `telelogger.bin` (the pre-compiled firmware). When you press **Flash Firmware via WiFi OTA**, the integration:
1. Reads the firmware binary
2. POSTs it as multipart form data to `http://<device_ip>/api/ota`
3. The device's HTTP server writes the firmware and restarts

For Serial flashing, `esptool.py` is invoked as a subprocess with the bundled binary.

---

## License

BSD License — see the main repository [LICENSE](../LICENSE) file.

---

*Built on top of [PR #1](https://github.com/northpower25/Freematics/pull/1) which added the HA webhook protocol to the Freematics firmware.*

---

# Freematics ONE+ Home Assistant Integration (Deutsch)

Eine HACS-kompatible Home Assistant Integration für das **Freematics ONE+** OBD-II Telematik-Gerät. Das Gerät sendet Echtzeit-Fahrzeugdaten (Geschwindigkeit, Drehzahl, GPS, Motorsensoren usw.) direkt an Home Assistant über einen sicheren HTTPS-Webhook — ohne VPN, Port-Weiterleitung oder öffentliche IP-Adresse (funktioniert auch mit Nabu Casa).

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Installation über HACS](#installation-über-hacs)
3. [Integration einrichten (Config Flow)](#integration-einrichten-config-flow)
4. [Wann werden die Einstellungen auf das Gerät übertragen?](#wann-werden-die-einstellungen-auf-das-gerät-übertragen)
5. [Firmware flashen](#firmware-flashen)
6. [Konfiguration an laufendes Gerät senden](#konfiguration-an-laufendes-gerät-senden)
7. [Lovelace Dashboard & Karte](#lovelace-dashboard--karte)
8. [Firmware aktualisieren](#firmware-aktualisieren)
9. [Einstellungen nach der Ersteinrichtung ändern](#einstellungen-nach-der-ersteinrichtung-ändern)
10. [Entitäten-Übersicht](#entitäten-übersicht)
11. [Fehlerbehebung](#fehlerbehebung)

---

## Voraussetzungen

- **Home Assistant** 2023.1 oder neuer
- **HACS** installiert ([HACS-Dokumentation](https://hacs.xyz/docs/setup/download))
- Freematics ONE+ Modell A oder Modell B
- WLAN-Netzwerk, SIM-Karte oder beides für die Internet-Konnektivität des Geräts
- (Optional) USB-Kabel zum Flashen des Geräts vom HA-Host

---

## Installation über HACS

1. Öffnen Sie Home Assistant und navigieren Sie zu **HACS** → **Integrationen**
2. Klicken Sie auf das **⋮ (Drei-Punkte)**-Menü → **Benutzerdefinierte Repositories**
3. Fügen Sie die Repository-URL hinzu:
   ```
   https://github.com/northpower25/Freematics
   ```
   Kategorie: **Integration**
4. Klicken Sie auf **Hinzufügen**
5. Suchen Sie nach **Freematics ONE+** in HACS und klicken Sie auf **Herunterladen**
6. **Starten Sie Home Assistant neu** (Einstellungen → System → Neustart)

---

## Integration einrichten (Config Flow)

1. Gehen Sie zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suchen Sie nach **Freematics ONE+** und klicken Sie darauf
3. Folgen Sie dem 5-stufigen Assistenten:

### Schritt 1 – Verbindungsart

Wählen Sie aus, wie Ihr Gerät mit dem Internet verbunden wird:
- **Nur WLAN**: Das Gerät nutzt ein WLAN-Netzwerk
- **Nur Mobilfunk/SIM**: Das Gerät nutzt eine SIM-Karte
- **WLAN + Mobilfunk-Fallback**: WLAN bevorzugt; Mobilfunk als Fallback

### Schritt 2 – WLAN-Zugangsdaten

Geben Sie **SSID** und **Passwort** des WLAN-Netzwerks ein.

### Schritt 3 – Mobilfunk/SIM

- **APN**: Der APN Ihres Mobilfunkanbieters (z.B. `internet`, `web.de`)
- **SIM-PIN**: Nur erforderlich, wenn Ihre SIM-Karte einen PIN-Schutz hat

### Schritt 4 – Webhook / Firmware-Einstellungen

Eine eindeutige Webhook-ID wird automatisch generiert. **Kopieren Sie diese Werte** — Sie benötigen sie beim Flashen:

| Firmware-Einstellung | Wert |
|---|---|
| `SERVER_PROTOCOL` | `4` (PROTOCOL_HA_WEBHOOK) |
| `SERVER_HOST` | Im Formular angezeigt |
| `SERVER_PORT` | `443` |
| `HA_WEBHOOK_ID` | Im Formular angezeigt |

### Schritt 5 – Flash-Methode

Wählen Sie die Flash-Methode:
- **WLAN OTA**: Firmware über WLAN hochladen
- **Seriell USB**: Firmware über USB-Kabel flashen

---

## Wann werden die Einstellungen auf das Gerät übertragen?

> **Kurzantwort:** Die Einstellungen werden zuerst in Home Assistant gespeichert. Auf das Gerät geschrieben werden sie erst beim Flashen der Firmware.

### Lebenszyklus der Einstellungen

```
Config Flow / Options Flow
        │
        ▼
 HA-Konfigurationseintrag   ← Einstellungen werden hier gespeichert (HA-Datenbank)
 (SSID, Passwort, APN,
  Webhook-ID, Server-Host …)
        │
        │  Bei jeder Flash-Anfrage erzeugt HA:
        ▼
 flash_image.bin            ← kombinierte Datei, on-demand aus aktuellen Einstellungen
 (NVS-Partition             ← Ihre WLAN-/Server-/Webhook-Daten, frisch eingebettet
  + Firmware-Binary)
        │
        ▼
  Gerät geflasht            ← Einstellungen wirken nach dem Neustart des Geräts
```

### Wichtige Punkte

1. **Das Speichern im Config Flow oder Options Flow aktualisiert das Gerät NICHT.**  
   Das Klicken auf *Weiter* / *Speichern* speichert die Werte nur in der HA-Datenbank. Das physische Gerät bleibt unverändert, bis Sie es flashen.

2. **Die Einstellungen werden beim Herunterladen in `flash_image.bin` eingebettet.**  
   Jedes Mal, wenn Sie das Freematics-Panel öffnen und der Download-Link aktiv wird, erstellt die Integration eine frische `flash_image.bin` aus den *aktuellen* Einstellungen. Wenn Sie eine Einstellung ändern, die Datei erneut herunterladen und flashen, startet das Gerät mit den neuen Werten.

3. **Das Firmware-Binary selbst ändert sich zwischen Flashvorgängen nicht.**  
   Nur der Einstellungsbereich (NVS-Partition, Offset `0x9000`) wird neu generiert. Die Anwendungs-Firmware bei Offset `0x10000` ist immer die Version, die mit der aktuellen Integration-Version gebündelt ist.

4. **Ausnahme – WLAN/APN ohne Reflash übertragen.**  
   Wenn das Gerät bereits mit `ENABLE_HTTPD=1` läuft, können WLAN-SSID, WLAN-Passwort und APN über den Button **Konfiguration an Gerät senden** übertragen werden — ohne Flashen. Die Einstellungen werden per HTTP in den NVS des Geräts geschrieben und wirken nach einem Neustart. Siehe [Konfiguration an laufendes Gerät senden](#konfiguration-an-laufendes-gerät-senden).

---

## Firmware flashen

> **Wichtig – Systemarchitektur:** In einer typischen Konfiguration läuft Home Assistant auf einem separaten Server (z.B. Raspberry Pi), während Sie HA über den Browser auf Ihrem Computer bedienen. Der Freematics ONE+ wird per USB an **Ihren Computer** angeschlossen – **nicht** an den HA-Server.

### Welche Methode soll ich verwenden?

| Situation | Empfohlene Methode |
|---|---|
| Gerät über USB am eigenen Computer angeschlossen | [Methode B: Browser-Flasher](#methode-b-browser-seriell-web-serial-api) ✅ |
| Gerät ohne USB-Kabel verfügbar | [Methode A: WLAN OTA](#methode-a-wlan-ota-empfohlen) ✅ |
| HA läuft auf demselben Rechner wie der Browser | [Methode C: Seriell via HA-Server](#methode-c-seriell-usb-via-ha-server) |

### Methode A: WLAN OTA (Empfohlen)

Funktioniert unabhängig davon, wo Home Assistant läuft.

1. Freematics ONE+ einschalten
2. Das Gerät startet im AP-Modus: WLAN **`TELELOGGER`**, Passwort: `PASSWORD`
3. Mit diesem WLAN verbinden
4. In HA: **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren**
5. Geräte-IP `192.168.4.1` eintragen und speichern
6. **Firmware via WLAN OTA flashen**-Button drücken
7. Logs prüfen: **Einstellungen → System → Protokolle**

### Methode B: Browser-Seriell (Web Serial API)

Flasht direkt vom Browser auf das Gerät, das am **eigenen Computer** per USB angeschlossen ist. Keine Software-Installation erforderlich.

**Voraussetzungen:**
- Google Chrome oder Microsoft Edge (Version 89 oder neuer)
- USB-Kabel zwischen Freematics ONE+ und Ihrem Computer
- USB-Seriell-Treiber installiert:
  - [CP210x-Treiber](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) (Silicon Labs)
  - [CH340-Treiber](https://www.wch-ic.com/downloads/CH341SER_EXE.html) (WCH)

**Schritte:**

1. Freematics ONE+ per USB an Ihren Computer anschließen
2. **Browser-Flasher** öffnen:  
   `http://<ihre-ha-adresse>/api/freematics/flasher`
3. **Connect & Flash Firmware** anklicken
4. Im Browser-Dialog den seriellen Port des Freematics ONE+ auswählen  
   *(suchen Sie nach: `CP2102`, `CH340` oder ähnlichem USB-Seriell-Gerät)*
5. Die Firmware wird automatisch geflasht (~30 s) und das Gerät startet neu

> **Port ermitteln:**
> - **Windows**: Geräte-Manager → Anschlüsse (COM & LPT) — erscheint als z.B. `Silicon Labs CP210x USB to UART Bridge (COM3)`
> - **macOS**: `/dev/tty.usbserial-*` oder `/dev/tty.SLAB_USBtoUART` im Terminal
> - **Linux**: `/dev/ttyUSB0` (`dmesg | tail` nach dem Einstecken)

### Methode C: Seriell USB via HA-Server

> ⚠️ **Nur verwenden, wenn der Freematics ONE+ per USB direkt am Home-Assistant-Server angeschlossen ist.** Wenn HA auf einem separaten Server läuft, verwenden Sie stattdessen [Methode A](#methode-a-wlan-ota-empfohlen) oder [Methode B](#methode-b-browser-seriell-web-serial-api).

> **`esptool` wird automatisch mit dieser Integration installiert** — keine manuelle Installation erforderlich.

1. USB-Kabel zwischen Freematics ONE+ und HA-Host anschließen
2. Seriellen Port ermitteln: `dmesg | tail` auf dem HA-Host
3. Port in Integrationseinstellungen eintragen: **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren**
4. **Firmware via Seriell USB flashen**-Button drücken
5. Logs prüfen: **Einstellungen → System → Protokolle**

---

## Konfiguration an laufendes Gerät senden

1. Gerät einschalten und mit dem Netzwerk verbinden
2. IP des Geräts in den Integrationseinstellungen eintragen
3. **Konfiguration an Gerät senden**-Button drücken

Sendet WLAN-SSID, WLAN-Passwort und APN über die HTTP-API des Geräts (`/api/control`).

---

## Lovelace Dashboard & Karte

### Vorgefertigtes Dashboard verwenden

1. `lovelace/freematics-dashboard.yaml` aus diesem Repository kopieren
2. In HA: **Einstellungen → Dashboards → Dashboard hinzufügen** → YAML-Modus
3. Inhalt einfügen und `WEBHOOK_ID_SHORT` durch die ersten 8 Zeichen Ihrer Webhook-ID ersetzen

### Benutzerdefinierte Lovelace-Karte

```yaml
type: custom:freematics-vehicle-card
title: Mein Auto
entity_prefix: sensor.freematics_one_WEBHOOK_ID_SHORT
```

---

## Firmware aktualisieren

1. **HACS → Integrationen → Freematics ONE+** → **Aktualisieren**
2. Home Assistant neu starten
3. **Firmware flashen**-Button drücken (Einstellungen bleiben erhalten und werden automatisch in die neue `flash_image.bin` eingebettet)

---

## Einstellungen nach der Ersteinrichtung ändern

Wenn Sie nach der Ersteinrichtung WLAN-Zugangsdaten, APN oder andere Einstellungen ändern möchten, gehen Sie wie folgt vor:

### Schritt 1 – Einstellungen in Home Assistant aktualisieren

1. Gehen Sie zu **Einstellungen → Geräte & Dienste → Freematics ONE+**
2. Klicken Sie auf **Konfigurieren** (das ⚙-Symbol oder den Link „Konfigurieren")
3. Ändern Sie die gewünschten Felder (WLAN-SSID, Passwort, APN, Geräte-IP, Flash-Methode usw.)
4. Klicken Sie auf **Speichern** — die neuen Werte sind jetzt in Home Assistant gespeichert

> **Am Gerät hat sich noch nichts geändert.** Es verwendet weiterhin die alten Einstellungen, bis Sie es flashen.

### Schritt 2 – Neue Einstellungen auf das Gerät übertragen

Wählen Sie die für Ihre Situation passende Methode:

#### Option A – Neu flashen (empfohlen, überträgt alle Einstellungen)

Öffnen Sie das **Freematics-Panel** (Seitenleiste → *Freematics ONE+*) und flashen Sie über den Browser-Flash oder den manuellen Flash. Das Panel erstellt `flash_image.bin` immer aus den *aktuellen* Einstellungen — die neu gespeicherten Werte werden automatisch eingebettet.

- **Browser-Flash (Chrome/Edge):** Das Panel verwendet automatisch das aktualisierte Manifest — klicken Sie einfach erneut auf den Flash-Button.
- **Manuelles Flashen (esptool / Freematics Builder):** Laden Sie die Datei im Panel erneut herunter, um eine frisch generierte `flash_image.bin` zu erhalten, und flashen Sie sie wie gewohnt bei Offset `0x9000`.

#### Option B – WLAN/APN ohne Reflash übertragen (nur für laufendes Gerät)

Wenn das Gerät bereits läuft, im Netzwerk erreichbar ist und die Firmware mit `ENABLE_HTTPD=1` kompiliert wurde:

1. Stellen Sie sicher, dass die Geräte-IP in den Integrationseinstellungen eingetragen ist
2. Drücken Sie den Button **Konfiguration an Gerät senden**
3. Die neue WLAN-SSID, das WLAN-Passwort und der APN werden per HTTP in den NVS des Geräts geschrieben
4. Gerät neu starten (Button **Gerät neu starten** oder OBD-Stecker ab- und wieder anstecken)

> ⚠️ Diese Methode aktualisiert nur WLAN und APN. **Server-Host, Webhook-Pfad und Port werden auf diesem Weg nicht übertragen** — dafür ist ein vollständiger Reflash erforderlich.

---

## Entitäten-Übersicht

Sensor-Entitäten werden automatisch erstellt, sobald das Gerät Daten sendet.
Schaltflächen-Entitäten stehen sofort nach der Einrichtung zur Verfügung.

Entitätsnamen folgen dem Muster:
- Sensoren: `sensor.freematics_one_<webhook_id>_<messgrösse>`
- Schaltflächen: `button.freematics_one_<aktion>`

---

## Fehlerbehebung

**Keine Sensordaten**
- Webhook-ID und SERVER_HOST in der Firmware prüfen
- SERVER_PROTOCOL = 4 in der Firmware sicherstellen
- HA-Logs auf Fehler prüfen

**WLAN OTA fehlgeschlagen**
- Sicherstellen, dass das Gerät erreichbar ist (Ping testen)
- Im AP-Modus: Mit `TELELOGGER`-WLAN verbunden?
- ENABLE_HTTPD=1 in der Firmware?
- Bei „Connection reset by peer": Das Gerät hat nach dem Flash neu gestartet — dies ist normal. Prüfen, ob es sich mit HA reconnectet.

**Browser-Flasher funktioniert nicht**
- Chrome oder Edge (Version 89+) verwenden — Firefox unterstützt Web Serial nicht
- USB-Seriell-Treiber für das Gerät installieren (CP210x oder CH340)
- Anderen USB-Port oder ein anderes USB-Kabel ausprobieren
- Die Web Serial API erfordert eine **sichere HTTPS-Verbindung**. Über eine lokale IP-Adresse (HTTP) funktioniert dies nicht. Nabu Casa oder manuelles Flash mit esptool.py verwenden (siehe unten).
- Wenn der Fortschrittsbalken nach der Port-Auswahl hängt: Der Browser konnte keine Verbindung herstellen. Manuelle Flash-Methode (esptool.py) nutzen.

**Serieller Flash via HA-Server fehlgeschlagen**
- Prüfen, ob das Gerät wirklich am HA-Server (nicht am eigenen Computer) angeschlossen ist
- Port prüfen: `dmesg | tail` auf dem HA-Host
- Berechtigungen: `sudo chmod 666 /dev/ttyUSB0`
- `esptool` wird automatisch durch die Integration installiert. Falls noch nicht vorhanden: `pip install esptool`

**Manuelles Flashen als Fallback (esptool)**

Wenn alle automatisierten Methoden scheitern, kann die Firmware manuell vom eigenen Computer geflasht werden.

**Schritt 1 – Python installieren**

Python von [https://www.python.org/downloads/](https://www.python.org/downloads/) herunterladen und installieren.

> **Windows**: Beim Installieren die Option **„Add Python to PATH"** aktivieren, damit `python` in der Eingabeaufforderung verfügbar ist.

**Schritt 2 – esptool installieren**

Ein Terminal öffnen (Windows: Eingabeaufforderung oder PowerShell) und eingeben:

```bash
pip install esptool
```

**Schritt 3 – `flash_image.bin` herunterladen**

Das **Freematics-Panel** in Home Assistant öffnen (Seitenleiste → *Freematics ONE+*) und den Link `flash_image.bin` herunterladen. Diese Datei enthält NVS-Einstellungen und Firmware in einer einzigen Binärdatei, die bei Offset `0x9000` geflasht wird.

**Schritt 4 – COM-Port ermitteln**

- **Windows**: Geräte-Manager → Anschlüsse (COM & LPT) → z.B. `COM3`
- **Linux**: `dmesg | tail` nach dem Einstecken → z.B. `/dev/ttyUSB0`
- **macOS**: `ls /dev/tty.usbserial*`

**Schritt 5 – Flashen**

```bash
python -m esptool --chip esp32 --port COM3 --baud 921600 write-flash 0x9000 flash_image.bin
```

*(COM3 durch den eigenen Port ersetzen, z.B. `/dev/ttyUSB0`)*

> **Hinweis:** Sowohl `write-flash` (Bindestrich) als auch `write_flash` (Unterstrich) werden von esptool akzeptiert. Unter Windows sollte immer `python -m esptool` statt `esptool.py` verwendet werden.

Nach dem Flashen startet das Gerät neu und verbindet sich mit dem WLAN anhand der in `flash_image.bin` gespeicherten Zugangsdaten.

**Alternative: PlatformIO / VS Code**

1. [Visual Studio Code](https://code.visualstudio.com/) und die [PlatformIO IDE-Erweiterung](https://platformio.org/install/ide?install=vscode) installieren.
2. Den Ordner `firmware_v5/telelogger/` in VS Code öffnen.
3. Einstellungen in `config.h` anpassen (WLAN-Zugangsdaten, Webhook-ID usw.).
4. Auf **Upload** klicken — PlatformIO kompiliert und flasht automatisch.

