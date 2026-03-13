"""Constants for the Freematics ONE+ integration."""

DOMAIN = "freematics"
CONF_WEBHOOK_ID = "webhook_id"
# Nabu Casa Cloud Webhook URL (hooks.nabu.casa/<token>) stored in entry.data so
# NVS re-provisioning can use it even when cloud is temporarily offline.
CONF_CLOUD_HOOK_URL = "cloud_hook_url"

# Device connectivity
CONF_CONNECTION_TYPE = "connection_type"
CONN_TYPE_WIFI = "wifi"
CONN_TYPE_CELLULAR = "cellular"
CONN_TYPE_BOTH = "both"

# WiFi settings
CONF_WIFI_SSID = "wifi_ssid"
CONF_WIFI_PASSWORD = "wifi_password"

# Cellular settings
CONF_CELL_APN = "cell_apn"
CONF_SIM_PIN = "sim_pin"

# Device settings
CONF_DEVICE_IP = "device_ip"
CONF_DEVICE_PORT = "device_port"
DEFAULT_DEVICE_PORT = 80

# Flash settings
CONF_FLASH_METHOD = "flash_method"
FLASH_METHOD_SERIAL = "serial"

CONF_SERIAL_PORT = "serial_port"
DEFAULT_SERIAL_BAUD = 921600

# Firmware version
FIRMWARE_VERSION = "5.1"

# Signal that carries incoming webhook data
SIGNAL_DATA_RECEIVED = f"{DOMAIN}_data_received"

# Dispatcher signal prefix for webhook data
DISPATCHER_PREFIX = DOMAIN

# Operating mode – determines which firmware features are enabled
CONF_OPERATING_MODE = "operating_mode"
OPERATING_MODE_TELELOGGER = "telelogger"   # Webhook → HA; HTTPD=on (for OTA), BLE=off
OPERATING_MODE_DATALOGGER = "datalogger"   # local HTTP API; HTTPD=on
DEFAULT_OPERATING_MODE = OPERATING_MODE_TELELOGGER

# Advanced firmware settings stored in NVS and written to the device during flash
CONF_ENABLE_HTTPD = "enable_httpd"
CONF_ENABLE_BLE = "enable_ble"
CONF_DATA_INTERVAL_MS = "data_interval_ms"
CONF_SYNC_INTERVAL_S = "sync_interval_s"
# Enable verbose cellular debug logging (maps to NET_DEBUG / CELL_DEBUG NVS key).
# When enabled, the firmware prints TX-Preview, TX hex-dump, AT+CCHSTATUS? and
# per-packet "Incoming data" lines to the serial console.  Disabled by default
# to keep production serial output clean.
CONF_CELL_DEBUG = "cell_debug"

# LED behaviour control (maps to LED_RED_EN / LED_WHITE_EN NVS keys, u8 0/1).
# LED_RED_EN  – red/power LED: lights up while the device is powered on or in
#               standby (i.e. not actively transmitting).  Default: enabled (1).
# LED_WHITE_EN – white/network LED: lights up during each data-transmission burst
#                over WiFi or cellular.  Default: enabled (1).
# Both can be disabled independently via the config/options flow to reduce
# light pollution in the vehicle cabin.
CONF_LED_RED_EN = "led_red_en"
CONF_LED_WHITE_EN = "led_white_en"

# Beep/buzzer control (maps to BEEP_EN NVS key, u8 0/1).
# When enabled (default) the device emits a short beep on each successful
# WiFi or cellular connection.  Disable to suppress in-cabin noise.
CONF_BEEP_EN = "beep_en"

# Device model identifiers (Freematics ONE+ variants)
CONF_DEVICE_MODEL = "device_model"
DEVICE_MODEL_A = "model_a"   # Model A: WiFi + Bluetooth (no cellular)
DEVICE_MODEL_B = "model_b"   # Model B: WiFi + Bluetooth + 4G cellular
DEVICE_MODEL_H = "model_h"   # Model H: WiFi only (no BT, no cellular)

# Defaults for advanced settings (0 = use firmware compile-time default)
DEFAULT_DATA_INTERVAL_MS = 0    # 0 = firmware default ≈1000 ms
DEFAULT_SYNC_INTERVAL_S = 0     # 0 = firmware default 120 s

