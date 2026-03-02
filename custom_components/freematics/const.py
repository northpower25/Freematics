"""Constants for the Freematics ONE+ integration."""

DOMAIN = "freematics"
CONF_WEBHOOK_ID = "webhook_id"

# JSON payload keys sent by the firmware -> (friendly name, unit, device class, state class)
SENSOR_DEFINITIONS = {
    "speed":          ("Speed",              "km/h",   "speed",       "measurement"),
    "rpm":            ("RPM",                "rpm",    None,          "measurement"),
    "throttle":       ("Throttle",           "%",      None,          "measurement"),
    "engine_load":    ("Engine Load",        "%",      None,          "measurement"),
    "coolant_temp":   ("Coolant Temperature","°C",     "temperature", "measurement"),
    "intake_temp":    ("Intake Temperature", "°C",     "temperature", "measurement"),
    "fuel_pressure":  ("Fuel Pressure",      "kPa",    "pressure",    "measurement"),
    "timing_advance": ("Timing Advance",     "°",      None,          "measurement"),
    "lat":            ("GPS Latitude",       "°",      None,          "measurement"),
    "lng":            ("GPS Longitude",      "°",      None,          "measurement"),
    "alt":            ("GPS Altitude",       "m",      None,          "measurement"),
    "gps_speed":      ("GPS Speed",          "km/h",   "speed",       "measurement"),
    "heading":        ("GPS Heading",        "°",      None,          "measurement"),
    "satellites":     ("GPS Satellites",     None,     None,          "measurement"),
    "hdop":           ("GPS HDOP",           None,     None,          "measurement"),
    "acc_x":          ("Accelerometer X",    "m/s²",   None,          "measurement"),
    "acc_y":          ("Accelerometer Y",    "m/s²",   None,          "measurement"),
    "acc_z":          ("Accelerometer Z",    "m/s²",   None,          "measurement"),
    "battery":        ("Battery Voltage",    "V",      "voltage",     "measurement"),
    "signal":         ("Signal Strength",    "dBm",    "signal_strength", "measurement"),
    "device_temp":    ("Device Temperature", "°C",     "temperature", "measurement"),
}
