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
12. [FAQ & HowTo](#faq--howto)
13. [Technical Background](#technical-background)

---

## Requirements

- **Home Assistant** 2023.1 or newer
- **HACS** installed ([see HACS docs](https://hacs.xyz/docs/setup/download))
- Freematics ONE+ Model A, Model B, or Model H
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
3. Follow the 7-step wizard:

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

### Step 5 – Device Model

Select your Freematics ONE+ hardware model (A, B, or H).

### Step 6 – Operating Mode

Choose how the device should operate after flashing:

| Mode | Description |
|---|---|
| **Telelogger – Webhook → Home Assistant** *(recommended)* | Pushes telemetry directly to the HA webhook. HTTPD and BLE are automatically disabled, freeing ~104 KB of heap — **required** for the TLS connection to succeed. |
| **Datalogger – Local HTTP API (HTTPD)** | Enables the built-in HTTP server on port 80 (`/api/live`, `/api/info`, …) for local network access. Use this if you don't need the HA webhook or want a local dashboard. |

**BLE (Bluetooth SPP server)** — independent of the mode selection. Enable only if you use the Freematics Controller App over Bluetooth. Keeping BLE off is strongly recommended for Telelogger mode because the BLE stack uses ~100 KB of heap.

**Intervals** — leave at `0` to keep firmware defaults (~1000 ms data interval, 120 s sync interval).

**LED & Buzzer settings** *(Advanced)*:
- **Red LED** (`LED_RED_EN`) — lights up while the device is powered on / in standby. Enable/disable to reduce cabin light pollution.
- **White LED** (`LED_WHITE_EN`) — lights up during each data transmission. Enable/disable independently.
- **Buzzer** (`BEEP_EN`) — emits a short beep on each successful WiFi or cellular connection. Disable to suppress in-cabin noise.

**Cellular Debug** (`CELL_DEBUG`) — enables verbose AT-command logging on the serial monitor. Useful when diagnosing SIM/cellular connection problems. Leave off for normal operation.

> **Note:** The firmware always logs data to the SD card regardless of mode. "Telelogger" and "Datalogger" describe how data is *transmitted*, not whether it is stored locally.

### Step 7 – Flash Method

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

### Webhook not connecting – SSL memory error (`-32512`)

If your serial monitor shows:

```
[E][ssl_client.cpp] _handle_error(): (-32512) SSL - Memory allocation failed
[HTTP] Unable to connect
```

This is `MBEDTLS_ERR_SSL_ALLOC_FAILED`. The BLE stack (~100 KB) and optionally the built-in HTTP server (~4 KB) leave insufficient contiguous heap for the TLS handshake.

**Fix:** Go to the integration **Options** → **Advanced Firmware Settings** and:

1. Set **Enable BLE** → ❌ Off
2. Set **Enable HTTPD** → ❌ Off
3. Re-flash the device

Disabling BLE is the most impactful change. After flashing, the webhook connection should succeed.

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

## FAQ & HowTo

A quick reference for the most common questions and problems. Each answer links to the relevant full section for more detail.

---

### ❓ Q: My device never sends any data to Home Assistant. Where do I start?

**A:** Work through this checklist:

1. **Is the device powered?** — Plug the Freematics ONE+ into the OBD-II port. The LEDs should light up briefly.
2. **Is the device connected to the internet?** — For WiFi: check that the SSID and password are correct. For cellular: check the APN.
3. **Is the Webhook ID correct?** — Compare the `HA_WEBHOOK_ID` in the firmware (baked in during flash) with the Webhook ID shown in the integration settings.
4. **Is `SERVER_HOST` correct?** — It must match your Home Assistant external URL (e.g. `your-ha.duckdns.org` or your Nabu Casa subdomain).
5. **Is `SERVER_PROTOCOL` = `4`?** — This selects the HA webhook protocol.
6. **Are there errors in HA logs?** — Go to **Settings → System → Logs** and filter for `freematics`.

> 💡 The fastest fix is usually to re-flash with the correct settings and then check the serial monitor output.

---

### ❓ Q: I see `SSL - Memory allocation failed` in the serial monitor. What does this mean?

**A:** This is `MBEDTLS_ERR_SSL_ALLOC_FAILED` — the ESP32 cannot allocate enough contiguous heap for the TLS handshake. Most commonly caused by BLE or HTTPD consuming memory.

**Fix:**
1. Go to **Settings → Integrations → Freematics ONE+ → Configure**
2. Set **Enable BLE** → ❌ Off
3. Set **Enable HTTPD** → ❌ Off  *(HTTPD is re-enabled automatically for WiFi OTA when you need it)*
4. Re-flash the device

Disabling BLE frees ~100 KB of heap — usually enough for the TLS connection to succeed.

---

### ❓ Q: WiFi OTA flash fails with "Connection refused" or "Unable to connect". What should I check?

**A:**
- Make sure the device is powered on and reachable at the configured IP address (ping it).
- If using AP mode: your computer must be connected to the **`TELELOGGER`** WiFi (password: `PASSWORD`) before starting the OTA flash from HA.
- The device must be running firmware with `ENABLE_HTTPD=1` to accept OTA uploads.
- `192.168.4.1` is the correct IP when the device is in AP mode.
- If you see **"Connection reset by peer"**: the device restarted after a *successful* flash — this is normal. Wait ~30 seconds and check if the device connects to HA.

---

### ❓ Q: Browser Serial flash (Method B) doesn't work — I don't see a "Connect & Flash" button or the progress bar gets stuck.

**A:**
- You must use **Google Chrome** or **Microsoft Edge** version 89 or later. Firefox does not support the Web Serial API.
- Your HA instance must be served over **HTTPS**. The Web Serial API is blocked on plain HTTP (local IP without a certificate). Use Nabu Casa, a Let's Encrypt certificate, or fall back to Method A (WiFi OTA) or the manual esptool method.
- Install the USB-Serial driver for your device:
  - [CP210x driver (Silicon Labs)](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)
  - [CH340 driver (WCH)](https://www.wch-ic.com/downloads/CH341SER_EXE.html)
- Try a different USB cable or port.
- If the progress bar freezes immediately after port selection: close the browser tab, reload, and try again.
- As a last resort, use the [Manual Flash Fallback (esptool)](#manual-flash-fallback-esptool) method.

---

### ❓ Q: Serial USB flash via HA Server (Method C) fails. The button does nothing or I see a permission error.

**A:**
- Ensure the Freematics ONE+ is connected to the **HA host** via USB — not to your own computer.
- Find the correct port: run `dmesg | tail` on the HA host right after plugging in the USB cable.
- Fix permissions: `sudo chmod 666 /dev/ttyUSB0` (replace with your actual port).
- `esptool` is installed automatically by this integration. If it is still missing, run `pip install esptool` on the HA host.
- Try Method B (Browser Serial) if your device is connected to your own computer instead of the HA server.

---

### ❓ Q: I changed the WiFi password. How do I update the device without reflashing?

**A:** If the device is running and on the network:
1. Update the WiFi password in **Settings → Integrations → Freematics ONE+ → Configure**
2. Make sure the **Device IP** is set correctly
3. Press **Send Config to Device** — this pushes the new SSID/password to the device's NVS over HTTP
4. Restart the device (button or OBD unplug/replug)

If the device is not reachable (e.g. it has already lost WiFi), you must re-flash with the correct credentials.

---

### ❓ Q: The LEDs in my car are annoying at night. How do I turn them off?

**A:** Go to **Settings → Integrations → Freematics ONE+ → Configure** → **Advanced Firmware Settings**:
- **Red LED** (`LED_RED_EN`) → disable to turn off the power/standby LED
- **White LED** (`LED_WHITE_EN`) → disable to turn off the transmission LED
- **Buzzer** (`BEEP_EN`) → disable to silence the connection beep

Re-flash after saving. The settings are written to the device's NVS at flash time.

---

### ❓ Q: The device connects via cellular but I'm having intermittent connection drops or TLS errors.

**A:**
1. Enable **Cellular Debug** (`CELL_DEBUG`) in **Configure → Advanced Firmware Settings** and re-flash. This adds verbose AT-command logging to the serial monitor so you can see exactly what's happening.
2. Check the APN — try leaving it empty to let the device auto-detect, or set it explicitly to your provider's value.
3. If you see `AT+CCHOPEN` errors: the SIM7600 firmware on your device may require a specific SSL context ID. The firmware tries both `ssl_ctx_id=0` and `ssl_ctx_id=1` automatically. If neither works, check that the SIM has data connectivity (try inserting in a phone first).
4. Check signal strength via the `sensor.…_signal` entity in HA (should be above −95 dBm for reliable data transfer).

---

### ❓ Q: How do I update the firmware after a new integration release?

**A:**
1. In HACS, go to **Integrations → Freematics ONE+** and click **Update**.
2. Restart Home Assistant.
3. Open the **Freematics panel** (sidebar → *Freematics ONE+*).
4. Flash the device again using your preferred method (WiFi OTA or Browser Serial).

Your device settings (WiFi, webhook, APN, etc.) are preserved in Home Assistant and automatically embedded in the new `flash_image.bin`. You do **not** need to re-run the setup wizard.

---

### ❓ Q: I want to reset the device to factory defaults and start over.

**A:**
1. In HA go to **Settings → Devices & Services**, find the Freematics ONE+ integration, and click **Delete**.
2. Add it again (**Add Integration → Freematics ONE+**) and run the setup wizard from scratch.
3. Flash the device with the new settings.

To erase the ESP32's NVS partition manually (complete wipe):
```bash
python -m esptool --chip esp32 --port COM3 erase_flash
```
After this the device will not boot until you flash the full `flash_image.bin` again.

---

### ❓ Q: The Lovelace card shows no data / entities are "unavailable".

**A:**
- Entities are only created when the first webhook payload arrives from the device. Until the device has sent at least one message, the entities do not exist in HA.
- Check that the device is running, connected to the internet, and that the Webhook ID and SERVER_HOST are correct.
- Verify the `entity_prefix` in the Lovelace card YAML matches the actual entity names. The prefix should be `sensor.freematics_one_<first-8-chars-of-webhook-id>`.

---

### ❓ Q: I installed the integration but do not see a "Freematics ONE+" entry in the sidebar.

**A:** The Lovelace panel is registered automatically, but you may need to **clear your browser cache** (Ctrl+F5 / Cmd+Shift+R) or **hard-reload** the HA frontend after installing. Also make sure you restarted Home Assistant after the HACS installation.

---

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
12. [FAQ & HowTo (Deutsch)](#faq--howto-deutsch)

---

## Voraussetzungen

- **Home Assistant** 2023.1 oder neuer
- **HACS** installiert ([HACS-Dokumentation](https://hacs.xyz/docs/setup/download))
- Freematics ONE+ Modell A, Modell B oder Modell H
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
3. Folgen Sie dem 7-stufigen Assistenten:

### Schritt 1 – Verbindungsart

Wählen Sie aus, wie Ihr Gerät mit dem Internet verbunden wird:

| Option | Beschreibung |
|---|---|
| **Nur WLAN** | Das Gerät nutzt ein WLAN-Netzwerk (Hotspot oder Heimrouter) |
| **Nur Mobilfunk/SIM** | Das Gerät nutzt eine SIM-Karte |
| **WLAN + Mobilfunk-Fallback** | WLAN bevorzugt; Mobilfunk als Fallback wenn WLAN nicht verfügbar |

### Schritt 2 – WLAN-Zugangsdaten *(nur bei WLAN/Beides)*

Geben Sie **SSID** und **Passwort** des WLAN-Netzwerks ein, mit dem sich das Gerät verbinden soll.

> Sie können auch den mobilen Hotspot Ihres Smartphones verwenden.

### Schritt 3 – Mobilfunk/SIM *(nur bei Mobilfunk/Beides)*

- **APN**: Der APN Ihres Mobilfunkanbieters (z.B. `internet`, `data.t-mobile.com`). Leer lassen für automatische Erkennung.
- **SIM-PIN**: Nur erforderlich, wenn Ihre SIM-Karte einen PIN-Schutz hat.

### Schritt 4 – Webhook / Firmware-Einstellungen

Eine eindeutige Webhook-ID wird automatisch generiert. **Kopieren Sie diese Werte** — Sie benötigen sie beim Flashen:

| Firmware-Einstellung | Wert |
|---|---|
| `SERVER_PROTOCOL` | `4` (PROTOCOL_HA_WEBHOOK) |
| `SERVER_HOST` | Im Formular angezeigt |
| `SERVER_PORT` | `443` |
| `HA_WEBHOOK_ID` | Im Formular angezeigt |

Die Webhook-ID kann angepasst werden oder der automatisch generierte Wert übernommen werden.

### Schritt 5 – Gerätemodell

Wählen Sie Ihr Freematics ONE+ Hardwaremodell (A, B oder H).

### Schritt 6 – Betriebsmodus

Wählen Sie, wie das Gerät nach dem Flashen betrieben werden soll:

| Modus | Beschreibung |
|---|---|
| **Telelogger – Webhook → Home Assistant** *(empfohlen)* | Sendet Telemetriedaten direkt an den HA-Webhook. HTTPD und BLE werden automatisch deaktiviert, wodurch ~104 KB Heap freigegeben werden — **erforderlich** für eine erfolgreiche TLS-Verbindung. |
| **Datalogger – Lokale HTTP-API (HTTPD)** | Aktiviert den eingebauten HTTP-Server auf Port 80 für lokalen Netzwerkzugriff. |

**BLE (Bluetooth SPP-Server)** — unabhängig von der Moduswahl. Nur aktivieren, wenn Sie die Freematics Controller App über Bluetooth nutzen. Für den Telelogger-Modus wird BLE-Deaktivierung dringend empfohlen (spart ~100 KB Heap).

**Intervalle** — bei `0` belassen, um die Firmware-Standardwerte zu verwenden (~1000 ms Datenintervall, 120 s Synchronisationsintervall).

**LED- & Buzzer-Einstellungen** *(Erweitert)*:
- **Rote LED** (`LED_RED_EN`) — leuchtet wenn das Gerät eingeschaltet/im Standby ist. Deaktivierbar zur Reduzierung von Licht im Fahrzeuginnenraum.
- **Weiße LED** (`LED_WHITE_EN`) — leuchtet bei jeder Datenübertragung. Unabhängig deaktivierbar.
- **Buzzer** (`BEEP_EN`) — kurzer Piepton bei erfolgreicher WLAN- oder Mobilfunkverbindung. Deaktivierbar zur Geräuschreduktion.

**Mobilfunk-Debug** (`CELL_DEBUG`) — aktiviert ausführliches AT-Befehls-Logging auf dem seriellen Monitor. Nützlich bei der Fehlersuche. Im Normalbetrieb deaktiviert lassen.

> **Hinweis:** Die Firmware schreibt Daten immer auf die SD-Karte, unabhängig vom Modus. "Telelogger" und "Datalogger" beschreiben die *Übertragungsart*, nicht ob Daten lokal gespeichert werden.

### Schritt 7 – Flash-Methode

Wählen Sie die Methode zum Flashen der Firmware:

| Methode | Beschreibung |
|---|---|
| **WLAN OTA** | Firmware über WLAN auf ein Gerät im Netzwerk oder im AP-Modus hochladen |
| **Seriell USB** | Flashen über USB-Kabel, das am HA-Host angeschlossen ist |

- **Geräte-IP**: IP-Adresse des laufenden Geräts (oder `192.168.4.1` im AP-Modus)
- **HTTP-Port**: Normalerweise `80`
- **Serieller Port**: z.B. `/dev/ttyUSB0` (Linux) oder `COM3` (Windows)

Klicken Sie auf **Weiter**, um die Einrichtung abzuschließen. Verwenden Sie anschließend die **Firmware flashen**-Schaltflächen, um den Flash-Vorgang zu starten.

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
- **Manuelles Flashen (esptool / Freematics Builder):** Laden Sie die Datei im Panel erneut herunter, um eine frisch generierte `flash_image.bin` zu erhalten, und flashen Sie sie wie gewohnt bei Offset `0x1000`.

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

### Sensor-Entitäten

| Entität | Beschreibung | Einheit |
|---|---|---|
| `sensor.…_speed` | Fahrzeuggeschwindigkeit (OBD) | km/h |
| `sensor.…_rpm` | Motordrehzahl | U/min |
| `sensor.…_throttle` | Drosselklappenstellung | % |
| `sensor.…_engine_load` | Motorlast | % |
| `sensor.…_coolant_temp` | Kühlmitteltemperatur | °C |
| `sensor.…_intake_temp` | Ansauglufttemperatur | °C |
| `sensor.…_fuel_pressure` | Kraftstoffdruck | kPa |
| `sensor.…_timing_advance` | Zündzeitpunkt-Vorverstellung | ° |
| `sensor.…_lat` | GPS-Breitengrad | ° |
| `sensor.…_lng` | GPS-Längengrad | ° |
| `sensor.…_alt` | GPS-Höhe | m |
| `sensor.…_gps_speed` | GPS-Geschwindigkeit | km/h |
| `sensor.…_heading` | GPS-Kursrichtung | ° |
| `sensor.…_satellites` | GPS-Satellitenanzahl | — |
| `sensor.…_hdop` | GPS-HDOP | — |
| `sensor.…_acc_x` | Beschleunigung X | m/s² |
| `sensor.…_acc_y` | Beschleunigung Y | m/s² |
| `sensor.…_acc_z` | Beschleunigung Z | m/s² |
| `sensor.…_battery` | Batteriespannung | V |
| `sensor.…_signal` | Signalstärke | dBm |
| `sensor.…_device_temp` | Gerätetemperatur | °C |

### Schaltflächen-Entitäten

| Entität | Beschreibung |
|---|---|
| `button.…_flash_firmware_via_serial` | Firmware via USB-Seriell flashen |
| `button.…_flash_firmware_via_wifi_ota` | Firmware via WLAN OTA flashen |
| `button.…_send_config_to_device` | WLAN/APN-Konfiguration ans Gerät senden |
| `button.…_restart_device` | Gerät neu starten |

Entitätsnamen folgen dem Muster:
- Sensoren: `sensor.freematics_one_<webhook_id_kurz>_<messgröße>`
- Schaltflächen: `button.freematics_one_<webhook_id_kurz>_<aktion>`

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

Das **Freematics-Panel** in Home Assistant öffnen (Seitenleiste → *Freematics ONE+*) und den Link `flash_image.bin` herunterladen. Diese Datei enthält Bootloader, Partitionstabelle, NVS-Einstellungen und Firmware in einer einzigen Binärdatei, die bei Offset `0x1000` geflasht wird.

**Schritt 4 – COM-Port ermitteln**

- **Windows**: Geräte-Manager → Anschlüsse (COM & LPT) → z.B. `COM3`
- **Linux**: `dmesg | tail` nach dem Einstecken → z.B. `/dev/ttyUSB0`
- **macOS**: `ls /dev/tty.usbserial*`

**Schritt 5 – Flashen**

```bash
python -m esptool --chip esp32 --port COM3 --baud 921600 write-flash 0x1000 flash_image.bin
```

*(COM3 durch den eigenen Port ersetzen, z.B. `/dev/ttyUSB0`)*

> **Hinweis:** Sowohl `write-flash` (Bindestrich) als auch `write_flash` (Unterstrich) werden von esptool akzeptiert. Unter Windows sollte immer `python -m esptool` statt `esptool.py` verwendet werden.

Nach dem Flashen startet das Gerät neu und verbindet sich mit dem WLAN anhand der in `flash_image.bin` gespeicherten Zugangsdaten.

**Alternative: PlatformIO / VS Code**

1. [Visual Studio Code](https://code.visualstudio.com/) und die [PlatformIO IDE-Erweiterung](https://platformio.org/install/ide?install=vscode) installieren.
2. Den Ordner `firmware_v5/telelogger/` in VS Code öffnen.
3. Einstellungen in `config.h` anpassen (WLAN-Zugangsdaten, Webhook-ID usw.).
4. Auf **Upload** klicken — PlatformIO kompiliert und flasht automatisch.

---

## FAQ & HowTo (Deutsch)

Häufige Fragen und Probleme auf einen Blick. Jede Antwort verweist auf den entsprechenden Detailabschnitt.

---

### ❓ F: Mein Gerät sendet keine Daten an Home Assistant. Wo fange ich an?

**A:** Folgende Checkliste durchgehen:

1. **Ist das Gerät eingeschaltet?** — Freematics ONE+ in die OBD-II-Buchse stecken. Die LEDs sollten kurz aufleuchten.
2. **Hat das Gerät Internet-Konnektivität?** — Bei WLAN: SSID und Passwort prüfen. Bei Mobilfunk: APN prüfen.
3. **Stimmt die Webhook-ID?** — Die in der Firmware gespeicherte `HA_WEBHOOK_ID` muss mit der Webhook-ID in den Integrationseinstellungen übereinstimmen.
4. **Stimmt `SERVER_HOST`?** — Er muss Ihrer externen HA-URL entsprechen (z.B. `ihr-name.duckdns.org` oder Ihre Nabu-Casa-Subdomain).
5. **Ist `SERVER_PROTOCOL` = `4`?** — Dieser Wert wählt das HA-Webhook-Protokoll.
6. **Gibt es Fehler in den HA-Logs?** — **Einstellungen → System → Protokolle** öffnen und nach `freematics` filtern.

> 💡 Die schnellste Lösung ist meist ein erneutes Flashen mit den korrekten Einstellungen, anschließend den seriellen Monitor-Output prüfen.

---

### ❓ F: Im seriellen Monitor erscheint `SSL - Memory allocation failed`. Was bedeutet das?

**A:** Dies ist `MBEDTLS_ERR_SSL_ALLOC_FAILED` — der ESP32 kann keinen ausreichend großen zusammenhängenden Heap-Speicher für den TLS-Handshake reservieren. Häufigste Ursache: BLE oder HTTPD belegen Speicher.

**Lösung:**
1. **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren**
2. **BLE aktivieren** → ❌ Aus
3. **HTTPD aktivieren** → ❌ Aus *(HTTPD wird für WLAN-OTA automatisch wieder aktiviert)*
4. Gerät neu flashen

BLE-Deaktivierung gibt ~100 KB Heap frei — in der Regel genug für eine erfolgreiche TLS-Verbindung.

---

### ❓ F: WLAN OTA schlägt mit „Connection refused" oder „Unable to connect" fehl.

**A:**
- Sicherstellen, dass das Gerät eingeschaltet und unter der konfigurierten IP-Adresse erreichbar ist (Ping-Test).
- Im AP-Modus: Ihr Computer muss mit dem **`TELELOGGER`**-WLAN (Passwort: `PASSWORD`) verbunden sein, bevor der OTA-Flash aus HA gestartet wird.
- Das Gerät muss Firmware mit `ENABLE_HTTPD=1` ausführen, um OTA-Uploads anzunehmen.
- Im AP-Modus ist `192.168.4.1` die korrekte IP-Adresse.
- Bei **„Connection reset by peer"**: Das Gerät hat nach einem *erfolgreichen* Flash neu gestartet — das ist normal. ~30 Sekunden warten und prüfen, ob sich das Gerät mit HA verbindet.

---

### ❓ F: Der Browser-Flasher (Methode B) funktioniert nicht — kein „Connect & Flash"-Button sichtbar oder Fortschrittsbalken hängt.

**A:**
- **Google Chrome** oder **Microsoft Edge** ab Version 89 verwenden. Firefox unterstützt Web Serial nicht.
- HA muss über **HTTPS** erreichbar sein. Web Serial funktioniert nicht über plain HTTP (lokale IP ohne Zertifikat). Nabu Casa, Let's Encrypt oder den manuellen esptool-Weg nutzen.
- USB-Seriell-Treiber installieren:
  - [CP210x-Treiber (Silicon Labs)](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)
  - [CH340-Treiber (WCH)](https://www.wch-ic.com/downloads/CH341SER_EXE.html)
- Anderen USB-Port oder ein anderes Kabel ausprobieren.
- Falls der Fortschrittsbalken sofort einfriert: Browser-Tab schließen, neu laden und erneut versuchen.
- Als letzten Ausweg: [Manuelles Flashen als Fallback (esptool)](#manuelles-flashen-als-fallback-esptool) nutzen.

---

### ❓ F: Serieller USB-Flash via HA-Server (Methode C) schlägt fehl.

**A:**
- Sicherstellen, dass der Freematics ONE+ per USB am **HA-Host** angeschlossen ist — nicht am eigenen Computer.
- Richtigen Port ermitteln: `dmesg | tail` auf dem HA-Host direkt nach dem Einstecken des USB-Kabels ausführen.
- Berechtigungen korrigieren: `sudo chmod 666 /dev/ttyUSB0` (Port durch den tatsächlichen ersetzen).
- `esptool` wird durch diese Integration automatisch installiert. Falls es fehlt: `pip install esptool` auf dem HA-Host ausführen.
- Wenn das Gerät am eigenen Computer angeschlossen ist: stattdessen Methode B (Browser-Seriell) verwenden.

---

### ❓ F: Ich habe das WLAN-Passwort geändert. Wie aktualisiere ich das Gerät ohne Reflash?

**A:** Wenn das Gerät läuft und im Netzwerk erreichbar ist:
1. Passwort unter **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren** aktualisieren
2. Sicherstellen, dass die **Geräte-IP** korrekt eingetragen ist
3. **Konfiguration an Gerät senden** drücken — überträgt die neue SSID/das neue Passwort per HTTP in den NVS
4. Gerät neu starten (Schaltfläche oder OBD-Stecker ab- und wieder anstecken)

Wenn das Gerät nicht erreichbar ist (z.B. WLAN bereits verloren), muss die Firmware neu geflasht werden.

---

### ❓ F: Die LEDs im Auto stören mich nachts. Wie deaktiviere ich sie?

**A:** **Einstellungen → Integrationen → Freematics ONE+ → Konfigurieren → Erweiterte Firmware-Einstellungen**:
- **Rote LED** (`LED_RED_EN`) → deaktivieren, um die Betriebs-/Standby-LED auszuschalten
- **Weiße LED** (`LED_WHITE_EN`) → deaktivieren, um die Übertragungs-LED auszuschalten
- **Buzzer** (`BEEP_EN`) → deaktivieren, um den Verbindungs-Piepton zu unterdrücken

Nach dem Speichern neu flashen. Die Einstellungen werden beim Flash in den NVS des Geräts geschrieben.

---

### ❓ F: Das Gerät verbindet sich über Mobilfunk, aber die Verbindung bricht immer wieder ab.

**A:**
1. **Mobilfunk-Debug** (`CELL_DEBUG`) unter **Konfigurieren → Erweiterte Firmware-Einstellungen** aktivieren und neu flashen. Dies fügt ausführliches AT-Befehls-Logging hinzu, mit dem der genaue Fehler sichtbar wird.
2. Den APN prüfen — leer lassen für automatische Erkennung oder den APN Ihres Anbieters explizit eintragen.
3. Signalstärke über die Entität `sensor.…_signal` prüfen (sollte über −95 dBm liegen).
4. SIM-Karte in einem Smartphone testen, um grundlegende Mobilfunkkonnektivität sicherzustellen.

---

### ❓ F: Wie aktualisiere ich die Firmware nach einem neuen Integrations-Release?

**A:**
1. In HACS: **Integrationen → Freematics ONE+** → **Aktualisieren**
2. Home Assistant neu starten
3. **Freematics-Panel** öffnen (Seitenleiste → *Freematics ONE+*)
4. Gerät erneut mit der bevorzugten Methode flashen (WLAN OTA oder Browser-Seriell)

Geräteeinstellungen (WLAN, Webhook, APN usw.) bleiben in HA erhalten und werden automatisch in die neue `flash_image.bin` eingebettet. Der Setup-Assistent muss **nicht** erneut durchlaufen werden.

---

### ❓ F: Ich möchte das Gerät auf Werkseinstellungen zurücksetzen und neu beginnen.

**A:**
1. In HA: **Einstellungen → Geräte & Dienste**, Freematics ONE+-Integration auswählen und **Löschen**.
2. Integration erneut hinzufügen (**Integration hinzufügen → Freematics ONE+**) und den Setup-Assistenten erneut durchlaufen.
3. Gerät mit den neuen Einstellungen neu flashen.

Zum vollständigen Löschen des ESP32-Flash (NVS-Partition):
```bash
python -m esptool --chip esp32 --port COM3 erase_flash
```
Danach startet das Gerät nicht mehr, bis `flash_image.bin` erneut geflasht wird.

---

### ❓ F: Die Lovelace-Karte zeigt keine Daten / Entitäten sind „nicht verfügbar".

**A:**
- Entitäten werden nur erstellt, wenn die erste Webhook-Nutzlast vom Gerät eingetroffen ist. Bis dahin existieren die Entitäten in HA nicht.
- Prüfen, ob das Gerät läuft, mit dem Internet verbunden ist und Webhook-ID sowie SERVER_HOST korrekt sind.
- Das `entity_prefix` in der Lovelace-Karten-YAML prüfen: es muss `sensor.freematics_one_<erste-8-Zeichen-der-Webhook-ID>` entsprechen.

---

### ❓ F: Die Integration wurde installiert, aber ich sehe keinen „Freematics ONE+"-Eintrag in der Seitenleiste.

**A:** Das Lovelace-Panel wird automatisch registriert, aber möglicherweise muss der **Browser-Cache geleert** werden (Strg+F5 / Cmd+Shift+R) oder das HA-Frontend **neu geladen** werden. Außerdem sicherstellen, dass Home Assistant nach der HACS-Installation neu gestartet wurde.

