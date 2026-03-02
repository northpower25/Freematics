"""Constants for the Freematics ONE+ integration."""

DOMAIN = "freematics"
CONF_WEBHOOK_ID = "webhook_id"

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
FLASH_METHOD_WIFI = "wifi"

CONF_SERIAL_PORT = "serial_port"
DEFAULT_SERIAL_BAUD = 921600

# Firmware version
FIRMWARE_VERSION = "5.0"

# Signal that carries incoming webhook data
SIGNAL_DATA_RECEIVED = f"{DOMAIN}_data_received"

# Dispatcher signal prefix for webhook data
DISPATCHER_PREFIX = DOMAIN

# JSON payload keys sent by the firmware → (friendly name, unit, device class, state class)
SENSOR_DEFINITIONS = {
    "speed":          ("Speed",               "km/h",  "speed",            "measurement"),
    "rpm":            ("RPM",                 "rpm",   None,               "measurement"),
    "throttle":       ("Throttle",            "%",     None,               "measurement"),
    "engine_load":    ("Engine Load",         "%",     None,               "measurement"),
    "coolant_temp":   ("Coolant Temperature", "°C",    "temperature",      "measurement"),
    "intake_temp":    ("Intake Temperature",  "°C",    "temperature",      "measurement"),
    "fuel_pressure":  ("Fuel Pressure",       "kPa",   "pressure",         "measurement"),
    "timing_advance": ("Timing Advance",      "°",     None,               "measurement"),
    "lat":            ("GPS Latitude",        "°",     None,               "measurement"),
    "lng":            ("GPS Longitude",       "°",     None,               "measurement"),
    "alt":            ("GPS Altitude",        "m",     None,               "measurement"),
    "gps_speed":      ("GPS Speed",           "km/h",  "speed",            "measurement"),
    "heading":        ("GPS Heading",         "°",     None,               "measurement"),
    "satellites":     ("GPS Satellites",      None,    None,               "measurement"),
    "hdop":           ("GPS HDOP",            None,    None,               "measurement"),
    "acc_x":          ("Accelerometer X",     "m/s²",  None,               "measurement"),
    "acc_y":          ("Accelerometer Y",     "m/s²",  None,               "measurement"),
    "acc_z":          ("Accelerometer Z",     "m/s²",  None,               "measurement"),
    "battery":        ("Battery Voltage",     "V",     "voltage",          "measurement"),
    "signal":         ("Signal Strength",     "dBm",   "signal_strength",  "measurement"),
    "device_temp":    ("Device Temperature",  "°C",    "temperature",      "measurement"),
}

# Control commands supported by the device HTTP API (/api/control)
CMD_SSID = "SSID={}"
CMD_WIFI_PWD = "WPWD={}"
CMD_APN = "APN={}"
CMD_RESET = "RESET"
CMD_UPTIME = "UPTIME"
