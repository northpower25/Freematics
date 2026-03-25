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
# Limited to 10 to prevent the sensor's state attributes from exceeding
# Home Assistant's 16 384-byte limit (recorder DB performance warning).
DEBUG_HISTORY_SIZE = 10

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
    # Additional standard OBD-II sensors (polled when ECU supports them)
    "intake_map":              ("Intake Manifold Pressure",     "kPa",   "pressure",         "measurement"),
    "maf_flow":                ("MAF Air Flow Rate",            "g/s",   None,               "measurement"),
    "runtime":                 ("Engine Run Time",              "s",     "duration",         "total_increasing"),
    "fuel_level":              ("Fuel Tank Level",              "%",     None,               "measurement"),
    "barometric":              ("Barometric Pressure",          "kPa",   "pressure",         "measurement"),
    "control_module_voltage":  ("Control Module Voltage",       "V",     "voltage",          "measurement"),
    "absolute_engine_load":    ("Absolute Engine Load",         "%",     None,               "measurement"),
    "relative_throttle":       ("Relative Throttle Position",   "%",     None,               "measurement"),
    "ambient_temp":            ("Ambient Air Temperature",      "°C",    "temperature",      "measurement"),
    "accel_pedal_d":           ("Accelerator Pedal Position D", "%",     None,               "measurement"),
    "accel_pedal_e":           ("Accelerator Pedal Position E", "%",     None,               "measurement"),
    "engine_oil_temp":         ("Engine Oil Temperature",       "°C",    "temperature",      "measurement"),
    "ethanol_fuel":            ("Ethanol Fuel Percentage",      "%",     None,               "measurement"),
    "hybrid_battery":          ("Hybrid Battery Remaining",     "%",     "battery",          "measurement"),
    "engine_fuel_rate":        ("Engine Fuel Rate",             "L/h",   None,               "measurement"),
    "rel_accel_pedal":         ("Relative Accel. Pedal",        "%",     None,               "measurement"),
    "odometer":                ("Odometer",                     "km",    "distance",         "total_increasing"),
    "catalyst_temp_b1s1":      ("Catalyst Temp B1S1",           "°C",    "temperature",      "measurement"),
    "catalyst_temp_b2s1":      ("Catalyst Temp B2S1",           "°C",    "temperature",      "measurement"),
    "engine_torque_demanded":  ("Engine Torque Demanded",       "%",     None,               "measurement"),
    "engine_torque_actual":    ("Engine Torque Actual",         "%",     None,               "measurement"),
    "engine_ref_torque":       ("Engine Reference Torque",      "Nm",    None,               "measurement"),
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
    "10B": ("intake_map",             1.0),   # PID_INTAKE_MAP (kPa)
    "110": ("maf_flow",               0.01),  # PID_MAF_FLOW (g/s, raw/100)
    "11F": ("runtime",                1.0),   # PID_RUNTIME (seconds)
    "12F": ("fuel_level",             1.0),   # PID_FUEL_LEVEL (%)
    "133": ("barometric",             1.0),   # PID_BAROMETRIC (kPa)
    "142": ("control_module_voltage", 0.001), # PID_CONTROL_MODULE_VOLTAGE (V, raw/1000)
    "143": ("absolute_engine_load",   1.0),   # PID_ABSOLUTE_ENGINE_LOAD (%)
    "145": ("relative_throttle",      1.0),   # PID_RELATIVE_THROTTLE_POS (%)
    "146": ("ambient_temp",           1.0),   # PID_AMBIENT_TEMP (°C)
    "149": ("accel_pedal_d",          1.0),   # PID_ACC_PEDAL_POS_D (%)
    "14A": ("accel_pedal_e",          1.0),   # PID_ACC_PEDAL_POS_E (%)
    "15C": ("engine_oil_temp",        1.0),   # PID_ENGINE_OIL_TEMP (°C)
    "152": ("ethanol_fuel",           1.0),   # PID_ETHANOL_FUEL (%)
    "15B": ("hybrid_battery",         1.0),   # PID_HYBRID_BATTERY_PERCENTAGE (%)
    "15E": ("engine_fuel_rate",       0.05),  # PID_ENGINE_FUEL_RATE (L/h, raw*0.05)
    "15A": ("rel_accel_pedal",        1.0),   # PID_REL_ACCEL_PEDAL (%)
    "1A6": ("odometer",               0.1),   # PID_ODOMETER (km, raw*0.1)
    "13C": ("catalyst_temp_b1s1",     0.1),   # PID_CATALYST_TEMP_B1S1 (°C = raw*0.1 - 40; -40 offset applied by sensor layer)
    "13D": ("catalyst_temp_b2s1",     0.1),   # PID_CATALYST_TEMP_B2S1 (°C = raw*0.1 - 40; -40 offset applied by sensor layer)
    "161": ("engine_torque_demanded", 1.0),   # PID_ENGINE_TORQUE_DEMANDED (%)
    "162": ("engine_torque_actual",   1.0),   # PID_ENGINE_TORQUE_PERCENTAGE (%)
    "163": ("engine_ref_torque",      1.0),   # PID_ENGINE_REF_TORQUE (Nm)
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

