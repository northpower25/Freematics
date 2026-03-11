#ifndef CONFIG_H_INCLUDED
#define CONFIG_H_INCLUDED

#ifdef CONFIG_ENABLE_OBD
#define ENABLE_OBD CONFIG_ENABLE_OBD
#endif
#ifdef CONFIG_ENABLE_MEMS
#define ENABLE_MEMS CONFIG_ENABLE_MEMS
#endif
#ifdef CONFIG_GNSS
#define GNSS CONFIG_GNSS
#endif
#ifdef CONFIG_STORAGE
#define STORAGE CONFIG_STORAGE
#endif
#ifdef CONFIG_BOARD_HAS_PSRAM
#define BOARD_HAS_PSRAM 1
#endif
#ifdef CONFIG_ENABLE_WIFI
#define ENABLE_WIFI CONFIG_ENABLE_WIFI
#define WIFI_SSID CONFIG_WIFI_SSID
#define WIFI_PASSWORD CONFIG_WIFI_PASSWORD
#endif
#ifdef CONFIG_ENABLE_BLE
#define ENABLE_BLE CONFIG_ENABLE_BLE
#endif
#ifdef CONFIG_ENABLE_HTTPD
#define ENABLE_HTTPD CONFIG_ENABLE_HTTPD
#endif
#ifdef CONFIG_SERVER_HOST
#define SERVER_HOST CONFIG_SERVER_HOST
#define SERVER_PORT CONFIG_SERVER_PORT
#define SERVER_PROTOCOL CONFIG_SERVER_PROTOCOL
#endif
#ifdef CONFIG_CELL_APN
#define CELL_APN CONFIG_CELL_APN
#endif

/**************************************
* Circular Buffer Configuration
**************************************/
#if BOARD_HAS_PSRAM
#define BUFFER_SLOTS 1024 /* max number of buffer slots */
#define BUFFER_LENGTH 384 /* bytes per slot */
#define SERIALIZE_BUFFER_SIZE 4096 /* bytes */
#else
#define BUFFER_SLOTS 32 /* max number of buffer slots */
#define BUFFER_LENGTH 256 /* bytes per slot */
#define SERIALIZE_BUFFER_SIZE 1024 /* bytes */
#endif

/**************************************
* Configuration Definitions
**************************************/
#define STORAGE_NONE 0
#define STORAGE_SPIFFS 1
#define STORAGE_SD 2

#define GNSS_NONE 0
#define GNSS_STANDALONE 1
#define GNSS_CELLULAR 2

#define PROTOCOL_UDP 1
#define PROTOCOL_HTTPS_GET 2
#define PROTOCOL_HTTPS_POST 3

/**************************************
* OBD-II configurations
**************************************/
#ifndef ENABLE_OBD
#define ENABLE_OBD 1
#endif

// maximum consecutive OBD access errors before entering standby
// Set to a high value so that a temporarily unreachable ECU does not
// permanently disconnect OBD-II.  The process() loop already retries
// obd.init() every 30 s when STATE_OBD_READY is clear, so a hard cap
// is rarely needed.
#define MAX_OBD_ERRORS 999

/**************************************
* Networking configurations
**************************************/
#ifndef ENABLE_WIFI
#define ENABLE_WIFI 1
#endif
// WiFi compile-time defaults (SSID/password are overridden at runtime via NVS)
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

// cellular network settings
#ifndef CELL_APN
#define CELL_APN ""
#endif

// Server settings – defaults to Freematics Hub over UDP.
// Override via build_flags to target a custom server (e.g. Home Assistant
// with PROTOCOL_HTTPS_POST=3 and an empty SERVER_HOST to be provisioned at
// runtime via NVS / config_nvs.bin).
#ifndef SERVER_HOST
#define SERVER_HOST "hub.freematics.com"
#endif
#ifndef SERVER_PROTOCOL
#define SERVER_PROTOCOL PROTOCOL_UDP
#endif

// SIM card setting
#define SIM_CARD_PIN ""
#define APN_USERNAME NULL
#define APN_PASSWORD NULL

// HTTPS settings
#define SERVER_PATH "/hub/api"

#if !SERVER_PORT
#undef SERVER_PORT
#if SERVER_PROTOCOL == PROTOCOL_UDP
#define SERVER_PORT 8081
#else
#define SERVER_PORT 443
#endif
#endif

// WiFi Mesh settings
#define WIFI_MESH_ID "123456"
#define WIFI_MESH_CHANNEL 13

// WiFi AP settings
#define WIFI_AP_SSID "TELELOGGER"
#define WIFI_AP_PASSWORD "PASSWORD"

// WiFi station join timeout – allow enough time for DHCP lease acquisition
#define WIFI_JOIN_TIMEOUT 15000 /* ms */
// maximum consecutive communication errors before resetting network
#define MAX_CONN_ERRORS_RECONNECT 10
// maximum allowed connecting time
#define MAX_CONN_TIME 10000 /* ms */
// data receiving timeout
#define DATA_RECEIVING_TIMEOUT 5000 /* ms */
// expected maximum server sync signal interval
#define SERVER_SYNC_INTERVAL 120 /* seconds, 0 to disable */
// data interval settings
#define STATIONARY_TIME_TABLE {10, 60, 180} /* seconds */
#define DATA_INTERVAL_TABLE {1000, 2000, 5000} /* ms */
#define PING_BACK_INTERVAL 900 /* seconds */
#define SIGNAL_CHECK_INTERVAL 10 /* seconds */

/**************************************
* Data storage configurations
**************************************/
#ifndef STORAGE
// change the following line to change storage type
#define STORAGE STORAGE_SD
#endif

/**************************************
* MEMS sensors
**************************************/
#ifndef ENABLE_MEMS
#define ENABLE_MEMS 1
#endif

/**************************************
* GPS
**************************************/
#ifndef GNSS
// change the following line to change GNSS setting
#define GNSS GNSS_STANDALONE
#endif
// keeping GNSS power on during standby (recommended: set to 1 so the GPS
// receiver maintains its almanac/ephemeris and achieves a faster fix after
// the device wakes up from standby mode)
#define GNSS_ALWAYS_ON 1
// GNSS reset timeout while no signal
#define GNSS_RESET_TIMEOUT 300 /* seconds */

/**************************************
* Standby/wakeup
**************************************/
// motion threshold for waking up
#define MOTION_THRESHOLD 0.4f /* vehicle motion threshold in G */
// engine jumpstart voltage for waking up (when MEMS unavailable) 
#define JUMPSTART_VOLTAGE 14 /* V */
// reset device after waking up
#define RESET_AFTER_WAKEUP 1

/**************************************
* Additional features
**************************************/
#define PIN_SENSOR1 34
#define PIN_SENSOR2 26

#define COOLING_DOWN_TEMP 75 /* celsius degrees */

// enable(1)/disable(0) http server
// Defaults to 1 (enabled) so that OTA firmware updates via WiFi work out of
// the box.  The runtime value is overridden by the NVS key ENABLE_HTTPD when
// the device has been provisioned by the HA integration (config_nvs.bin).
#ifndef ENABLE_HTTPD
#define ENABLE_HTTPD 1
#endif

// Firmware version string – bumped manually on significant releases.
// Printed at boot alongside the __DATE__/__TIME__ build timestamp so users
// can confirm they are running the expected build.
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "5.1"
#endif

// enable(1)/disable(0) BLE SPP server (for Freematics Controller App).
#ifndef ENABLE_BLE
#define ENABLE_BLE 1
#endif


#endif // CONFIG_H_INCLUDED
