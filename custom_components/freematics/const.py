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

# OBD-II polling control (maps to OBD_EN NVS key, u8 0/1).
# When enabled (default) the firmware polls standard OBD-II PIDs such as
# speed, RPM, throttle, and engine load.  Disable to suppress OBD queries
# (e.g. when no OBD-II vehicle is connected or to reduce ECU bus load).
CONF_OBD_EN = "obd_en"

# CAN bus control (maps to CAN_EN NVS key, u8 0/1).
# Reserved for future CAN bus sniffing support.  Defaults to disabled.
CONF_CAN_EN = "can_en"

# Standby-time override (maps to STANDBY_TIME NVS key, u16, seconds 5-900).
# The device enters standby after this many seconds of no motion.
# 0 means "use firmware compile-time default" (currently 180 s).
CONF_STANDBY_TIME_S = "standby_time_s"
DEFAULT_STANDBY_TIME_S = 180  # matches STATIONARY_TIME_TABLE last entry

# Deep standby mode (maps to DEEP_STANDBY NVS key, u8, 0=off 1=on).
# When enabled the device uses ESP32 deep sleep during standby, cutting power
# consumption further.  The device restarts fully on wake-up.
CONF_DEEP_STANDBY = "deep_standby"
DEFAULT_DEEP_STANDBY = False

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
    "81":  ("signal",           1.0),   # PID_CSQ: signal strength (dBm)
    "82":  ("device_temp",     1.0),   # PID_DEVICE_TEMP (°C)
    "84":  ("led_white_state", 1.0),   # PID_LED_WHITE_STATE: 1=on, 0=off (runtime enableLedWhite)
    "85":  ("beep_state",      1.0),   # PID_BEEP_STATE: 1=on, 0=off (runtime enableBeep)
    "86":  ("sd_total_mb",     1.0),   # PID_SD_TOTAL_MB: SD total capacity in MiB (0 = no card)
    "87":  ("sd_free_mb",      1.0),   # PID_SD_FREE_MB: SD free space in MiB
    "88":  ("conn_type",       1.0),   # PID_CONN_TYPE: active transport (1=WiFi, 2=Cellular/LTE)
    "89":  ("obd_state",       1.0),   # PID_OBD_STATE: 1=OBD polling active, 0=disabled
    "8A":  ("can_state",       1.0),   # PID_CAN_STATE: 1=CAN bus active, 0=disabled
    "8B":  ("standby_time_device", 1.0), # PID_STANDBY_TIME: standby timeout in seconds (0=firmware default)
    "8C":  ("deep_standby_device", 1.0), # PID_DEEP_STANDBY: 1=deep sleep on standby, 0=disabled
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

# PID_CONN_TYPE (0x88) values – active transport reported by the firmware.
# These match the raw byte sent by the firmware (scale factor 1.0 → float after parsing).
PID_CONN_TYPE_WIFI     = 1.0  # active transport is WiFi (STATE_WIFI_CONNECTED)
PID_CONN_TYPE_CELLULAR = 2.0  # active transport is cellular / LTE (SIM7600)

# Settings version: UTC ISO 8601 timestamp of the last config/options save that
# changed NVS-relevant settings.  Combined with FIRMWARE_VERSION to form the
# "effective OTA version" used by PULL-OTA so the device re-downloads and
# re-applies NVS settings whenever the user updates WiFi, LED, BLE, etc.
# Format example: "2026-03-13T14:23:34+00:00"
CONF_SETTINGS_VERSION = "settings_version"

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
DEFAULT_OTA_MODE  = OTA_MODE_PULL  # Pull-OTA enabled by default so fresh serial flashes
                                   # always have an OTA token in NVS and can receive
                                   # firmware updates over the air without re-flashing.

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
# Pull-OTA provisioning commands (firmware v5.1+ with NVS-over-HTTP support).
# These commands update the device's NVS in real time so OTA can be enabled
# on a device that was flashed without a provisioned OTA token in NVS.
CMD_OTA_TOKEN    = "OTA_TOKEN={}"
CMD_OTA_HOST     = "OTA_HOST={}"
CMD_OTA_INTERVAL = "OTA_INTERVAL={}"
# LED / buzzer runtime control.  Values are 1 (enable) or 0 (disable).
# Changes take effect immediately AND are persisted to NVS so they survive reboot.
CMD_LED_WHITE = "LED_WHITE={}"
CMD_LED_RED   = "LED_RED={}"
CMD_BEEP      = "BEEP={}"
# OBD / CAN / standby-time runtime control.
# Values for OBD and CAN are 1 (enable) or 0 (disable).
# STANDBY_TIME value is in seconds (5-900; 0 = use firmware default 180 s).
# Changes take effect immediately AND are persisted to NVS so they survive reboot.
CMD_OBD          = "OBD={}"
CMD_CAN          = "CAN={}"
CMD_STANDBY_TIME = "STANDBY_TIME={}"
CMD_DEEP_STANDBY = "DEEP_STANDBY={}"
# Query commands – read current live device NVS state.
# Device returns "1" / "0" for boolean states, the numeric value for STANDBY_TIME,
# and raw CAN frame data (newline-separated) for CAN_DATA.
# Older firmware versions return "ERR" for unrecognised commands.
CMD_OBD_QUERY           = "OBD?"
CMD_CAN_QUERY           = "CAN?"
CMD_STANDBY_TIME_QUERY  = "STANDBY_TIME?"
CMD_DEEP_STANDBY_QUERY  = "DEEP_STANDBY?"
CMD_CAN_DATA            = "CAN_DATA?"