# Vehicle identification configuration keys.
# Stored in the config entry so vehicle-specific OBD2 PIDs can be provisioned
# to the device via NVS.  Optional – devices without a vehicle profile still
# poll all supported standard OBD2 PIDs.
CONF_VEHICLE_MAKE = "vehicle_make"
CONF_VEHICLE_MODEL = "vehicle_model"
CONF_VEHICLE_YEAR_RANGE = "vehicle_year_range"

# ---------------------------------------------------------------------------
# Entity metadata – purpose, data-source, dependency and documentation info
# exposed as extra_state_attributes on every entity so that users can
# discover exactly where each value comes from and what firmware settings
# affect it without leaving Home Assistant.
# ---------------------------------------------------------------------------

_DOCS = "https://github.com/northpower25/Freematics/blob/main/docs/README.md"
_DOCS_SENSORS  = f"{_DOCS}#sensor-entities"
_DOCS_BUTTONS  = f"{_DOCS}#button-entities"
_DOCS_TRACKER  = f"{_DOCS}#device-tracker"
_DOCS_TECH     = f"{_DOCS}#technical-background"
_DOCS_ENTITIES = f"{_DOCS}#entities-reference"

# OBD-II dependency note shared across all OBD sensors.
_OBD_DEP = (
    "OBD-II polling must be enabled (NVS key OBD_EN=1, default on). "
    "The vehicle ECU must support OBD-II service 01."
)

