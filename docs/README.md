# Freematics ONE+ Home Assistant Integration

A HACS-compatible Home Assistant integration for the **Freematics ONE+** OBD-II telematics device. The device pushes real-time vehicle telemetry data (speed, RPM, GPS, engine sensors, etc.) directly to Home Assistant via a secure HTTPS webhook — no VPN, port forwarding, or public IP required (works with Nabu Casa too).

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation via HACS](#installation-via-hacs)
3. [Integration Setup (Config Flow)](#integration-setup-config-flow)
4. [Firmware Flashing](#firmware-flashing)
   - [Method A: WiFi OTA (Recommended)](#method-a-wifi-ota-recommended)
   - [Method B: Serial USB](#method-b-serial-usb)
5. [Sending Configuration to a Running Device](#sending-configuration-to-a-running-device)
6. [Lovelace Dashboard & Card](#lovelace-dashboard--card)
7. [Updating the Firmware](#updating-the-firmware)
8. [Entities Reference](#entities-reference)
9. [Troubleshooting](#troubleshooting)
10. [Technical Background](#technical-background)

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

## Firmware Flashing

### Method A: WiFi OTA (Recommended)

This method connects to the device over WiFi and uploads the firmware binary.

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

### Method B: Serial USB

This method uses `esptool` to flash via a USB serial connection.

**Requirements:**
- USB cable between the Freematics ONE+ and the HA host machine
- `esptool` installed on the HA host:
  ```bash
  pip install esptool
  ```
- Correct serial port permissions (Linux: `sudo usermod -aG dialout homeassistant`)

**Steps:**

1. Connect the Freematics ONE+ to the HA host via USB
2. Find the serial port: check `dmesg | tail` or `ls /dev/tty*`
3. Set the serial port in integration settings: **Settings → Integrations → Freematics ONE+ → Configure**
4. Press **Flash Firmware via Serial USB** button
5. Check logs for progress

**Manual flash command** (if the button fails):
```bash
esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 921600 \
  write_flash --flash_mode dio --flash_size detect \
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

> Your device settings (WiFi credentials, webhook ID, etc.) are preserved in Home Assistant and will be re-applied automatically.

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

### Serial flash fails

- Check the serial port path (`dmesg | tail` after plugging in USB)
- Ensure correct permissions: `sudo chmod 666 /dev/ttyUSB0`
- Try reducing baud rate (edit `flash_manager.py` to use `115200`)
- Install esptool: `pip install esptool`

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
4. [Firmware flashen](#firmware-flashen)
5. [Konfiguration an laufendes Gerät senden](#konfiguration-an-laufendes-gerät-senden)
6. [Lovelace Dashboard & Karte](#lovelace-dashboard--karte)
7. [Firmware aktualisieren](#firmware-aktualisieren)
8. [Entitäten-Übersicht](#entitäten-übersicht)
9. [Fehlerbehebung](#fehlerbehebung)

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

## Firmware flashen

### Methode A: WLAN OTA (Empfohlen)

1. Schalten Sie den Freematics ONE+ ein
2. Das Gerät startet im AP-Modus: WLAN **`TELELOGGER`**, Passwort: `PASSWORD`
3. Verbinden Sie sich mit diesem WLAN
4. Gerät-IP einstellen: `192.168.4.1`
5. In HA: **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren**
6. IP eintragen und speichern
7. **Firmware via WLAN OTA flashen**-Button drücken
8. Logs prüfen: **Einstellungen → System → Protokolle**

### Methode B: Seriell USB

1. USB-Kabel zwischen Freematics ONE+ und HA-Host
2. `esptool` installieren: `pip install esptool`
3. Seriellen Port ermitteln: `dmesg | tail`
4. Port in Integrationseinstellungen eintragen
5. **Firmware via Seriell USB flashen**-Button drücken

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
3. **Firmware flashen**-Button drücken (Einstellungen bleiben erhalten)

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

**Serieller Flash fehlgeschlagen**
- Port prüfen: `dmesg | tail`
- Berechtigungen: `sudo chmod 666 /dev/ttyUSB0`
- esptool installieren: `pip install esptool`
