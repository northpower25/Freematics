This Arduino sketch is developed for [Freematics ONE+](https://freematics.com/products/freematics-one-plus/) to collect vehicle telemetry data from OBD, GPS, motion sensor, to log the data in local storage and to transmit the data to a remote server in real-time. It demonstrates most capabilities of Freematics ONE+ and works well with [Traccar](https://www.traccar.org) GPS tracking platform.

Data Collection
---------------

The sketch collects following data.

* Vehicle OBD data (from OBD port)
* Battery voltage (from OBD port)
* Geolocation data (from internal or external GNSS) 
* Accelerometer and gyroscope data (from internal MEMS motion sensor)
* Cellular or WiFi network signal level
* Device temperature

Collected data are stored in a circular buffer in ESP32's IRAM or PSRAM. When PSRAM is enabled, hours of data can be buffered in case of temporary network outage and transmitted when network connection resumes.
  
Data Transmission
-----------------

Data transmission over UDP and HTTP(s) protocols are implemented for the followings.

* WiFi (ESP32 built-in)
* 3G WCDMA (SIM5360)
* 4G LTE CAT-4 (SIM7600)
* 4G LTE CAT-M (SIM7070)

UDP mode implements a telemetry client for [Freematics Hub](https://hub.freematics.com) and [Traccar](https://www.traccar.org). HTTP(s) mode implements [OsmAnd](https://www.traccar.org/osmand/) protocol with additional data sent as POST payload.

Seamless WiFi and cellular network co-working is implemented. When defined WiFi hotspot is available, data is transmitted via WiFi and cellular module is switched off. When no WiFi hotspot can be reached, cellular module is switched on for data transmission until WiFi hotspot available again.

Home Assistant Integration (no VPN / no port forwarding)
---------------------------------------------------------

A dedicated **Home Assistant webhook protocol** (`PROTOCOL_HA_WEBHOOK`) pushes
vehicle telemetry as JSON directly to your Home Assistant instance.  It is
compatible with both a locally reachable HA instance and the
[Nabu Casa](https://www.nabucasa.com/) cloud remote UI
(`<id>.ui.nabu.casa`) so **no VPN, port forwarding or public IP** is needed.

### Step 1 – Install the custom integration

Copy the `custom_components/freematics` directory from this repository into
your Home Assistant `config/custom_components/` folder and restart HA.

### Step 2 – Add the integration in Home Assistant

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Freematics ONE+** and follow the setup wizard.
3. The wizard will display a **Webhook ID** and the full webhook URL.

   For Nabu Casa users the host is `<id>.ui.nabu.casa`.

### Step 3 – Flash the firmware

Set the following values in [config.h](config.h) (or via `idf.py menuconfig`
under *Telelogger Configuration*):

```c
#define SERVER_PROTOCOL PROTOCOL_HA_WEBHOOK   // select HA webhook protocol
#define SERVER_HOST     "<your-ha-host>"       // e.g. abc123.ui.nabu.casa
#define SERVER_PORT     443
#define HA_WEBHOOK_ID   "<webhook-id-from-ha>"
```

After the firmware boots, the device will start posting JSON telemetry to
`https://<SERVER_HOST>/api/webhook/<HA_WEBHOOK_ID>` every data interval.
Home Assistant will automatically create sensor entities for every telemetry
value (speed, RPM, GPS coordinates, battery voltage, etc.).

### Sensor entities created

| Entity | Unit |
|--------|------|
| Speed | km/h |
| RPM | rpm |
| Throttle | % |
| Engine Load | % |
| Coolant Temperature | °C |
| Intake Temperature | °C |
| Fuel Pressure | kPa |
| GPS Latitude / Longitude | ° |
| GPS Altitude | m |
| GPS Speed | km/h |
| GPS Heading | ° |
| GPS Satellites | — |
| Accelerometer X/Y/Z | m/s² |
| Battery Voltage | V |
| Signal Strength | dBm |
| Device Temperature | °C |

Data Storage
------------

Following types of data storage are supported.

* MicroSD card storage
* ESP32 built-in Flash memory storage (SPIFFS)

BLE & App
---------

A BLE SPP server is implemented in [FreematicsPlus](https://github.com/stanleyhuangyc/Freematics/blob/master/libraries/FreematicsPlus) library. To enable BLE support, change ENABLE_BLE to 1 [config.h](config.h). This will enable remote control and data monitoring via [Freematics Controller App](https://freematics.com/software/freematics-controller/).

Prerequisites
-------------

* Freematics ONE+ [Model A](https://freematics.com/products/freematics-one-plus/), [Model B](https://freematics.com/products/freematics-one-plus-model-b/), [Model H](https://freematics.com/products/freematics-one-plus-model-h/)
* A micro SIM card if cellular network connectivity required
* [PlatformIO](http://platformio.org/), [Arduino IDE](https://github.com/espressif/arduino-esp32#installation-instructions), [Freematics Builder](https://freematics.com/software/arduino-builder) or [ESP-IDF](https://github.com/espressif/esp-idf) for compiling and uploading code