# Metadata for every key in SENSOR_DEFINITIONS.
# Each entry is a dict with the keys:
#   purpose          – what the entity measures / represents
#   data_source      – protocol path from ECU/hardware to HA
#   dependencies     – firmware settings or hardware prerequisites
#   documentation_url – canonical docs anchor
SENSOR_METADATA: dict[str, dict[str, str]] = {
    # ── Core OBD-II PIDs ────────────────────────────────────────────────────
    "speed": {
        "purpose": "Vehicle speed reported by the engine control unit (ECU).",
        "data_source": (
            "OBD-II service 01 PID 0x0D. "
            "Firmware transmits as hex key 0x10D in the webhook JSON payload."
        ),
        "dependencies": _OBD_DEP + " PID 0x0D (Vehicle Speed) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "rpm": {
        "purpose": "Engine crankshaft speed in revolutions per minute.",
        "data_source": (
            "OBD-II service 01 PID 0x0C. "
            "Raw value A*256+B divided by 4 (rpm); firmware hex key 0x10C."
        ),
        "dependencies": _OBD_DEP + " PID 0x0C (Engine RPM) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "throttle": {
        "purpose": "Absolute throttle position as a percentage of fully open.",
        "data_source": (
            "OBD-II service 01 PID 0x11. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x111."
        ),
        "dependencies": _OBD_DEP + " PID 0x11 (Throttle Position) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_load": {
        "purpose": "Calculated engine load as a percentage of maximum torque.",
        "data_source": (
            "OBD-II service 01 PID 0x04. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x104."
        ),
        "dependencies": _OBD_DEP + " PID 0x04 (Calculated Engine Load) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "coolant_temp": {
        "purpose": "Engine coolant temperature in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x05. "
            "Raw byte A minus 40 (°C); firmware hex key 0x105."
        ),
        "dependencies": _OBD_DEP + " PID 0x05 (Coolant Temperature) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "intake_temp": {
        "purpose": "Intake air temperature at the manifold in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x0F. "
            "Raw byte A minus 40 (°C); firmware hex key 0x10F."
        ),
        "dependencies": _OBD_DEP + " PID 0x0F (Intake Air Temperature) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "fuel_pressure": {
        "purpose": "Fuel rail gauge pressure in kilopascals.",
        "data_source": (
            "OBD-II service 01 PID 0x0A. "
            "Raw byte A multiplied by 3 (kPa); firmware hex key 0x10A."
        ),
        "dependencies": _OBD_DEP + " PID 0x0A (Fuel Pressure) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "timing_advance": {
        "purpose": "Ignition timing advance relative to top-dead-centre in degrees.",
        "data_source": (
            "OBD-II service 01 PID 0x0E. "
            "Raw byte A divided by 2 minus 64 (°); firmware hex key 0x10E."
        ),
        "dependencies": _OBD_DEP + " PID 0x0E (Timing Advance) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "short_fuel_trim_1": {
        "purpose": "Short-term fuel trim for bank 1 in percent (negative = lean correction).",
        "data_source": (
            "OBD-II service 01 PID 0x06. "
            "Raw byte A scaled to ±100 %; firmware hex key 0x106."
        ),
        "dependencies": _OBD_DEP + " PID 0x06 (Short-Term Fuel Trim Bank 1) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "long_fuel_trim_1": {
        "purpose": "Long-term fuel trim for bank 1 in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x07. "
            "Raw byte A scaled to ±100 %; firmware hex key 0x107."
        ),
        "dependencies": _OBD_DEP + " PID 0x07 (Long-Term Fuel Trim Bank 1) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "short_fuel_trim_2": {
        "purpose": "Short-term fuel trim for bank 2 in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x08. "
            "Firmware hex key 0x108. Only available on V6/V8 engines with two banks."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x08 (Short-Term Fuel Trim Bank 2) must be supported. "
            "Requires a multi-bank engine."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "long_fuel_trim_2": {
        "purpose": "Long-term fuel trim for bank 2 in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x09. "
            "Firmware hex key 0x109. Only available on V6/V8 engines."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x09 (Long-Term Fuel Trim Bank 2) must be supported. "
            "Requires a multi-bank engine."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    # ── GPS sensors ─────────────────────────────────────────────────────────
    "lat": {
        "purpose": "Current GPS latitude in decimal degrees (WGS-84).",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0A (hex key 'A') in the webhook JSON payload."
        ),
        "dependencies": (
            "GPS module must be active. Firmware NVS key GPS_EN must be 1 (default). "
            "Requires a GPS fix (outdoor or with GPS antenna)."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "lng": {
        "purpose": "Current GPS longitude in decimal degrees (WGS-84).",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0B (hex key 'B') in the webhook JSON payload."
        ),
        "dependencies": (
            "GPS module must be active. Firmware NVS key GPS_EN must be 1 (default). "
            "Requires a GPS fix."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "alt": {
        "purpose": "GPS altitude above the WGS-84 ellipsoid in metres.",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0C (hex key 'C') in the webhook JSON payload."
        ),
        "dependencies": "GPS module active, GPS fix acquired. See lat/lng dependencies.",
        "documentation_url": _DOCS_SENSORS,
    },
    "gps_speed": {
        "purpose": "Vehicle speed derived from GPS Doppler measurement in km/h.",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0D (hex key 'D'), already converted to km/h."
        ),
        "dependencies": (
            "GPS module active, GPS fix acquired. "
            "Independent of OBD-II – reports speed even when OBD is disabled."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "heading": {
        "purpose": "GPS course-over-ground heading in degrees (0° = north, clockwise).",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0E (hex key 'E') in the webhook JSON payload."
        ),
        "dependencies": "GPS module active, GPS fix acquired. See lat/lng dependencies.",
        "documentation_url": _DOCS_SENSORS,
    },
    "satellites": {
        "purpose": "Number of GPS satellites currently used in the position fix.",
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x0F (hex key 'F') in the webhook JSON payload."
        ),
        "dependencies": "GPS module active. Value is 0 when no GPS fix.",
        "documentation_url": _DOCS_SENSORS,
    },
    "hdop": {
        "purpose": (
            "Horizontal Dilution of Precision (HDOP) – lower values indicate better GPS accuracy. "
            "Used by the device tracker to estimate gps_accuracy (HDOP × 5 metres)."
        ),
        "data_source": (
            "Onboard u-blox GPS module. "
            "Firmware custom PID 0x12 (hex key '12') in the webhook JSON payload."
        ),
        "dependencies": "GPS module active. Value is 0 when no GPS fix.",
        "documentation_url": _DOCS_SENSORS,
    },
    # ── Accelerometer ────────────────────────────────────────────────────────
    "acc_x": {
        "purpose": "Lateral (X-axis) acceleration in g-force.",
        "data_source": (
            "Onboard 3-axis accelerometer (MPU-6050). "
            "Firmware PID 0x20 (hex key '20') transmits X;Y;Z as a combined field; "
            "the integration splits it into acc_x, acc_y, acc_z."
        ),
        "dependencies": (
            "Accelerometer hardware present on device. "
            "No NVS configuration required – always active."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "acc_y": {
        "purpose": "Longitudinal (Y-axis) acceleration in g-force.",
        "data_source": (
            "Onboard 3-axis accelerometer (MPU-6050). "
            "Firmware PID 0x20 (hex key '20') transmits X;Y;Z combined; split by integration."
        ),
        "dependencies": "Accelerometer hardware present. See acc_x.",
        "documentation_url": _DOCS_SENSORS,
    },
    "acc_z": {
        "purpose": "Vertical (Z-axis) acceleration in g-force (approx. 1 g at rest).",
        "data_source": (
            "Onboard 3-axis accelerometer (MPU-6050). "
            "Firmware PID 0x20 (hex key '20') transmits X;Y;Z combined; split by integration."
        ),
        "dependencies": "Accelerometer hardware present. See acc_x.",
        "documentation_url": _DOCS_SENSORS,
    },
    # ── Device hardware sensors ──────────────────────────────────────────────
    "battery": {
        "purpose": "Vehicle 12 V battery voltage measured at the OBD-II port in volts.",
        "data_source": (
            "On-device ADC on the OBD connector VBATT pin. "
            "Firmware custom PID 0x24 (hex key '24'); raw value divided by 100 to get volts."
        ),
        "dependencies": (
            "Device powered via OBD-II port. "
            "Independent of OBD protocol – measured even when OBD_EN=0."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "signal": {
        "purpose": "Wireless signal strength in dBm (WiFi RSSI or cellular RSSI).",
        "data_source": (
            "ESP32 WiFi stack or SIM7600 cellular modem. "
            "Firmware custom PID 0x81 (hex key '81') in the webhook JSON payload."
        ),
        "dependencies": (
            "Device connected via WiFi or cellular. "
            "Reflects the transport used for the most recent packet."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "device_temp": {
        "purpose": "Internal ESP32 chip temperature in degrees Celsius.",
        "data_source": (
            "ESP32 internal temperature sensor. "
            "Firmware custom PID 0x82 (hex key '82') in the webhook JSON payload."
        ),
        "dependencies": "No configuration required – always reported by the firmware.",
        "documentation_url": _DOCS_SENSORS,
    },
    # ── Extended OBD-II sensors ──────────────────────────────────────────────
    "intake_map": {
        "purpose": "Absolute intake manifold pressure (MAP) in kilopascals.",
        "data_source": (
            "OBD-II service 01 PID 0x0B. "
            "Raw byte A in kPa; firmware hex key 0x10B."
        ),
        "dependencies": _OBD_DEP + " PID 0x0B (Intake MAP) must be supported by the ECU.",
        "documentation_url": _DOCS_SENSORS,
    },
    "maf_flow": {
        "purpose": "Mass air flow rate measured by the MAF sensor in grams per second.",
        "data_source": (
            "OBD-II service 01 PID 0x10. "
            "Raw value (A*256+B) divided by 100 (g/s); firmware hex key 0x110."
        ),
        "dependencies": _OBD_DEP + " PID 0x10 (MAF Air Flow Rate) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "runtime": {
        "purpose": "Total engine run time since the last ECU power-on in seconds (ever-increasing).",
        "data_source": (
            "OBD-II service 01 PID 0x1F. "
            "Raw value A*256+B (seconds); firmware hex key 0x11F. "
            "State class total_increasing."
        ),
        "dependencies": _OBD_DEP + " PID 0x1F (Run Time Since Engine Start) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "fuel_level": {
        "purpose": "Fuel tank fill level as a percentage of full capacity.",
        "data_source": (
            "OBD-II service 01 PID 0x2F. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x12F."
        ),
        "dependencies": _OBD_DEP + " PID 0x2F (Fuel Tank Level Input) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "barometric": {
        "purpose": "Barometric (absolute atmospheric) pressure in kilopascals.",
        "data_source": (
            "OBD-II service 01 PID 0x33. "
            "Raw byte A in kPa; firmware hex key 0x133."
        ),
        "dependencies": _OBD_DEP + " PID 0x33 (Barometric Pressure) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "control_module_voltage": {
        "purpose": "Supply voltage of the engine control module in volts.",
        "data_source": (
            "OBD-II service 01 PID 0x42. "
            "Raw value (A*256+B) divided by 1000 (V); firmware hex key 0x142."
        ),
        "dependencies": _OBD_DEP + " PID 0x42 (Control Module Voltage) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "absolute_engine_load": {
        "purpose": "Absolute engine load as a percentage (normalised by cylinder displacement).",
        "data_source": (
            "OBD-II service 01 PID 0x43. "
            "Raw value (A*256+B) scaled to 0–100 %; firmware hex key 0x143."
        ),
        "dependencies": _OBD_DEP + " PID 0x43 (Absolute Load Value) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "relative_throttle": {
        "purpose": "Relative (learned) throttle position in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x45. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x145."
        ),
        "dependencies": _OBD_DEP + " PID 0x45 (Relative Throttle Position) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "ambient_temp": {
        "purpose": "Ambient (outside) air temperature from the ECU sensor in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x46. "
            "Raw byte A minus 40 (°C); firmware hex key 0x146."
        ),
        "dependencies": _OBD_DEP + " PID 0x46 (Ambient Air Temperature) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "accel_pedal_d": {
        "purpose": "Accelerator pedal position D in percent (physical pedal sensor).",
        "data_source": (
            "OBD-II service 01 PID 0x49. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x149."
        ),
        "dependencies": _OBD_DEP + " PID 0x49 (Accelerator Pedal Position D) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "accel_pedal_e": {
        "purpose": "Accelerator pedal position E in percent (redundant pedal sensor).",
        "data_source": (
            "OBD-II service 01 PID 0x4A. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x14A."
        ),
        "dependencies": _OBD_DEP + " PID 0x4A (Accelerator Pedal Position E) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_oil_temp": {
        "purpose": "Engine oil temperature in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x5C. "
            "Raw byte A minus 40 (°C); firmware hex key 0x15C."
        ),
        "dependencies": _OBD_DEP + " PID 0x5C (Engine Oil Temperature) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "ethanol_fuel": {
        "purpose": "Ethanol content of the fuel blend in percent (E85 flex-fuel vehicles).",
        "data_source": (
            "OBD-II service 01 PID 0x52. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x152."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x52 (Ethanol Fuel %) must be supported. "
            "Typically only available on flex-fuel vehicles."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "hybrid_battery": {
        "purpose": "Hybrid/EV high-voltage battery state-of-charge in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x5B. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x15B."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x5B (Hybrid Battery Pack Remaining Life) must be supported. "
            "Typically only available on hybrid or electric vehicles."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_fuel_rate": {
        "purpose": "Instantaneous engine fuel consumption rate in litres per hour.",
        "data_source": (
            "OBD-II service 01 PID 0x5E. "
            "Raw value (A*256+B) multiplied by 0.05 (L/h); firmware hex key 0x15E."
        ),
        "dependencies": _OBD_DEP + " PID 0x5E (Engine Fuel Rate) must be supported.",
        "documentation_url": _DOCS_SENSORS,
    },
    "rel_accel_pedal": {
        "purpose": "Relative accelerator pedal position in percent.",
        "data_source": (
            "OBD-II service 01 PID 0x5A. "
            "Raw byte A scaled to 0–100 %; firmware hex key 0x15A."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x5A (Relative Accelerator Pedal Position) must be supported."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "odometer": {
        "purpose": "Vehicle odometer reading in kilometres (ever-increasing total distance).",
        "data_source": (
            "OBD-II service 01 PID 0xA6. "
            "Raw value (A*256*256*256 + B*256*256 + C*256 + D) multiplied by 0.1 (km); "
            "firmware hex key 0x1A6. State class total_increasing."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0xA6 (Odometer) must be supported. "
            "Availability varies widely by manufacturer."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "catalyst_temp_b1s1": {
        "purpose": "Catalytic converter temperature bank 1 sensor 1 in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x3C. "
            "Raw value (A*256+B) multiplied by 0.1 minus 40 (°C); firmware hex key 0x13C."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x3C (Catalyst Temperature Bank 1 Sensor 1) must be supported."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "catalyst_temp_b2s1": {
        "purpose": "Catalytic converter temperature bank 2 sensor 1 in degrees Celsius.",
        "data_source": (
            "OBD-II service 01 PID 0x3D. "
            "Raw value (A*256+B) multiplied by 0.1 minus 40 (°C); firmware hex key 0x13D."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x3D (Catalyst Temperature Bank 2 Sensor 1) must be supported. "
            "Requires a multi-bank engine."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_torque_demanded": {
        "purpose": "Driver-demanded engine torque as a percentage of the reference torque.",
        "data_source": (
            "OBD-II service 01 PID 0x61. "
            "Raw byte A minus 125 (%); firmware hex key 0x161."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x61 (Driver's Demand Engine Torque) must be supported."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_torque_actual": {
        "purpose": "Actual engine torque as a percentage of the reference torque.",
        "data_source": (
            "OBD-II service 01 PID 0x62. "
            "Raw byte A minus 125 (%); firmware hex key 0x162."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x62 (Actual Engine Torque) must be supported."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
    "engine_ref_torque": {
        "purpose": "Engine reference (maximum) torque in newton-metres.",
        "data_source": (
            "OBD-II service 01 PID 0x63. "
            "Raw value A*256+B (Nm); firmware hex key 0x163."
        ),
        "dependencies": (
            _OBD_DEP
            + " PID 0x63 (Engine Reference Torque) must be supported."
        ),
        "documentation_url": _DOCS_SENSORS,
    },
}

# Metadata for non-sensor entities (debug sensor, CAN debug, device tracker, buttons).
DEBUG_SENSOR_METADATA: dict[str, str] = {
    "purpose": (
        "Diagnostic entity that exposes the complete device configuration and runtime state. "
        "Shows active connection type (WiFi / LTE) as state; all other fields are attributes."
    ),
    "data_source": (
        "Combination of: (1) HA config entry options set during setup/options flow, "
        "(2) live device telemetry PIDs 0x81–0x8C received via webhook, "
        "(3) queries to the device HTTP API (/api/control, /api/info) when device IP is set, "
        "and (4) OTA pull-view events from the HA OTA endpoint."
    ),
    "dependencies": (
        "Full diagnostics require a device IP address configured in the integration options "
        "so that HA can query the /api/control and /api/info endpoints. "
        "OTA status fields require OTA mode to be enabled (OTA_MODE_PULL or OTA_MODE_CLOUD)."
    ),
    "documentation_url": _DOCS_ENTITIES,
}

CAN_DEBUG_SENSOR_METADATA: dict[str, str] = {
    "purpose": (
        "Dedicated CAN bus diagnostic entity. "
        "Shows live CAN bus state (active/inactive) as entity state; "
        "captured raw CAN frames and config/live enable flags as attributes."
    ),
    "data_source": (
        "CAN enable configured flag: HA config entry (NVS key CAN_EN). "
        "CAN live state: device telemetry PID 0x8A (hex key '8A') via webhook. "
        "CAN frames: queried from device via /api/control?cmd=CAN_DATA? when device IP is set."
    ),
    "dependencies": (
        "CAN bus sniffing must be enabled (NVS key CAN_EN=1). "
        "Raw frame capture requires device IP configured in integration options. "
        "Firmware v5.1+ required for CAN_DATA? query command."
    ),
    "documentation_url": _DOCS_ENTITIES,
}

DEVICE_TRACKER_METADATA: dict[str, str] = {
    "purpose": (
        "GPS device tracker entity that combines latitude, longitude, altitude and accuracy "
        "into a single HA tracker compatible with the Map card and zone automations."
    ),
    "data_source": (
        "Derives position from sensor entities freematics_<id8>_lat and freematics_<id8>_lng "
        "(see GPS sensor metadata). Subscribes to their state-change events. "
        "GPS accuracy is estimated from the HDOP sensor: accuracy = HDOP × 5 metres."
    ),
    "dependencies": (
        "GPS module active, GPS fix acquired. "
        "Requires freematics_<id8>_lat and freematics_<id8>_lng sensor entities to be populated."
    ),
    "documentation_url": _DOCS_TRACKER,
}

BUTTON_METADATA: dict[str, dict[str, str]] = {
    "flash_serial": {
        "purpose": (
            "Flashes the bundled firmware binary and a freshly generated NVS partition "
            "to the device via USB serial using esptool running on the HA server."
        ),
        "data_source": (
            "Firmware binary: bundled with the integration at "
            "custom_components/freematics/firmware/telelogger.bin. "
            "NVS partition: generated at press time from current config entry options "
            "(WiFi, APN, webhook ID, server host, OTA token, LED/beep/OBD/CAN settings)."
        ),
        "dependencies": (
            "Freematics ONE+ must be connected via USB to the Home Assistant host. "
            "Serial port must be configured in the integration options. "
            "Python packages esptool>=4.7.0 and esp-idf-nvs-partition-gen>=0.2.0 required."
        ),
        "documentation_url": f"{_DOCS}#method-c-serial-usb-via-ha-server",
    },
    "send_config": {
        "purpose": (
            "Pushes the current WiFi, APN, LED, beep and OTA settings from the HA config "
            "entry to a running device via the device HTTP API (/api/control). "
            "Settings take effect immediately and are persisted to device NVS."
        ),
        "data_source": (
            "All values are read from the current HA config entry options at press time. "
            "Sends HTTP commands to the device's /api/control endpoint."
        ),
        "dependencies": (
            "Device IP address must be configured in the integration options. "
            "Device must be reachable on the local network. "
            "Device HTTPD must be enabled (HTTPD_EN=1, default on). "
            "Firmware v5.1+ required for OTA provisioning commands."
        ),
        "documentation_url": f"{_DOCS}#sending-configuration-to-a-running-device",
    },
    "restart": {
        "purpose": "Sends a RESET command to the device via the HTTP API, triggering a reboot.",
        "data_source": (
            "Sends HTTP GET to /api/control?cmd=RESET on the configured device IP:port."
        ),
        "dependencies": (
            "Device IP address must be configured in the integration options. "
            "Device must be reachable on the local network. "
            "Device HTTPD must be enabled."
        ),
        "documentation_url": f"{_DOCS}#sending-configuration-to-a-running-device",
    },
    "publish_cloud_ota": {
        "purpose": (
            "Publishes the bundled firmware binary and version metadata to "
            "/config/www/FreematicsONE/<device_id>/ so the device can download it "
            "via the Cloud OTA (Variant 2) mechanism at its next OTA check interval."
        ),
        "data_source": (
            "Firmware binary: custom_components/freematics/firmware/telelogger.bin. "
            "Published files accessible via /local/FreematicsONE/<device_id>/firmware.bin "
            "and /local/FreematicsONE/<device_id>/version.json using the HA external URL."
        ),
        "dependencies": (
            "OTA mode must be set to 'cloud' (OTA_MODE_CLOUD) in integration options. "
            "An external HA URL must be configured (Nabu Casa or custom domain) so the "
            "device can reach the /local/ path. "
            "OTA token and check interval must be provisioned into device NVS."
        ),
        "documentation_url": f"{_DOCS}#updating-the-firmware",
    },
}