# Number of raw webhook payloads to keep in the debug entity's history.
# 5000 entries cover enough history for error analysis (each payload is
# typically < 200 bytes, so the list stays well within Python memory limits).
DEBUG_HISTORY_SIZE = 5000

# JSON payload keys sent by the firmware → (friendly name, unit, device class, state class)
SENSOR_DEFINITIONS = {
    "speed":                ("Speed",                      "km/h",  "speed",            "measurement"),
    "rpm":                  ("RPM",                        "rpm",   None,               "measurement"),
    "throttle":             ("Throttle",                   "%",     None,               "measurement"),
    "engine_load":          ("Engine Load",                "%",     None,               "measurement"),
    "coolant_temp":         ("Coolant Temperature",        "°C",    "temperature",      "measurement"),
    "intake_temp":          ("Intake Temperature",         "°C",    "temperature",      "measurement"),
    "fuel_pressure":        ("Fuel Pressure",              "kPa",   "pressure",         "measurement"),
    "timing_advance":       ("Timing Advance",             "°",     None,               "measurement"),
    "short_fuel_trim_1":    ("Short-Term Fuel Trim B1",    "%",     None,               "measurement"),
    "long_fuel_trim_1":     ("Long-Term Fuel Trim B1",     "%",     None,               "measurement"),
    "short_fuel_trim_2":    ("Short-Term Fuel Trim B2",    "%",     None,               "measurement"),
    "long_fuel_trim_2":     ("Long-Term Fuel Trim B2",     "%",     None,               "measurement"),
    "lat":                  ("GPS Latitude",               "°",     None,               "measurement"),
    "lng":                  ("GPS Longitude",              "°",     None,               "measurement"),
    "alt":                  ("GPS Altitude",               "m",     None,               "measurement"),
    "gps_speed":            ("GPS Speed",                  "km/h",  "speed",            "measurement"),
    "heading":              ("GPS Heading",                "°",     None,               "measurement"),
    "satellites":           ("GPS Satellites",             None,    None,               "measurement"),
    "hdop":                 ("GPS HDOP",                   None,    None,               "measurement"),
    "acc_x":                ("Accelerometer X",            "g",     None,               "measurement"),
    "acc_y":                ("Accelerometer Y",            "g",     None,               "measurement"),
    "acc_z":                ("Accelerometer Z",            "g",     None,               "measurement"),
    "battery":              ("Battery Voltage",            "V",     "voltage",          "measurement"),
    "signal":               ("Signal Strength",            "dBm",   "signal_strength",  "measurement"),
    "device_temp":          ("Device Temperature",         "°C",    "temperature",      "measurement"),
}

# Mapping from Freematics hex PID strings (as printed by %X) to (sensor_key, scale_factor).
#
# The firmware serialises each sample as "PID_HEX:value" pairs separated by
# commas and terminated with "*CHECKSUM".  OBD-II PIDs are sent with the 0x100
# bit set so they don't collide with the custom GPS/device PIDs that share the
# same low-byte values:
#
#   e.g. PID_SPEED (0x0D)  → stored as 0x10D → hex string "10D"
#        PID_GPS_SPEED (0x0D, no 0x100 bit) → hex string "D"
#
# scale_factor: multiply the raw integer value before storing.
#   e.g. PID_BATTERY_VOLTAGE is stored as voltage*100 → scale 0.01 → V

# Type alias for a PID mapping entry: (sensor_key, scale_factor)
_PidMapping = tuple[str, float]

PID_MAP: dict[str, _PidMapping] = {
    # ── Custom / device PIDs (no 0x100 bit) ─────────────────────────
    "0":   ("ts",            1.0),   # PID_TIMESTAMP: uptime ms (skipped by sensor)
    "A":   ("lat",           1.0),   # PID_GPS_LATITUDE
    "B":   ("lng",           1.0),   # PID_GPS_LONGITUDE
    "C":   ("alt",           1.0),   # PID_GPS_ALTITUDE (m)
    "D":   ("gps_speed",     1.0),   # PID_GPS_SPEED (already converted to km/h)
    "E":   ("heading",       1.0),   # PID_GPS_HEADING (°)
    "F":   ("satellites",    1.0),   # PID_GPS_SAT_COUNT
    "10":  ("gps_time",      1.0),   # PID_GPS_TIME (HHMMSS, skipped by sensor)
    "12":  ("hdop",          1.0),   # PID_GPS_HDOP
    "20":  ("acc",           1.0),   # PID_ACC: x;y;z in g (expanded to acc_x/y/z)
    "24":  ("battery",       0.01),  # PID_BATTERY_VOLTAGE: raw/100 → V
    "81":  ("signal",        1.0),   # PID_CSQ: signal strength (dBm)
    "82":  ("device_temp",   1.0),   # PID_DEVICE_TEMP (°C)
    # ── OBD-II PIDs (0x100 bit set by firmware) ──────────────────────
    "104": ("engine_load",        1.0),   # PID_ENGINE_LOAD (%)
    "105": ("coolant_temp",       1.0),   # PID_COOLANT_TEMP (°C)
    "106": ("short_fuel_trim_1",  1.0),   # PID_SHORT_TERM_FUEL_TRIM_1 (%)
    "107": ("long_fuel_trim_1",   1.0),   # PID_LONG_TERM_FUEL_TRIM_1 (%)
    "108": ("short_fuel_trim_2",  1.0),   # PID_SHORT_TERM_FUEL_TRIM_2 (%)
    "109": ("long_fuel_trim_2",   1.0),   # PID_LONG_TERM_FUEL_TRIM_2 (%)
    "10A": ("fuel_pressure",      1.0),   # PID_FUEL_PRESSURE (kPa)
    "10C": ("rpm",                1.0),   # PID_RPM
    "10D": ("speed",              1.0),   # PID_SPEED (km/h)
    "10E": ("timing_advance",     1.0),   # PID_TIMING_ADVANCE (°)
    "10F": ("intake_temp",        1.0),   # PID_INTAKE_TEMP (°C)
    "111": ("throttle",           1.0),   # PID_THROTTLE (%)
}

# OTA pull update configuration
# CONF_OTA_TOKEN: long-lived secret token stored in entry.data/options.  Embedded
# as a path component in the HA pull-OTA endpoint so the device can download
# firmware without HA session credentials.  Provisioned into device NVS as the
# OTA_TOKEN key so the firmware knows its token after the next NVS flash.
CONF_OTA_TOKEN = "ota_token"
# How often (seconds) the device should check the pull-OTA endpoint for new
# firmware.  0 = disabled (default).  Stored as NVS key OTA_INTERVAL (u16).
CONF_OTA_CHECK_INTERVAL_S = "ota_check_interval_s"
DEFAULT_OTA_CHECK_INTERVAL_S = 3600  # check once per hour by default when OTA is enabled

# OTA update mode.
# OTA_MODE_DISABLED – no OTA; device never checks for firmware updates.
# OTA_MODE_PULL     – Variant 1: HA always serves the latest bundled firmware;
#                     the device downloads and flashes whenever HA has a newer
#                     version.  No manual "Publish" step needed.
# OTA_MODE_CLOUD    – Variant 2: HA only offers firmware after the user presses
#                     the "Publish Firmware for Cloud OTA" button, giving full
#                     manual control over when the device receives an update.
CONF_OTA_MODE = "ota_mode"
OTA_MODE_DISABLED = "disabled"
OTA_MODE_PULL     = "pull"
OTA_MODE_CLOUD    = "cloud"
DEFAULT_OTA_MODE  = OTA_MODE_DISABLED  # opt-in; no automatic updates out of the box

# Control commands supported by the device HTTP API (/api/control)
CMD_SSID = "SSID={}"
CMD_WIFI_PWD = "WPWD={}"
CMD_APN = "APN={}"
CMD_SIM_PIN = "PIN={}"
CMD_RESET = "RESET"
CMD_UPTIME = "UPTIME"
# Pause / resume the telemetry task (stops SSL cloud-hook traffic so OTA has
# exclusive access to the WiFi radio and available heap).
CMD_STANDBY = "OFF"
CMD_RESUME = "ON"
CMD_STANDBY_QUERY = "ON?"
