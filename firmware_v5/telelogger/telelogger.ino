/******************************************************************************
* Arduino sketch of a vehicle data data logger and telemeter for Freematics Hub
* Works with Freematics ONE+ Model A and Model B
* Developed by Stanley Huang <stanley@freematics.com.au>
* Distributed under BSD license
* Visit https://freematics.com/products for hardware information
* Visit https://hub.freematics.com to view live and history telemetry data
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
* THE SOFTWARE.
******************************************************************************/

#include <FreematicsPlus.h>
#include <httpd.h>
#include <mbedtls/sha256.h>
#include "config.h"
#include "telestore.h"
#include "teleclient.h"
#if BOARD_HAS_PSRAM
#include "esp32/himem.h"
#endif
#include "driver/adc.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_sleep.h"
#if ENABLE_OLED
#include "FreematicsOLED.h"
#endif
#if ENABLE_WIFI
#include <Update.h>
#endif

// states
#define STATE_STORAGE_READY 0x1
#define STATE_OBD_READY 0x2
#define STATE_GPS_READY 0x4
#define STATE_MEMS_READY 0x8
#define STATE_NET_READY 0x10
#define STATE_GPS_ONLINE 0x20
#define STATE_CELL_CONNECTED 0x40
#define STATE_WIFI_CONNECTED 0x80
#define STATE_WORKING 0x100
#define STATE_STANDBY 0x200

typedef struct {
  byte pid;
  byte tier;
  int value;
  uint32_t ts;
} PID_POLLING_INFO;

PID_POLLING_INFO obdData[]= {
  // Tier 1: polled every cycle (fast-changing: speed, RPM, throttle, load)
  {PID_SPEED, 1},
  {PID_RPM, 1},
  {PID_THROTTLE, 1},
  {PID_ENGINE_LOAD, 1},
  // Tier 2: polled once per two cycles (medium rate)
  {PID_FUEL_PRESSURE, 2},
  {PID_TIMING_ADVANCE, 2},
  {PID_INTAKE_MAP, 2},
  {PID_MAF_FLOW, 2},
  // Tier 3: polled once per many cycles (slow-changing)
  {PID_COOLANT_TEMP, 3},
  {PID_INTAKE_TEMP, 3},
  {PID_SHORT_TERM_FUEL_TRIM_1, 3},
  {PID_LONG_TERM_FUEL_TRIM_1, 3},
  {PID_SHORT_TERM_FUEL_TRIM_2, 3},
  {PID_LONG_TERM_FUEL_TRIM_2, 3},
  {PID_RUNTIME, 3},
  {PID_FUEL_LEVEL, 3},
  {PID_BAROMETRIC, 3},
  {PID_CONTROL_MODULE_VOLTAGE, 3},
  {PID_ABSOLUTE_ENGINE_LOAD, 3},
  {PID_RELATIVE_THROTTLE_POS, 3},
  {PID_AMBIENT_TEMP, 3},
  {PID_ACC_PEDAL_POS_D, 3},
  {PID_ACC_PEDAL_POS_E, 3},
  {PID_ENGINE_OIL_TEMP, 3},
  {PID_ETHANOL_FUEL, 3},
  {PID_HYBRID_BATTERY_PERCENTAGE, 3},
  {PID_ENGINE_FUEL_RATE, 3},
  {PID_REL_ACCEL_PEDAL, 3},
  {PID_ODOMETER, 3},
  // Catalyst temperatures (only supported on petrol engines)
  {PID_CATALYST_TEMP_B1S1, 3},
  {PID_CATALYST_TEMP_B2S1, 3},
  {PID_ENGINE_TORQUE_DEMANDED, 3},
  {PID_ENGINE_TORQUE_PERCENTAGE, 3},
  {PID_ENGINE_REF_TORQUE, 3},
};

CBufferManager bufman;
Task subtask;

#if ENABLE_MEMS
float accBias[3] = {0}; // calibrated reference accelerometer data
float accSum[3] = {0};
float acc[3] = {0};
float gyr[3] = {0};
float mag[3] = {0};
uint8_t accCount = 0;
#endif
int deviceTemp = 0;

// config data
char apn[32];
char simPin[16] = SIM_CARD_PIN;
#if ENABLE_WIFI
char wifiSSID[32] = WIFI_SSID;
char wifiPassword[32] = WIFI_PASSWORD;
#endif
// Server settings – loaded from NVS at boot; fall back to compile-time defaults.
// Set via NVS keys SERVER_HOST, SERVER_PORT, WEBHOOK_PATH using the
// Freematics HA integration provisioning flash (config_nvs.bin).
char serverHost[128] = SERVER_HOST;
uint16_t serverPort = SERVER_PORT;
// WEBHOOK_PATH overrides the legacy /hub/api/post/<devid> path when set.
// Nabu Casa cloud hook paths are ~185 characters; 256 bytes ensures they fit.
char webhookPath[256] = "";
// Cellular-specific server overrides (NVS keys CELL_HOST, CELL_PORT, CELL_PATH).
// When non-empty, these replace SERVER_HOST / SERVER_PORT / WEBHOOK_PATH for
// cellular (SIM7600) connections.  Set to hooks.nabu.casa + the Nabu Casa
// cloud-hook token path by the HA integration when Nabu Casa cloud is active,
// so that cellular devices reach the cloud webhook endpoint directly rather than
// the Remote UI proxy (*.ui.nabu.casa) which the SIM7600 TLS stack cannot use.
// WiFi connections use SERVER_HOST / WEBHOOK_PATH, which the HA integration sets
// from get_url(prefer_external=True) – typically *.ui.nabu.casa (Nabu Casa Remote
// UI).  Using the Remote UI for WiFi ensures WiFi telemetry and WiFi OTA (which
// always uses *.ui.nabu.casa) share the same TLS session, avoiding mbedTLS heap
// fragmentation from repeated TLS host switching on the ESP32.
char cellServerHost[128] = "";
uint16_t cellServerPort = 443;
char cellWebhookPath[256] = "";
// Runtime HTTP server enable.  Defaults to the compile-time ENABLE_HTTPD value
// (1 = on) so OTA firmware updates via WiFi work without requiring NVS
// provisioning.  Can be overridden by NVS key ENABLE_HTTPD written by the HA
// integration config_nvs.bin.  Only takes effect when compiled with ENABLE_HTTPD=1.
uint8_t enableHttpd = ENABLE_HTTPD;
// Runtime BLE enable – set to 0 via NVS key ENABLE_BLE to disable the BLE
// SPP server and free ~100 KB heap for the TLS webhook client.  Defaults to
// 1 (on) so devices that were never provisioned keep the previous behaviour.
// Only takes effect when the firmware is compiled with ENABLE_BLE=1.
uint8_t enableBle = 1;
nvs_handle_t nvs;
// NVS settings version string (NVS_VER key): written by the HA integration
// when generating the NVS partition so the firmware can report which settings
// are active.  Format: "<FIRMWARE_VERSION>.<settings_timestamp>" e.g.
// "5.1.2026-03-16T16:11:20+00:00".  Empty when NVS was not provisioned by HA.
char nvsVersion[64] = "";

// ---------------------------------------------------------------------------
// Pull-OTA configuration (loaded from NVS by loadConfig(), firmware v5.2+).
// When otaToken is non-empty the firmware periodically GETs
//   https://{otaHost}:{otaPort}/api/freematics/ota_pull/{otaToken}/meta.json
// and downloads / flashes a newer firmware version when one is available.
// ---------------------------------------------------------------------------
// Secret path token provisioned by the HA integration (OTA_TOKEN NVS key).
// Embedded as a URL path component so no Authorization header is needed.
char otaToken[68] = "";   // 64 hex chars + null; empty = feature disabled
// HA server hostname for pull-OTA (OTA_HOST NVS key).  May differ from
// serverHost when Nabu Casa cloud is active (serverHost would be
// hooks.nabu.casa which does not serve the pull-OTA endpoint).
char otaHost[128] = "";
uint16_t otaPort = 443;   // OTA_PORT NVS key (u16)
// Interval between pull-OTA checks in seconds.  0 = disabled (default).
uint16_t otaCheckIntervalS = 0;  // OTA_INTERVAL NVS key (u16)

// live data
String netop;
String ip;
int16_t rssi = 0;
int16_t rssiLast = 0;
char vin[18] = {0};
uint16_t dtc[6] = {0};
float batteryVoltage = 0;
GPS_DATA* gd = 0;

char devid[12] = {0};
char isoTime[32] = {0};

// stats data
uint32_t lastMotionTime = 0;
uint32_t timeoutsOBD = 0;
uint32_t timeoutsNet = 0;
uint32_t lastStatsTime = 0;

int32_t syncInterval = SERVER_SYNC_INTERVAL * 1000;
int32_t dataInterval = 1000;

#if STORAGE != STORAGE_NONE
int fileid = 0;
uint16_t lastSizeKB = 0;
#endif

byte ledMode = 0;

// Runtime LED / buzzer enable flags.  All default to true (on) so that
// un-provisioned devices preserve the original hardware behaviour.
// Set via NVS keys LED_RED_EN, LED_WHITE_EN, and BEEP_EN (u8, 0=off 1=on).
bool enableLedRed = true;    // red/power LED: lights up in standby / power-on state
bool enableLedWhite = true;  // white/network LED: lights up during data transmission
bool enableBeep = true;      // connection beep: short buzz on WiFi/cellular connect

// Runtime OBD / CAN enable flags.  Loaded from NVS by loadConfig().
// OBD defaults to true so un-provisioned devices keep the existing behaviour.
// CAN defaults to false (no CAN sniffing by default).
// Set via NVS keys OBD_EN and CAN_EN (u8, 0=off 1=on).
bool enableObd = true;   // OBD-II PID polling (compile-time ENABLE_OBD must also be 1)
bool enableCan = false;  // CAN bus sniffing (future use; NVS key CAN_EN)

// Deep-standby flag.  When true the device uses ESP32 deep sleep during
// standby instead of the normal active-wait loop.  Loaded from NVS key
// DEEP_STANDBY (u8, 0=off 1=on).  Defaults to false.
bool enableDeepStandby = false;

// Vehicle identification loaded from NVS (VEHICLE_MAKE, VEHICLE_MODEL, VEHICLE_YEAR).
// Stored for informational purposes and future vehicle-specific PID selection.
char vehicleMake[32] = "";
char vehicleModel[32] = "";
char vehicleYear[8] = "";
// Vehicle-specific extra PIDs (VEHICLE_PIDS NVS key).
// Comma-separated list of mode-1 PID hex values, e.g. "22,23,5A".
// The firmware parses this at startup and appends those PIDs to the dynamic poll list.
char vehiclePidsStr[128] = "";
// Runtime dynamic vehicle PID poll list (parsed from vehiclePidsStr).
#define MAX_VEHICLE_PIDS 16
PID_POLLING_INFO vehicleObdData[MAX_VEHICLE_PIDS];
int vehicleObdDataCount = 0;

// Standby-time override loaded from NVS key STANDBY_TIME (u16, seconds).
// 0 means "use the compile-time STATIONARY_TIME_TABLE default" (currently 180 s).
// When set to a value between 5 and 900 it replaces the last (maximum) entry
// of the stationary-time table so the device enters standby sooner.
uint16_t nvsStandbyTimeS = 0;

// ---------------------------------------------------------------------------
// CAN bus sniffing buffer
// When enableCan is true, process() calls obd.receiveData() to drain incoming
// CAN frames from the ELM327's monitor-all (ATM1) queue and appends each
// frame's bytes as a two-hex-chars-per-byte entry in s_canFrameList.
// The list is exposed via /api/control?cmd=CAN_DATA and cleared when read.
// ---------------------------------------------------------------------------
#define CAN_DATA_LIST_MAX 32    // maximum number of stored CAN frame snapshots
// Ring buffer storing hex-encoded CAN frame payloads, newest last.
// Each entry is at most 2*8=16 chars (8 data bytes × 2 hex digits).
// The buffer is guarded by s_canBufMux for cross-task access from dataserver.
char   s_canFrameList[CAN_DATA_LIST_MAX][20];
int    s_canFrameCount = 0;   // number of valid entries (0 … CAN_DATA_LIST_MAX)
uint32_t s_canFrameTotal = 0; // total CAN frames seen since boot (for display)
portMUX_TYPE s_canBufMux = portMUX_INITIALIZER_UNLOCKED;
// Tracks whether sniffing is currently active so we can call sniff(true/false)
// only on transitions rather than every process() call.
static bool s_canSniffActive = false;

// Set to true by handlerOTA while an OTA flash is in progress.
// The telemetry task checks this flag and yields the WiFi to the OTA upload.
volatile bool s_ota_active = false;

// SD card paths for the two-phase pull-OTA staging mechanism (STORAGE_SD only).
// Phase 1 (during active telemetry): firmware is downloaded to OTA_PENDING_PATH.
// Phase 2 (at next standby transition): firmware is flashed from SD to flash.
// OTA_META_PATH stores the expected byte count so partial downloads can be
// detected and removed at startup without attempting a corrupt flash.
#define OTA_PENDING_PATH "/ota_fw.bin"    // staged firmware binary
#define OTA_META_PATH    "/ota_meta.txt"  // companion: expected byte count (decimal)
#define OTA_NVS_PATH     "/ota_nvs.bin"   // staged NVS settings binary (optional)

// Set by performPullOtaCheck() when a firmware has been fully downloaded to SD.
// Cleared by performPullOtaFlash() on success or unrecoverable error.
// Also set at startup when a previously staged file is found on SD.
static volatile bool s_ota_pending = false;

// Sentinel values for the LED/beep runtime-state PIDs (0x84 / 0x85), the
// connection-type PID (0x88), and the OBD/CAN/standby PIDs (0x89/0x8a/0x8b).
// Initialised to -1 so the first call to process()
// always adds the PIDs to the buffer.  Reset back to -1 by initialize() and
// whenever a new WiFi or cellular connection is established (in telemetry()), so
// the current state is always re-sent after a reconnect — preventing a permanent
// "Unbekannt" IST-Status in Home Assistant when HA is reloaded while the device
// is connected (HA loses diag state but device won't resend unchanged values
// unless the sentinels are reset).
static int8_t s_lastLedWhite = -1;
static int8_t s_lastBeep     = -1;
static int8_t s_lastConnType = -1;  // PID_CONN_TYPE sentinel: 1=WiFi, 2=Cellular
static int8_t  s_lastObd         = -1;   // PID_OBD_STATE sentinel
static int8_t  s_lastCan         = -1;   // PID_CAN_STATE sentinel
static int16_t s_lastStandbyTime = -1;   // PID_STANDBY_TIME sentinel (seconds)
static int8_t  s_lastDeepStandby = -1;   // PID_DEEP_STANDBY sentinel

// Inject-on-next-packet flag: set whenever the sentinels are reset (new
// connection established or session start).  The telemetry task checks this
// flag and injects LED/beep/conn-type/SD PIDs directly into the outgoing
// CStorage packet before store.tailer(), guaranteeing these IST-Status values
// are in the FIRST transmitted packet regardless of which buffer getNewest()
// picks up.  Without this, a race between process() (updating sentinels and
// filling buffers) and the telemetry loop (slow OTA check over cellular delays
// getNewest()) causes the sentinel-triggered buffer to be overwritten before it
// is transmitted — leaving HA with "Unbekannt" for LED/beep/SD indefinitely.
static volatile bool s_send_state_pids = false;

// Cached SD card capacity/free space (MiB) — updated by process() each time it
// emits PID_SD_TOTAL_MB / PID_SD_FREE_MB.  Read (not written) by the telemetry
// inject block so it does not need to access the SD SPI bus from the wrong task.
static uint32_t s_cachedSdTotalMb = 0;
static uint32_t s_cachedSdFreeMb  = 0;

// Pull-OTA constants used in initialize(), standby(), performPullOtaFlash(),
// and performPullOtaCheck().  Defined here (before any function body) so that
// all translation-unit uses see them regardless of source order.
// Minimum plausible firmware binary size — rejects short error pages returned
// instead of the real binary.
#define PULL_OTA_MIN_FW_SIZE       65536U   // 64 KB
// Chunk size for SD download and SD→flash write loops.
#define PULL_OTA_CHUNK_SIZE        4096U    // 4 KB
// Per-chunk receive timeout when streaming from the network socket.
#define PULL_OTA_CHUNK_TIMEOUT_MS  30000U   // 30 s
// Delay after setting s_ota_active to let the telemetry task yield its SSL
// connections before Update.begin() allocates flash partition memory.
#define OTA_TELEMETRY_YIELD_DELAY_MS 1000U

// Shared chunk buffer used by the download (to SD) and flash (from SD) phases.
// File-scope static so both functions share one allocation.
static uint8_t s_otaChunkBuf[PULL_OTA_CHUNK_SIZE];

bool serverSetup(IPAddress& ip);
void serverProcess(int timeout);
void processMEMS(CBuffer* buffer);
bool processGPS(CBuffer* buffer);
void processBLE(int timeout);
#if STORAGE == STORAGE_SD
// Forward declaration: defined in the Pull-OTA section below.
static bool performPullOtaFlash();
#endif

class State {
public:
  bool check(uint16_t flags) { return (m_state & flags) == flags; }
  void set(uint16_t flags) { m_state |= flags; }
  void clear(uint16_t flags) { m_state &= ~flags; }
  uint16_t m_state = 0;
};

FreematicsESP32 sys;

class OBD : public COBD
{
protected:
  void idleTasks()
  {
    // do some quick tasks while waiting for OBD response
#if ENABLE_MEMS
    processMEMS(0);
#endif
    processBLE(0);
  }
};

OBD obd;

MEMS_I2C* mems = 0;

#if STORAGE == STORAGE_SPIFFS
SPIFFSLogger logger;
#elif STORAGE == STORAGE_SD
SDLogger logger;
#endif

#if SERVER_PROTOCOL == PROTOCOL_UDP
TeleClientUDP teleClient;
#else
TeleClientHTTP teleClient;
#endif

#if ENABLE_OLED
OLED_SH1106 oled;
#endif

State state;

// ---------------------------------------------------------------------------
// Volatile request flags set by the httpd task (handlerControl) to request
// telemetry state changes.  All actual state.m_state modifications are
// applied by the net task at the top of its main loop so that m_state is
// always written from a single task context — same thread-safety pattern
// as s_ota_active.
// ---------------------------------------------------------------------------
static volatile bool s_http_standby_enter = false;
static volatile bool s_http_standby_exit  = false;


// Called from handlerControl (httpd task) to pause or resume the telemetry task.
void httpControlStandby(bool enter) {
    if (enter) {
        s_http_standby_enter = true;
        s_http_standby_exit  = false;
    } else {
        s_http_standby_exit  = true;
        s_http_standby_enter = false;
    }
}

// Returns true when the telemetry task is in (or has been requested to enter)
// standby mode.  Called from handlerControl to answer "ON?" queries.
bool httpIsStandby() {
    return state.check(STATE_STANDBY) || s_http_standby_enter;
}

void printTimeoutStats()
{
  Serial.print("Timeouts: OBD:");
  Serial.print(timeoutsOBD);
  Serial.print(" Network:");
  Serial.println(timeoutsNet);
}

void beep(int duration)
{
    // turn on buzzer at 2000Hz frequency 
    sys.buzzer(2000);
    delay(duration);
    // turn off buzzer
    sys.buzzer(0);
}

#if LOG_EXT_SENSORS
void processExtInputs(CBuffer* buffer)
{
#if LOG_EXT_SENSORS == 1
  uint8_t levels[2] = {(uint8_t)digitalRead(PIN_SENSOR1), (uint8_t)digitalRead(PIN_SENSOR2)};
  buffer->add(PID_EXT_SENSORS, ELEMENT_UINT8, levels, sizeof(levels), 2);
#elif LOG_EXT_SENSORS == 2
  uint16_t reading[] = {adc1_get_raw(ADC1_CHANNEL_0), adc1_get_raw(ADC1_CHANNEL_1)};
  Serial.print("GPIO0:");
  Serial.print((float)reading[0] * 3.15 / 4095 - 0.01);
  Serial.print(" GPIO1:");
  Serial.println((float)reading[1] * 3.15 / 4095 - 0.01);
  buffer->add(PID_EXT_SENSORS, ELEMENT_UINT16, reading, sizeof(reading), 2);
#endif
}
#endif

/*******************************************************************************
  HTTP API
*******************************************************************************/
#if ENABLE_HTTPD
int handlerLiveData(UrlHandlerParam* param)
{
    char *buf = param->pucBuffer;
    int bufsize = param->bufSize;
    int n = snprintf(buf, bufsize, "{\"obd\":{\"vin\":\"%s\",\"battery\":%.1f,\"pid\":[", vin, batteryVoltage);
    uint32_t t = millis();
    for (int i = 0; i < sizeof(obdData) / sizeof(obdData[0]); i++) {
        n += snprintf(buf + n, bufsize - n, "{\"pid\":%u,\"value\":%d,\"age\":%u},",
            0x100 | obdData[i].pid, obdData[i].value, (unsigned int)(t - obdData[i].ts));
    }
    n--;
    n += snprintf(buf + n, bufsize - n, "]}");
#if ENABLE_MEMS
    if (accCount) {
      n += snprintf(buf + n, bufsize - n, ",\"mems\":{\"acc\":[%d,%d,%d],\"stationary\":%u}",
          (int)((accSum[0] / accCount - accBias[0]) * 100), (int)((accSum[1] / accCount - accBias[1]) * 100), (int)((accSum[2] / accCount - accBias[2]) * 100),
          (unsigned int)(millis() - lastMotionTime));
    }
#endif
    if (gd && gd->ts) {
      n += snprintf(buf + n, bufsize - n, ",\"gps\":{\"utc\":\"%s\",\"lat\":%f,\"lng\":%f,\"alt\":%f,\"speed\":%f,\"sat\":%d,\"age\":%u}",
          isoTime, gd->lat, gd->lng, gd->alt, gd->speed, (int)gd->sat, (unsigned int)(millis() - gd->ts));
    }
    buf[n++] = '}';
    param->contentLength = n;
    param->contentType=HTTPFILETYPE_JSON;
    return FLAG_DATA_RAW;
}
#endif

/*******************************************************************************
  Reading and processing OBD data
*******************************************************************************/
#if ENABLE_OBD
void processOBD(CBuffer* buffer)
{
  static int idx[2] = {0, 0};
  int tier = 1;
  for (byte i = 0; i < sizeof(obdData) / sizeof(obdData[0]); i++) {
    if (obdData[i].tier > tier) {
        // reset previous tier index
        idx[tier - 2] = 0;
        // keep new tier number
        tier = obdData[i].tier;
        // move up current tier index
        i += idx[tier - 2]++;
        // check if into next tier
        if (obdData[i].tier != tier) {
            idx[tier - 2]= 0;
            i--;
            continue;
        }
    }
    byte pid = obdData[i].pid;
    if (!obd.isValidPID(pid)) continue;
    int value;
    if (obd.readPID(pid, value)) {
        obdData[i].ts = millis();
        obdData[i].value = value;
        buffer->add((uint16_t)pid | 0x100, ELEMENT_INT32, &value, sizeof(value));
    } else {
        timeoutsOBD++;
        printTimeoutStats();
        break;
    }
    if (tier > 1) break;
  }
  // Poll vehicle-specific extra PIDs (from VEHICLE_PIDS NVS key).
  // Use a static index to cycle through all vehicle PIDs one per call (tier-3 pacing).
  if (vehicleObdDataCount > 0) {
    static int vehiclePidIdx = 0;
    if (vehiclePidIdx >= vehicleObdDataCount) vehiclePidIdx = 0;
    byte vpid = vehicleObdData[vehiclePidIdx].pid;
    if (obd.isValidPID(vpid)) {
      int vval;
      if (obd.readPID(vpid, vval)) {
        vehicleObdData[vehiclePidIdx].ts    = millis();
        vehicleObdData[vehiclePidIdx].value = vval;
        buffer->add((uint16_t)vpid | 0x100, ELEMENT_INT32, &vval, sizeof(vval));
      }
    }
    vehiclePidIdx++;
  }
  int kph = obdData[0].value;
  if (kph >= 2) lastMotionTime = millis();
}
#endif

bool initGPS()
{
  // start GNSS receiver
  if (sys.gpsBeginExt()) {
    Serial.println("GNSS:OK(E)");
  } else if (sys.gpsBegin()) {
    Serial.println("GNSS:OK(I)");
  } else {
    Serial.println("GNSS:NO");
    return false;
  }
  return true;
}

bool processGPS(CBuffer* buffer)
{
  static uint32_t lastGPStime = 0;
  static float lastGPSLat = 0;
  static float lastGPSLng = 0;

  if (!gd) {
    lastGPStime = 0;
    lastGPSLat = 0;
    lastGPSLng = 0;
  }
#if GNSS == GNSS_STANDALONE
  if (state.check(STATE_GPS_READY)) {
    // read parsed GPS data
    if (!sys.gpsGetData(&gd)) {
      return false;
    }
  }
#else
    if (!teleClient.cell.getLocation(&gd)) {
      return false;
    }
#endif
  if (!gd || lastGPStime == gd->time) return false;
  if (gd->date) {
    // generate ISO time string
    char *p = isoTime + sprintf(isoTime, "%04u-%02u-%02uT%02u:%02u:%02u",
        (unsigned int)(gd->date % 100) + 2000, (unsigned int)(gd->date / 100) % 100, (unsigned int)(gd->date / 10000),
        (unsigned int)(gd->time / 1000000), (unsigned int)(gd->time % 1000000) / 10000, (unsigned int)(gd->time % 10000) / 100);
    unsigned char tenth = (gd->time % 100) / 10;
    if (tenth) p += sprintf(p, ".%c00", '0' + tenth);
    *p = 'Z';
    *(p + 1) = 0;
  }
  if (gd->lng == 0 && gd->lat == 0) {
    // No position fix yet – still log satellite count and HDOP so that
    // sensor.gps_satellites / sensor.gps_hdop in HA show the GPS is actively
    // searching even before the first valid position is obtained.
    if (buffer) {
      if (gd->sat) buffer->add(PID_GPS_SAT_COUNT, ELEMENT_UINT8, &gd->sat, sizeof(uint8_t));
      if (gd->hdop) buffer->add(PID_GPS_HDOP, ELEMENT_UINT8, &gd->hdop, sizeof(uint8_t));
    }
    if (gd->date) {
      Serial.print("[GNSS] ");
      Serial.print(isoTime);
      Serial.print(" SATS:");
      Serial.println(gd->sat);
    }
    return false;
  }
  if ((lastGPSLat || lastGPSLng) && (abs(gd->lat - lastGPSLat) > 0.001 || abs(gd->lng - lastGPSLng) > 0.001)) {
    // invalid coordinates data
    lastGPSLat = 0;
    lastGPSLng = 0;
    return false;
  }
  lastGPSLat = gd->lat;
  lastGPSLng = gd->lng;

  float kph = gd->speed * 1.852f;
  if (kph >= 2) lastMotionTime = millis();

  if (buffer) {
    buffer->add(PID_GPS_TIME, ELEMENT_UINT32, &gd->time, sizeof(uint32_t));
    buffer->add(PID_GPS_LATITUDE, ELEMENT_FLOAT, &gd->lat, sizeof(float));
    buffer->add(PID_GPS_LONGITUDE, ELEMENT_FLOAT, &gd->lng, sizeof(float));
    buffer->add(PID_GPS_ALTITUDE, ELEMENT_FLOAT_D1, &gd->alt, sizeof(float)); /* m */
    buffer->add(PID_GPS_SPEED, ELEMENT_FLOAT_D1, &kph, sizeof(kph));
    buffer->add(PID_GPS_HEADING, ELEMENT_UINT16, &gd->heading, sizeof(uint16_t));
    if (gd->sat) buffer->add(PID_GPS_SAT_COUNT, ELEMENT_UINT8, &gd->sat, sizeof(uint8_t));
    if (gd->hdop) buffer->add(PID_GPS_HDOP, ELEMENT_UINT8, &gd->hdop, sizeof(uint8_t));
  }
  
  Serial.print("[GNSS] ");
  Serial.print(gd->lat, 6);
  Serial.print(' ');
  Serial.print(gd->lng, 6);
  Serial.print(' ');
  Serial.print((int)kph);
  Serial.print("km/h");
  Serial.print(" SATS:");
  Serial.print(gd->sat);
  Serial.print(" HDOP:");
  Serial.print(gd->hdop);
  Serial.print(" Course:");
  Serial.println(gd->heading);
  //Serial.println(gd->errors);
  lastGPStime = gd->time;
  return true;
}

bool waitMotionGPS(int timeout)
{
  unsigned long t = millis();
  lastMotionTime = 0;
  do {
      serverProcess(100);
    if (!processGPS(0)) continue;
    if (lastMotionTime) return true;
  } while (millis() - t < timeout);
  return false;
}

#if ENABLE_MEMS
void processMEMS(CBuffer* buffer)
{
  if (!state.check(STATE_MEMS_READY)) return;

  // load and store accelerometer data
  float temp;
#if ENABLE_ORIENTATION
  ORIENTATION ori;
  if (!mems->read(acc, gyr, mag, &temp, &ori)) return;
#else
  if (!mems->read(acc, gyr, mag, &temp)) return;
#endif
  deviceTemp = (int)temp;

  accSum[0] += acc[0];
  accSum[1] += acc[1];
  accSum[2] += acc[2];
  accCount++;

  // Update lastMotionTime whenever the instantaneous bias-corrected
  // acceleration exceeds MOTION_THRESHOLD.  This is the fallback motion
  // source when OBD-II and GPS are both unavailable: without it the
  // stationary-timeout logic in process() would put the device into
  // STANDBY (and disconnect WiFi) after ~3 minutes even while the
  // vehicle is driving.  Uses instantaneous values (same approach as
  // waitMotion()) rather than the per-buffer average so that brief
  // manoeuvres (cornering, braking) are detected even across long
  // sampling windows.
  {
    float motion = 0;
    for (byte i = 0; i < 3; i++) {
      float m = acc[i] - accBias[i];
      motion += m * m;
    }
    if (motion >= MOTION_THRESHOLD * MOTION_THRESHOLD) {
      lastMotionTime = millis();
    }
  }

  if (buffer) {
    if (accCount) {
      float value[3];
      value[0] = accSum[0] / accCount - accBias[0];
      value[1] = accSum[1] / accCount - accBias[1];
      value[2] = accSum[2] / accCount - accBias[2];
      buffer->add(PID_ACC, ELEMENT_FLOAT_D2, value, sizeof(value), 3);
#if ENABLE_ORIENTATION
      value[0] = ori.yaw;
      value[1] = ori.pitch;
      value[2] = ori.roll;
      buffer->add(PID_ORIENTATION, ELEMENT_FLOAT_D2, value, sizeof(value), 3);
#endif
    }
    accSum[0] = 0;
    accSum[1] = 0;
    accSum[2] = 0;
    accCount = 0;
  }
}

void calibrateMEMS()
{
  if (state.check(STATE_MEMS_READY)) {
    accBias[0] = 0;
    accBias[1] = 0;
    accBias[2] = 0;
    int n;
    unsigned long t = millis();
    for (n = 0; millis() - t < 1000; n++) {
      float acc[3];
      if (!mems->read(acc)) continue;
      accBias[0] += acc[0];
      accBias[1] += acc[1];
      accBias[2] += acc[2];
      delay(10);
    }
    accBias[0] /= n;
    accBias[1] /= n;
    accBias[2] /= n;
    Serial.print("ACC BIAS:");
    Serial.print(accBias[0]);
    Serial.print('/');
    Serial.print(accBias[1]);
    Serial.print('/');
    Serial.println(accBias[2]);
  }
}
#endif

void printTime()
{
  time_t utc;
  time(&utc);
  struct tm *btm = gmtime(&utc);
  if (btm->tm_year > 100) {
    // valid system time available
    char buf[64];
    sprintf(buf, "%04u-%02u-%02u %02u:%02u:%02u",
      1900 + btm->tm_year, btm->tm_mon + 1, btm->tm_mday, btm->tm_hour, btm->tm_min, btm->tm_sec);
    Serial.print("UTC:");
    Serial.println(buf);
  }
}

/*******************************************************************************
  Initializing all data logging components
*******************************************************************************/
void initialize()
{
  // dump buffer data
  bufman.purge();

  // Reset LED/beep/conn_type sentinels so the current state is re-sent in the
  // first buffer of the new telemetry session.  initialize() is called at the
  // start of every logging session (boot and after each network disconnection),
  // so resetting here ensures the device always reports its live LED/beep state
  // and active transport type to HA after a reconnect — preventing a permanent
  // "Unbekannt" IST-Status when HA is reloaded while the device was connected
  // (HA loses diag state, device never resends unchanged values unless the
  // sentinels are reset).
  s_lastLedWhite    = -1;
  s_lastBeep        = -1;
  s_lastConnType    = -1;
  s_lastObd         = -1;
  s_lastCan         = -1;
  s_lastStandbyTime = -1;
  // Signal the telemetry task to inject IST-Status PIDs into the very next
  // transmitted packet so they are not lost to the getNewest() race.
  s_send_state_pids = true;

#if ENABLE_MEMS
  if (state.check(STATE_MEMS_READY)) {
    calibrateMEMS();
  }
#endif

#if GNSS == GNSS_STANDALONE
  if (!state.check(STATE_GPS_READY)) {
    if (initGPS()) {
      state.set(STATE_GPS_READY);
    }
  }
#endif

#if ENABLE_OBD
  // initialize OBD communication (skipped when enableObd=false via NVS key OBD_EN)
  if (enableObd && !state.check(STATE_OBD_READY)) {
    timeoutsOBD = 0;
    // Pre-wake: send OBD2 diagnostic requests BEFORE obd.init() so the vehicle ECU
    // is active when init() tries to communicate.  Many vehicles (especially VAG:
    // VW/Skoda/Audi/Seat, but also BMW and Mercedes) keep the diagnostic CAN bus
    // silent until they receive an initial request — obd.init() alone may time out
    // because it expects the ECU to already be responsive.
    // Sequence: minimal ELM327 reset + two PID requests (RPM=0x0C, coolant=0x05).
    // The ECU may not reply yet (still waking up), which is fine; the intent is to
    // put a frame on the bus and let the ECU's diagnostic stack initialise before
    // obd.init() fires its own PID_SPEED probe.
    if (obd.link) {
      char wbuf[64];
      obd.link->sendCommand("ATZ\r",  wbuf, sizeof(wbuf), 1000); // reset ELM327
      obd.link->sendCommand("ATE0\r", wbuf, sizeof(wbuf),  500); // disable echo
      obd.link->sendCommand("ATH0\r", wbuf, sizeof(wbuf),  500); // disable headers
      obd.link->sendCommand("010C\r", wbuf, sizeof(wbuf),  500); // RPM – wake req 1
      obd.link->sendCommand("0105\r", wbuf, sizeof(wbuf),  500); // coolant – wake req 2
      Serial.println("OBD:pre-wake sent");
      delay(100); // give ECU time to start its diagnostic task
    }
    if (obd.init()) {
      Serial.println("OBD:OK");
      state.set(STATE_OBD_READY);
#if ENABLE_OLED
      oled.println("OBD OK");
#endif
    } else {
      Serial.println("OBD:NO");
      //state.clear(STATE_WORKING);
      //return;
    }
  }
  // CAN bus sniffing: enable/disable only on transitions to minimise AT commands.
  // sniff(true) sends ATM1 to the ELM327 – puts it in "monitor all" mode so every
  // CAN frame on the bus is captured and readable via receiveData().
  // Works independently of STATE_OBD_READY; useful even when OBD-II init fails.
  if (enableCan != s_canSniffActive) {
    obd.sniff(enableCan);
    s_canSniffActive = enableCan;
    Serial.println(enableCan ? "CAN:sniff on" : "CAN:sniff off");
    if (enableCan) {
      // Send initial CAN wake-up frame on the OBD2 functional broadcast address
      // (0x7DF) to activate the diagnostic bus before passive sniffing begins.
      // Payload 02 01 00 = ISO 15765-4 "PIDs supported [01-20]" request.
      byte wakeFrame[] = {0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
      char rxbuf[32];
      obd.setCANID(0x7DF);
      obd.sendCANMessage(wakeFrame, 8, rxbuf, sizeof(rxbuf));
      Serial.println("CAN:wake-up sent");
    }
  }
#endif

#if STORAGE != STORAGE_NONE
  if (!state.check(STATE_STORAGE_READY)) {
    // init storage
    if (logger.init()) {
      state.set(STATE_STORAGE_READY);
    }
  }
  if (state.check(STATE_STORAGE_READY)) {
    fileid = logger.begin();
    if (fileid) {
      // Write a diagnostic boot banner so that every CSV log file carries
      // the firmware version, device ID, and the initial subsystem status
      // that would otherwise only appear on the serial console.
      char diag[128];
      logger.timestamp(millis());
      snprintf(diag, sizeof(diag), "BOOT FW=%s ID=%s", FIRMWARE_VERSION, devid);
      logger.logEvent(diag);
      snprintf(diag, sizeof(diag), "STATE OBD=%c GPS=%c MEMS=%c",
          state.check(STATE_OBD_READY)  ? '1' : '0',
          state.check(STATE_GPS_READY)  ? '1' : '0',
          state.check(STATE_MEMS_READY) ? '1' : '0');
      logger.logEvent(diag);
#if ENABLE_WIFI
      snprintf(diag, sizeof(diag), "WIFI SSID=%s", wifiSSID[0] ? wifiSSID : "-");
      logger.logEvent(diag);
#endif
      logger.flush();
    }
  }
#endif

#if STORAGE == STORAGE_SD
  // Startup check: detect a firmware staged by a previous session.
  // against the actual /ota_fw.bin file size.  A match means the download
  // completed successfully; set s_ota_pending so the flash happens at the
  // next standby transition.  Any mismatch means a partial download —
  // clean up both files to avoid a corrupt flash attempt.
  if (state.check(STATE_STORAGE_READY)) {
    if (SD.exists(OTA_META_PATH)) {
      unsigned long expectedSize = 0;
      {
        File mf = SD.open(OTA_META_PATH, FILE_READ);
        if (mf) {
          char buf[16] = {0};
          mf.readBytesUntil('\n', buf, sizeof(buf) - 1);
          mf.close();
          expectedSize = strtoul(buf, nullptr, 10);
        }
      }
      bool stagingValid = false;
      if (expectedSize >= PULL_OTA_MIN_FW_SIZE && SD.exists(OTA_PENDING_PATH)) {
        File ff = SD.open(OTA_PENDING_PATH, FILE_READ);
        unsigned long actual = ff ? (unsigned long)ff.size() : 0UL;
        if (ff) ff.close();
        stagingValid = (actual == expectedSize);
      }
      if (stagingValid) {
        Serial.println("[OTA-PULL] Staged firmware found on SD — flashing at boot");
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL BOOT_FLASH");
        // Flash immediately at boot: the telemetry task has not started yet so
        // there is no need for s_ota_active synchronisation.  Flashing at boot
        // also ensures the update is applied even on devices that never reach
        // standby naturally (e.g. no OBD / no MEMS stationary timeout).
        if (performPullOtaFlash()) {
          // Flash succeeded; reboot timer is running — block here until it fires.
          while (true) delay(1000);
        }
        // Flash failed (corrupt image etc.): staging files already cleaned up
        // by performPullOtaFlash().  Continue normal boot.
      } else {
        SD.remove(OTA_PENDING_PATH);
        SD.remove(OTA_META_PATH);
        SD.remove(OTA_NVS_PATH);
        Serial.println("[OTA-PULL] Stale/incomplete SD staging files removed");
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL STALE_REMOVED");
      }
    } else if (SD.exists(OTA_PENDING_PATH)) {
      // Firmware file without companion meta — can't verify, remove it.
      SD.remove(OTA_PENDING_PATH);
      SD.remove(OTA_NVS_PATH);
    } else {
      // Normal case: no OTA firmware staged on SD.
      Serial.println("[OTA] SD:none");
    }
  }
#endif

  // re-try OBD if connection not established
#if ENABLE_OBD
  if (state.check(STATE_OBD_READY)) {
    char buf[128];
    if (obd.getVIN(buf, sizeof(buf))) {
      memcpy(vin, buf, sizeof(vin) - 1);
      Serial.print("VIN:");
      Serial.println(vin);
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) {
        char diag[32];
        snprintf(diag, sizeof(diag), "VIN=%s", vin);
        logger.logEvent(diag);
      }
#endif
    }
    int dtcCount = obd.readDTC(dtc, sizeof(dtc) / sizeof(dtc[0]));
    if (dtcCount > 0) {
      Serial.print("DTC:");
      Serial.println(dtcCount);
    }
#if ENABLE_OLED
    oled.print("VIN:");
    oled.println(vin);
#endif
  }
#endif

  // check system time
  printTime();

  lastMotionTime = millis();
  state.set(STATE_WORKING);

#if ENABLE_OLED
  delay(1000);
  oled.clear();
  oled.print("DEVICE ID: ");
  oled.println(devid);
  oled.setCursor(0, 7);
  oled.print("Packets");
  oled.setCursor(80, 7);
  oled.print("KB Sent");
  oled.setFontSize(FONT_SIZE_MEDIUM);
#endif
}

void showStats()
{
  uint32_t t = millis() - teleClient.startTime;
  char buf[32];
  sprintf(buf, "%02u:%02u.%c ", t / 60000, (t % 60000) / 1000, (t % 1000) / 100 + '0');
  Serial.print("[NET] ");
  Serial.print(buf);
  Serial.print("| Packet #");
  Serial.print(teleClient.txCount);
  Serial.print(" | Out: ");
  Serial.print(teleClient.txBytes >> 10);
  Serial.print(" KB | In: ");
  Serial.print(teleClient.rxBytes);
  Serial.print(" bytes | ");
  Serial.print((unsigned int)((uint64_t)(teleClient.txBytes + teleClient.rxBytes) * 3600 / (millis() - teleClient.startTime)));
  Serial.print(" KB/h");

  Serial.println();
#if ENABLE_OLED
  oled.setCursor(0, 2);
  oled.println(timestr);
  oled.setCursor(0, 5);
  oled.printInt(teleClient.txCount, 2);
  oled.setCursor(80, 5);
  oled.printInt(teleClient.txBytes >> 10, 3);
#endif
}

bool waitMotion(long timeout)
{
#if ENABLE_MEMS
  unsigned long t = millis();
  if (state.check(STATE_MEMS_READY)) {
    do {
      // calculate relative movement
      float motion = 0;
      float acc[3];
      if (!mems->read(acc)) continue;
      if (accCount == 10) {
        accCount = 0;
        accSum[0] = 0;
        accSum[1] = 0;
        accSum[2] = 0;
      }
      accSum[0] += acc[0];
      accSum[1] += acc[1];
      accSum[2] += acc[2];
      accCount++;
      for (byte i = 0; i < 3; i++) {
        float m = (acc[i] - accBias[i]);
        motion += m * m;
      }
#if ENABLE_HTTPD
      serverProcess(100);
#endif
      processBLE(100);
      // check movement
      if (motion >= MOTION_THRESHOLD * MOTION_THRESHOLD) {
        //lastMotionTime = millis();
        Serial.println(motion);
        return true;
      }
    } while (state.check(STATE_STANDBY) && ((long)(millis() - t) < timeout || timeout == -1));
    return false;
  }
#endif
  serverProcess(timeout);
  return false;
}

/*******************************************************************************
  Collecting and processing data
*******************************************************************************/
void process()
{
  static uint32_t lastGPStick = 0;
  uint32_t startTime = millis();

  CBuffer* buffer = bufman.getFree();
  buffer->state = BUFFER_STATE_FILLING;

#if ENABLE_OBD
  // process OBD data if connected
  if (state.check(STATE_OBD_READY)) {
    processOBD(buffer);
    if (obd.errors >= MAX_OBD_ERRORS) {
      if (!obd.init()) {
        Serial.println("[OBD] ECU OFF");
#if STORAGE != STORAGE_NONE
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OBD ECU_OFF");
#endif
        state.clear(STATE_OBD_READY | STATE_WORKING);
        return;
      }
    }
  } else {
    // STATE_OBD_READY not set – attempt reconnection.
    // Limit to one attempt every 30 s: obd.init() sends ATZ which hard-resets
    // the ELM327.  Calling it every process() cycle (every 1–5 s) resets the
    // adapter before it can finish its auto-protocol detection, creating a
    // permanent reconnect loop where OBD-II never connects.
    // Use full init (quick=false): tries readPID twice instead of once, which
    // is more robust for ECUs that are slow to respond after engine start.
    // lastOBDReinit=0 at declaration means the first attempt is deferred until
    // millis() >= 30000 (~30 s after boot), giving initialize()'s own init
    // attempt a clear head-start and the ECU time to become ready.
    static uint32_t lastOBDReinit = 0;
    if (millis() - lastOBDReinit >= 30000) {
      lastOBDReinit = millis();
      if (obd.init(PROTO_AUTO, false)) {
        state.set(STATE_OBD_READY);
        Serial.println("[OBD] ECU ON");
      }
    }
  }
#endif

#if ENABLE_OBD
  // CAN bus frame capture (when enableCan=true via NVS key CAN_EN).
  // Drains all frames currently buffered by the ELM327 ATM1 monitor-all mode.
  // Each receiveData() call reads one frame's payload bytes.  Frames are
  // hex-encoded and stored in s_canFrameList (ring buffer, newest last).
  // The HA integration reads this via /api/control?cmd=CAN_DATA, clears it.
  if (enableCan) {
    byte rxbuf[32];  // one CAN frame payload: up to 8 data bytes from receiveData
    int rxbytes;
    while ((rxbytes = obd.receiveData(rxbuf, sizeof(rxbuf))) > 0) {
      // Hex-encode the received payload bytes into a local string.
      char hexEntry[sizeof(rxbuf) * 2 + 1];
      int hexLen = 0;
      for (int i = 0; i < rxbytes && hexLen < (int)sizeof(hexEntry) - 2; i++) {
        hexLen += snprintf(hexEntry + hexLen, sizeof(hexEntry) - hexLen, "%02X", rxbuf[i]);
      }
      hexEntry[hexLen] = 0;
      portENTER_CRITICAL(&s_canBufMux);
      if (s_canFrameCount < CAN_DATA_LIST_MAX) {
        // Append entry to the list.
        strncpy(s_canFrameList[s_canFrameCount], hexEntry, sizeof(s_canFrameList[0]) - 1);
        s_canFrameList[s_canFrameCount][sizeof(s_canFrameList[0]) - 1] = 0;
        s_canFrameCount++;
      } else {
        // Ring buffer full – drop oldest entry and shift.
        memmove(s_canFrameList[0], s_canFrameList[1],
                (CAN_DATA_LIST_MAX - 1) * sizeof(s_canFrameList[0]));
        strncpy(s_canFrameList[CAN_DATA_LIST_MAX - 1], hexEntry, sizeof(s_canFrameList[0]) - 1);
        s_canFrameList[CAN_DATA_LIST_MAX - 1][sizeof(s_canFrameList[0]) - 1] = 0;
      }
      s_canFrameTotal++;
      portEXIT_CRITICAL(&s_canBufMux);
    }
  }
#endif
  if (rssi != rssiLast) {
    int val = (rssiLast = rssi);
    buffer->add(PID_CSQ, ELEMENT_INT32, &val, sizeof(val));
  }
#if ENABLE_OBD
  if (sys.devType > 12) {
    batteryVoltage = (float)(analogRead(A0) * 45) / 4095;
  } else {
    batteryVoltage = obd.getVoltage();
  }
  if (batteryVoltage) {
    uint16_t v = batteryVoltage * 100;
    buffer->add(PID_BATTERY_VOLTAGE, ELEMENT_UINT16, &v, sizeof(v));
  }
#endif

#if LOG_EXT_SENSORS
  processExtInputs(buffer);
#endif

#if ENABLE_MEMS
  processMEMS(buffer);
#endif

  bool success = processGPS(buffer);
#if GNSS_RESET_TIMEOUT
  if (success) {
    lastGPStick = millis();
    state.set(STATE_GPS_ONLINE);
  } else {
    if (millis() - lastGPStick > GNSS_RESET_TIMEOUT * 1000) {
      sys.gpsEnd();
      state.clear(STATE_GPS_ONLINE | STATE_GPS_READY);
      delay(20);
      if (initGPS()) state.set(STATE_GPS_READY);
      lastGPStick = millis();
    }
  }
#endif

  if (!state.check(STATE_MEMS_READY)) {
    deviceTemp = readChipTemperature();
  }
  buffer->add(PID_DEVICE_TEMP, ELEMENT_INT32, &deviceTemp, sizeof(deviceTemp));

  // Report white-LED and beep runtime state so HA can display live IST-Status.
  // Uses the file-scope sentinels s_lastLedWhite / s_lastBeep (both initialised
  // to -1 and reset to -1 on every telemetry reconnect via initialize() and on
  // every new WiFi/cellular connection) so the current state is always re-sent
  // after a connection drop, preventing a permanent "Unbekannt" IST-Status in
  // Home Assistant when the very first transmission attempt fails and the buffer
  // is subsequently purged.
  {
    uint8_t lwv = enableLedWhite ? 1 : 0;
    uint8_t bv  = enableBeep     ? 1 : 0;
    if ((int8_t)lwv != s_lastLedWhite) {
      s_lastLedWhite = (int8_t)lwv;
      buffer->add(PID_LED_WHITE_STATE, ELEMENT_UINT8, &lwv, sizeof(lwv));
    }
    if ((int8_t)bv != s_lastBeep) {
      s_lastBeep = (int8_t)bv;
      buffer->add(PID_BEEP_STATE, ELEMENT_UINT8, &bv, sizeof(bv));
    }
  }

  // Report active transport type (WiFi vs Cellular) via PID_CONN_TYPE (0x88).
  // Only added when a network connection is active (STATE_NET_READY) so the
  // value is always meaningful — the device is either on WiFi or cellular,
  // never in AP-only mode when this PID reaches HA.  The sentinel is reset on
  // every new connection, so the first packet of each session always includes
  // this PID, enabling HA to correctly update "WiFi letzte Verbindung" /
  // "LTE letzte Verbindung" timestamps for both transports.
  if (state.check(STATE_NET_READY)) {
    // 1 = WiFi (STATE_WIFI_CONNECTED), 2 = Cellular (SIM7600 / LTE).
    uint8_t ctv = state.check(STATE_WIFI_CONNECTED) ? 1 : 2;
    if ((int8_t)ctv != s_lastConnType) {
      s_lastConnType = (int8_t)ctv;
      buffer->add(PID_CONN_TYPE, ELEMENT_UINT8, &ctv, sizeof(ctv));
    }
  }

  // Report OBD / CAN runtime state (PIDs 0x89 / 0x8a) so HA can display
  // the live IST-Status alongside the configured value from the options flow.
  {
    uint8_t ov = enableObd ? 1 : 0;
    uint8_t cv = enableCan ? 1 : 0;
    if ((int8_t)ov != s_lastObd) {
      s_lastObd = (int8_t)ov;
      buffer->add(PID_OBD_STATE, ELEMENT_UINT8, &ov, sizeof(ov));
    }
    if ((int8_t)cv != s_lastCan) {
      s_lastCan = (int8_t)cv;
      buffer->add(PID_CAN_STATE, ELEMENT_UINT8, &cv, sizeof(cv));
    }
  }

  // Report standby-time override (PID 0x8b).  0 = firmware compile-time default.
  {
    int16_t sv = (int16_t)nvsStandbyTimeS;
    if (sv != s_lastStandbyTime) {
      s_lastStandbyTime = sv;
      buffer->add(PID_STANDBY_TIME, ELEMENT_UINT16, &nvsStandbyTimeS, sizeof(nvsStandbyTimeS));
    }
  }

  // Report deep-standby mode (PID 0x8c): 1 = deep sleep on standby, 0 = normal.
  {
    uint8_t dv = enableDeepStandby ? 1 : 0;
    if ((int8_t)dv != s_lastDeepStandby) {
      s_lastDeepStandby = (int8_t)dv;
      buffer->add(PID_DEEP_STANDBY, ELEMENT_UINT8, &dv, sizeof(dv));
    }
  }

#if STORAGE == STORAGE_SD
  // Report SD card total/free space once per minute so HA can display SD
  // presence and usage without a direct HTTP connection to the device.
  // PID_SD_TOTAL_MB = 0 signals "no card / not ready" to HA.
  // Also purge oldest log files when SD is >= 80% full (auto-cleanup).
  {
    static uint32_t lastSdReportMs = 0;
    uint32_t nowMs = millis();
    if (lastSdReportMs == 0 || nowMs - lastSdReportMs >= 60000UL) {
      lastSdReportMs = nowMs;
      uint32_t sdTotalMb = 0;
      uint32_t sdFreeMb  = 0;
      if (state.check(STATE_STORAGE_READY)) {
        // Purge oldest 20% of log files when SD >= 80% full.
        if (logger.purgeOldFiles()) {
          logger.logEvent("SD:PURGE");
        }
        uint64_t tot = SD.totalBytes();
        uint64_t used = SD.usedBytes();
        sdTotalMb = (uint32_t)(tot >> 20);
        sdFreeMb  = (uint32_t)((tot > used ? tot - used : 0) >> 20);
      }
      // Update module-level cache so the telemetry inject block can include
      // the SD values in the guaranteed first-packet injection without
      // touching the SD SPI bus from the wrong task.
      s_cachedSdTotalMb = sdTotalMb;
      s_cachedSdFreeMb  = sdFreeMb;
      buffer->add(PID_SD_TOTAL_MB, ELEMENT_UINT32, &sdTotalMb, sizeof(sdTotalMb));
      buffer->add(PID_SD_FREE_MB,  ELEMENT_UINT32, &sdFreeMb,  sizeof(sdFreeMb));
    }
  }
#endif

  buffer->timestamp = millis();
  buffer->state = BUFFER_STATE_FILLED;

  // display file buffer stats
  if (startTime - lastStatsTime >= 3000) {
    bufman.printStats();
    lastStatsTime = startTime;
  }

#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    // Prepend a timestamp record (PID 0) before the data payload so that the
    // /api/data endpoint (handlerLogData in dataserver.cpp) can correlate each
    // CSV record with a time offset.  The network serialisation path already
    // does this via store.timestamp(buffer->timestamp); the file path was
    // missing it, causing ts to remain 0 throughout CSV parsing and breaking
    // all time-filtered data queries.
    logger.timestamp(buffer->timestamp);
    buffer->serialize(logger);
    uint16_t sizeKB = (uint16_t)(logger.size() >> 10);
    if (sizeKB != lastSizeKB) {
      logger.flush();
      lastSizeKB = sizeKB;
      Serial.print("[FILE] ");
      Serial.print(sizeKB);
      Serial.println("KB");
    }
    // Detect and log subsystem state transitions (OBD/GPS/WiFi/Cell).
    // prevDiagState is initialised to 0xFFFF so the very first call
    // always writes a STATUS line, establishing the initial state in the CSV.
    {
      static uint16_t prevDiagState = 0xFFFF; /* impossible mask value forces initial STATUS entry */
      const uint16_t DIAG_MASK = STATE_OBD_READY | STATE_GPS_READY | STATE_GPS_ONLINE
                                | STATE_WIFI_CONNECTED | STATE_CELL_CONNECTED;
      uint16_t cur = state.m_state & DIAG_MASK;
      if (cur != prevDiagState) {
        char diag[128];
        snprintf(diag, sizeof(diag),
            "STATUS OBD=%c GPS=%c FIX=%c WIFI=%c CELL=%c t=%lu",
            state.check(STATE_OBD_READY)      ? '1' : '0',
            state.check(STATE_GPS_READY)      ? '1' : '0',
            state.check(STATE_GPS_ONLINE)     ? '1' : '0',
            state.check(STATE_WIFI_CONNECTED) ? '1' : '0',
            state.check(STATE_CELL_CONNECTED) ? '1' : '0',
            millis() / 1000);
        logger.logEvent(diag);
        prevDiagState = cur;
      }
    }
  }
#endif

  const int dataIntervals[] = DATA_INTERVAL_TABLE;
#if ENABLE_OBD || ENABLE_MEMS
  // motion adaptive data interval control
  // Build effective stationary-time table, applying STANDBY_TIME NVS override
  // (nvsStandbyTimeS, 5-900 s) to the last (maximum-standby) entry when set.
  const uint16_t stationaryTimeDefaults[] = STATIONARY_TIME_TABLE;
  const byte stationaryCount = sizeof(stationaryTimeDefaults) / sizeof(stationaryTimeDefaults[0]);
  uint16_t stationaryTime[stationaryCount];
  for (byte i = 0; i < stationaryCount; i++) {
    stationaryTime[i] = stationaryTimeDefaults[i];
  }
  if (nvsStandbyTimeS >= 5) {
    stationaryTime[stationaryCount - 1] = nvsStandbyTimeS;
  }
  unsigned int motionless = (millis() - lastMotionTime) / 1000;
  bool stationary = true;
  for (byte i = 0; i < stationaryCount; i++) {
    dataInterval = dataIntervals[i];
    if (motionless < stationaryTime[i] || stationaryTime[i] == 0) {
      stationary = false;
      break;
    }
  }
  if (stationary) {
    // stationery timeout
    Serial.print("Stationary for ");
    Serial.print(motionless);
    Serial.println(" secs");
    // trip ended, go into standby
    state.clear(STATE_WORKING);
    return;
  }
#else
  dataInterval = dataIntervals[0];
#endif
  // Idle loop: wait out the rest of the data interval while servicing
  // low-priority tasks.  Each iteration sleeps at most 100 ms so that the
  // built-in HTTP server is polled regularly (every ~100 ms) even when BLE
  // is disabled.  This ensures that /api/control?cmd=OFF requests (sent by
  // the HA OTA flash manager to pause telemetry before uploading firmware)
  // are received and acted upon during normal telemetry operation.
  do {
    long t = dataInterval - (millis() - startTime);
    long slice = (t > 100) ? 100 : (t > 0 ? t : 0);
    processBLE(slice);
#if ENABLE_HTTPD
    if (enableHttpd) serverProcess(0);
#endif
  } while (millis() - startTime < dataInterval);
}

bool initCell(bool quick = false)
{
  Serial.println("[CELL] Activating...");
  // power on network module
  if (!teleClient.cell.begin(&sys)) {
    Serial.println("[CELL] No supported module");
#if ENABLE_OLED
    oled.println("No Cell Module");
#endif
    return false;
  }
  if (quick) return true;
#if ENABLE_OLED
    oled.print(teleClient.cell.deviceName());
    oled.println(" OK\r");
    oled.print("IMEI:");
    oled.println(teleClient.cell.IMEI);
#endif
  Serial.print("CELL:");
  Serial.println(teleClient.cell.deviceName());
  // Retry checkSIM up to 3 times; the SIM may not be ready immediately after power-on
  {
    bool simReady = false;
    for (byte simRetry = 0; simRetry < 3 && !simReady; simRetry++) {
      if (teleClient.cell.checkSIM(simPin)) {
        simReady = true;
      } else if (simRetry < 2) {
        delay(2000);
      }
    }
    if (!simReady) {
      Serial.println("NO SIM CARD");
    }
  }
  Serial.print("IMEI:");
  Serial.println(teleClient.cell.IMEI);
  Serial.println("[CELL] Searching...");
  if (*apn) {
    Serial.print("APN:");
    Serial.println(apn);
  }
  if (teleClient.cell.setup(apn, APN_USERNAME, APN_PASSWORD)) {
    netop = teleClient.cell.getOperatorName();
    if (netop.length()) {
      Serial.print("Operator:");
      Serial.println(netop);
#if ENABLE_OLED
      oled.println(op);
#endif
    }

#if GNSS == GNSS_CELLULAR
    if (teleClient.cell.setGPS(true)) {
      Serial.println("CELL GNSS:OK");
    }
#endif

    ip = teleClient.cell.getIP();
    if (ip.length()) {
      Serial.print("[CELL] IP:");
      Serial.println(ip);
#if ENABLE_OLED
      oled.print("IP:");
      oled.println(ip);
#endif
    }
    state.set(STATE_CELL_CONNECTED);
  } else {
    char *p = strstr(teleClient.cell.getBuffer(), "+CPSI:");
    if (p) {
      char *q = strchr(p, '\r');
      if (q) *q = 0;
      Serial.print("[CELL] ");
      Serial.println(p + 7);
#if ENABLE_OLED
      oled.println(p + 7);
#endif
    } else {
      Serial.print(teleClient.cell.getBuffer());
    }
  }
  timeoutsNet = 0;
  return state.check(STATE_CELL_CONNECTED);
}

/*******************************************************************************
  Initializing network, maintaining connection and doing transmissions
*******************************************************************************/
void telemetry(void* inst)
{
  uint32_t lastRssiTime = 0;
  uint8_t connErrors = 0;
  CStorageRAM store;
  store.init(
#if BOARD_HAS_PSRAM
    (char*)heap_caps_malloc(SERIALIZE_BUFFER_SIZE, MALLOC_CAP_SPIRAM),
#else
    (char*)malloc(SERIALIZE_BUFFER_SIZE),
#endif
    SERIALIZE_BUFFER_SIZE
  );
  teleClient.reset();

  for (;;) {
    // Yield the WiFi radio to the OTA flash handler while it is active.
    // Without this, the telemetry task competes for bandwidth and can cause
    // WiFi reconnects that disrupt the HTTP connection used for the upload.
    if (s_ota_active) {
      delay(500);
      continue;
    }

    // Apply standby / resume requests originating from the httpd task.
    // The actual m_state writes happen here (net task only) so that
    // state.m_state is always modified from a single task context.
    if (s_http_standby_enter) {
      s_http_standby_enter = false;
      state.set(STATE_STANDBY);
      state.clear(STATE_WORKING);
      Serial.println("[HTTP] Telemetry paused via /api/control?cmd=OFF");
    }
    if (s_http_standby_exit) {
      s_http_standby_exit = false;
      state.clear(STATE_STANDBY);
      Serial.println("[HTTP] Telemetry resumed via /api/control?cmd=ON");
    }

    if (state.check(STATE_STANDBY)) {
      if (state.check(STATE_CELL_CONNECTED) || state.check(STATE_WIFI_CONNECTED)) {
        teleClient.shutdown();
        netop = "";
        ip = "";
        rssi = 0;
      }
      state.clear(STATE_NET_READY | STATE_CELL_CONNECTED | STATE_WIFI_CONNECTED);
      teleClient.reset();
      bufman.purge();
      // Reset LED/beep/conn_type sentinels so the current state is re-sent in
      // the first buffer after the connection is re-established.  Without this
      // reset the state-change detection would suppress the PIDs (value
      // unchanged) and Home Assistant would keep showing "Unbekannt" for the
      // IST-Status and the connection-type timestamps.
      s_lastLedWhite    = -1;
      s_lastBeep        = -1;
      s_lastConnType    = -1;
      s_lastObd         = -1;
      s_lastCan         = -1;
      s_lastStandbyTime = -1;
      s_send_state_pids = true;

      uint32_t t = millis();
      do {
        delay(1000);
      } while (state.check(STATE_STANDBY) && millis() - t < 1000L * PING_BACK_INTERVAL);
      if (state.check(STATE_STANDBY)) {
        // start ping
#if ENABLE_WIFI
        if (wifiSSID[0]) { 
          Serial.print("[WIFI] Joining SSID:");
          Serial.println(wifiSSID);
          teleClient.wifi.begin(wifiSSID, wifiPassword);
        }
        if (teleClient.wifi.setup()) {
          Serial.println("[WIFI] Ping...");
          teleClient.ping();
        }
        else
#endif
        {
          if (initCell()) {
            Serial.println("[CELL] Ping...");
            teleClient.ping();
          }
        }
        teleClient.shutdown();
        state.clear(STATE_CELL_CONNECTED | STATE_WIFI_CONNECTED);
      }
      continue;
    }

#if ENABLE_WIFI
    if (wifiSSID[0] && !state.check(STATE_WIFI_CONNECTED)) {
      if (!teleClient.wifi.connected()) {
        Serial.print("[WIFI] Joining SSID:");
        Serial.println(wifiSSID);
        teleClient.wifi.begin(wifiSSID, wifiPassword);
      }
      teleClient.wifi.setup(WIFI_JOIN_TIMEOUT);
    }
#endif

    while (state.check(STATE_WORKING)) {
      // Break out immediately when OTA or a standby request is pending so
      // the outer loop can process the flag and shut down SSL connections
      // before Update.begin() is called.  Without this check the inner loop
      // keeps transmitting packets (and holding SSL heap) even after
      // cmd=OFF / s_ota_active is set, which exhausts available heap and
      // triggers abort() during Update.begin().
      if (s_ota_active || s_http_standby_enter) break;

#if ENABLE_WIFI
      if (wifiSSID[0]) {
        if (!state.check(STATE_WIFI_CONNECTED) && teleClient.wifi.connected()) {
          ip = teleClient.wifi.getIP();
          if (ip.length()) {
            Serial.print("[WIFI] IP:");
            Serial.println(ip);
          }
          connErrors = 0;
          if (teleClient.connect()) {
            state.set(STATE_WIFI_CONNECTED | STATE_NET_READY);
            if (enableBeep) beep(50);
            // Reset sentinels so the first WiFi packet always re-transmits the
            // LED/beep state and connection type to HA.  Without this, the
            // sentinels retain their values from the previous cellular session
            // and HA would keep showing stale IST-Status values.
            s_lastLedWhite    = -1;
            s_lastBeep        = -1;
            s_lastConnType    = -1;
            s_lastObd         = -1;
            s_lastCan         = -1;
            s_lastStandbyTime = -1;
            s_send_state_pids = true;
            // switch off cellular module when wifi connected
            if (state.check(STATE_CELL_CONNECTED)) {
              teleClient.cell.end();
              state.clear(STATE_CELL_CONNECTED);
              Serial.println("[CELL] Deactivated");
            }
          }
        } else if (state.check(STATE_WIFI_CONNECTED) && !teleClient.wifi.connected()) {
          Serial.println("[WIFI] Disconnected");
          state.clear(STATE_WIFI_CONNECTED);
        }
      }
#endif
      if (!state.check(STATE_WIFI_CONNECTED) && !state.check(STATE_CELL_CONNECTED)) {
        connErrors = 0;
        if (!initCell() || !teleClient.connect()) {
          teleClient.cell.end();
          state.clear(STATE_NET_READY | STATE_CELL_CONNECTED);
          Serial.println("[CELL] Deactivated");
#if ENABLE_WIFI
          if (wifiSSID[0]) {
            // Try WiFi immediately before the cellular backoff delay
            if (!teleClient.wifi.connected()) {
              Serial.print("[WIFI] Joining SSID:");
              Serial.println(wifiSSID);
              teleClient.wifi.begin(wifiSSID, wifiPassword);
            }
            if (teleClient.wifi.setup(WIFI_JOIN_TIMEOUT)) {
              break;  // WiFi connected; re-enter outer loop to complete setup
            }
          }
#endif
          // avoid turning on/off cellular module too frequently to avoid operator banning
          delay(60000 * 3);
          break;
        }
        Serial.println("[CELL] In service");
        state.set(STATE_NET_READY);
        if (enableBeep) beep(50);
        // Reset sentinels so the first cellular packet always re-transmits the
        // LED/beep state and connection type to HA.  Without this, the sentinels
        // retain their values from the previous WiFi session and HA would keep
        // showing stale IST-Status values and incorrect connection timestamps.
        s_lastLedWhite    = -1;
        s_lastBeep        = -1;
        s_lastConnType    = -1;
        s_lastObd         = -1;
        s_lastCan         = -1;
        s_lastStandbyTime = -1;
        s_send_state_pids = true;
      }

      if (millis() - lastRssiTime > SIGNAL_CHECK_INTERVAL * 1000) {
#if ENABLE_WIFI
        if (state.check(STATE_WIFI_CONNECTED))
        {
          rssi = teleClient.wifi.RSSI();
        }
        else
#endif
        {
          rssi = teleClient.cell.RSSI();
        }
        if (rssi) {
          Serial.print("RSSI:");
          Serial.print(rssi);
          Serial.println("dBm");
        }
        lastRssiTime = millis();

#if ENABLE_WIFI
        if (wifiSSID[0] && !state.check(STATE_WIFI_CONNECTED) && !teleClient.wifi.connected()) {
          teleClient.wifi.begin(wifiSSID, wifiPassword);
        }
#endif
      }

      // Periodic pull-OTA check: runs only when WiFi is connected and
      // OTA_TOKEN + OTA_INTERVAL are provisioned.  OTA is WiFi-only; the
      // SIM7600E-H cellular modem cannot reliably connect to the OTA endpoint
      // (TLS error 15 against *.ui.nabu.casa / Cloudflare).  The check is
      // placed here (before the empty-buffer continue) so it fires even when
      // OBD2/GPS are inactive and no telemetry data is being collected.
      // Rate-limited by otaCheckIntervalS; 0 means disabled.
      //
      // For STORAGE_SD: performPullOtaCheck() downloads the binary to SD and
      // returns false (no reboot yet).  The flash happens in standby().
      // For other storage: returns true when direct flash has started (reboot
      // imminent) so the caller blocks here waiting for the reboot timer.
      if (otaToken[0] && otaCheckIntervalS > 0 &&
          state.check(STATE_WIFI_CONNECTED)) {
        static uint32_t lastOtaCheckMs = 0;
        uint32_t nowMs = millis();
        if (lastOtaCheckMs == 0 || nowMs - lastOtaCheckMs >= (uint32_t)otaCheckIntervalS * 1000UL) {
          lastOtaCheckMs = nowMs;
          Serial.println("[OTA-PULL] Checking for firmware update...");
          // Do NOT close the telemetry TLS session here.  In virtually all
          // deployments (Nabu Casa / hooks.nabu.casa) the OTA host and the
          // telemetry webhook host are the same *.ui.nabu.casa or
          // hooks.nabu.casa domain.  Calling wifi.close() before the OTA
          // check would tear down the active TLS session and force a new
          // TLS handshake, creating an alloc→free→alloc cycle that fragments
          // the mbedTLS heap over time (each cycle leaves behind tiny holes
          // that reduce the maximum contiguous block).  Over ~30 telemetry
          // packets the max block shrinks from ~40 KB to ~20 KB — well below
          // the 38 KB TLS_MIN_FREE_HEAP threshold — causing Guard 2 in
          // WifiHTTP::open() to fire ("Low heap … after cleanup, skipping TLS
          // connect") on every subsequent OTA check, rendering OTA unusable.
          //
          // WifiHTTP::open() already handles both cases correctly:
          //   • Same host: reuse the existing TLS session (zero TLS cycles).
          //   • Different host, heap OK: stop() + connect() atomically.
          //   • Different host, heap low: Guard 1 returns false; the post-OTA
          //     check below restarts WiFi to coalesce the heap.
          if (performPullOtaCheck()) {
            // Direct-flash path: firmware flash started; device will reboot
            // shortly.  Block here so the loop doesn't continue transmitting.
            while (true) delay(1000);
          }
#if STORAGE == STORAGE_SD
          // SD-staged path: firmware was written to /ota_fw.bin; standby()
          // will call performPullOtaFlash() when the car turns off.
          // Break out of the inner while immediately so no further transmit
          // attempts are made with the now-fragmented TLS heap.  The outer
          // for(;;) loop sees s_ota_pending=true on the next iteration and
          // enters its delay(1000)/continue idle path.
          // performPullOtaCheck() called wifi.close() internally which reset
          // m_state to HTTP_DISCONNECTED, so the HTTP_ERROR-based guard below
          // would never fire after a successful SD download — break explicitly.
          if (s_ota_pending) {
            teleClient.wifi.end();
            state.clear(STATE_NET_READY | STATE_WIFI_CONNECTED);
            break;
          }
#endif
          // If OTA failed due to genuine heap fragmentation (e.g. a TLS
          // teardown inside performPullOtaCheck() leaked mbedTLS state), the
          // heap may still be too low to re-establish telemetry.  Detect this
          // and restart WiFi to coalesce the heap.
#if ENABLE_WIFI
          if (teleClient.wifi.state() == HTTP_ERROR &&
              state.check(STATE_WIFI_CONNECTED) &&
              ESP.getMaxAllocHeap() < TLS_MIN_FREE_HEAP) {
            Serial.printf("[WIFI] Low heap (%u bytes max block) after OTA TLS fail, restarting WiFi\n",
                          (unsigned)ESP.getMaxAllocHeap());
            teleClient.wifi.end();
            state.clear(STATE_NET_READY | STATE_WIFI_CONNECTED);
            break;
          }
#endif
        }
      }

      // get data from buffer
      CBuffer* buffer = bufman.getNewest();
      if (!buffer) {
        delay(50);
        continue;
      }
#if SERVER_PROTOCOL == PROTOCOL_UDP
      store.header(devid);
#endif
      store.timestamp(buffer->timestamp);
      buffer->serialize(store);
      bufman.free(buffer);
      // Inject IST-Status PIDs (LED/beep/conn-type/SD) directly into this
      // packet whenever a new connection has just been established.
      //
      // Without this injection, there is a race between process() and the
      // telemetry loop that reliably loses these PIDs on cellular connections:
      //   1. Sentinel reset → process() adds PIDs to Buffer A, updates sentinel.
      //   2. OTA meta-check over cellular takes several seconds while process()
      //      fills Buffers B, C, D … (sentinel already matches, no PIDs).
      //   3. getNewest() returns Buffer D (newest), Buffer A is overwritten.
      //   4. Result: HA never receives LED/beep/SD → "Unbekannt" forever.
      // WiFi is not immune but the OTA check is much faster there, so the race
      // is rarely observed.  With this injection both transports are reliable.
      if (s_send_state_pids) {
        s_send_state_pids = false;
        {
          uint8_t v = enableLedWhite ? 1 : 0;
          store.log(PID_LED_WHITE_STATE, &v, 1);
          s_lastLedWhite = (int8_t)v;
        }
        {
          uint8_t v = enableBeep ? 1 : 0;
          store.log(PID_BEEP_STATE, &v, 1);
          s_lastBeep = (int8_t)v;
        }
        if (state.check(STATE_NET_READY)) {
          uint8_t v = state.check(STATE_WIFI_CONNECTED) ? 1 : 2;
          store.log(PID_CONN_TYPE, &v, 1);
          s_lastConnType = (int8_t)v;
        }
        {
          uint8_t ov = enableObd ? 1 : 0;
          store.log(PID_OBD_STATE, &ov, 1);
          s_lastObd = (int8_t)ov;
        }
        {
          uint8_t cv = enableCan ? 1 : 0;
          store.log(PID_CAN_STATE, &cv, 1);
          s_lastCan = (int8_t)cv;
        }
        {
          store.log(PID_STANDBY_TIME, &nvsStandbyTimeS, 1);
          s_lastStandbyTime = (int16_t)nvsStandbyTimeS;
        }
        {
          uint8_t dv = enableDeepStandby ? 1 : 0;
          store.log(PID_DEEP_STANDBY, &dv, 1);
          s_lastDeepStandby = (int8_t)dv;
        }
#if STORAGE == STORAGE_SD
        // s_cachedSdTotalMb/Free are kept current by process(); they are 0
        // before the first SD read which HA correctly interprets as "no card".
        store.log(PID_SD_TOTAL_MB, &s_cachedSdTotalMb, 1);
        store.log(PID_SD_FREE_MB,  &s_cachedSdFreeMb,  1);
#endif
      }
      store.tailer();
      Serial.print("[DAT] ");
      Serial.println(store.buffer());

      // start transmission
      // Snapshot enableLedWhite before the (blocking) transmit call so that
      // if the main task processes a LED_WHITE=0 /api/control command while
      // teleClient.transmit() is running, the LED is still driven LOW after
      // the transmission completes.  Without the snapshot, the check at the
      // second #ifdef PIN_LED block could see enableLedWhite=false and skip
      // the LOW write, leaving the LED stuck on.
#ifdef PIN_LED
      const bool ledWhiteFlash = enableLedWhite;
      if (ledWhiteFlash) digitalWrite(PIN_LED, HIGH);
#endif

      if (teleClient.transmit(store.buffer(), store.length())) {
        // successfully sent
        connErrors = 0;
        showStats();
      } else {
        timeoutsNet++;
        connErrors++;
        printTimeoutStats();
        if (connErrors < MAX_CONN_ERRORS_RECONNECT) {
          // quick reconnect
          if (!teleClient.connect(true)) {
            // Quick reconnect failed while the WiFi radio is still up.
            // Check if this is a heap-fragmentation failure (the TLS handshake
            // cannot allocate its internal buffers) rather than a transient
            // server-side error.  ESP.getMaxAllocHeap() returns the largest
            // contiguous free DRAM block; values below TLS_MIN_FREE_HEAP
            // indicate that mbedtls_ssl_setup()'s 2×17 KB record buffers
            // cannot be satisfied even if total free memory is nominally OK.
            // In that case waiting for MAX_CONN_ERRORS_RECONNECT attempts
            // wastes ~40 s in an unrecoverable state.  Disconnect WiFi now to
            // trigger the outer loop's WiFi-restart path (begin + setup), which
            // stops and re-starts the WiFi driver.  The driver's internal DRAM
            // allocations are freed by esp_wifi_stop() and re-initialised by
            // esp_wifi_start(), coalescing the fragmented heap and giving the
            // next TLS handshake a contiguous block to work with.
#if ENABLE_WIFI
            if (state.check(STATE_WIFI_CONNECTED) &&
                ESP.getMaxAllocHeap() < TLS_MIN_FREE_HEAP) {
              Serial.printf("[WIFI] Low heap (%u bytes max block) after TLS fail, restarting WiFi\n",
                            (unsigned)ESP.getMaxAllocHeap());
              teleClient.wifi.end();
              state.clear(STATE_NET_READY | STATE_WIFI_CONNECTED);
              break;
            }
#endif
          }
        }
      }
#ifdef PIN_LED
      if (ledWhiteFlash) digitalWrite(PIN_LED, LOW);
#endif
      store.purge();

      teleClient.inbound();

      if (state.check(STATE_CELL_CONNECTED) && !teleClient.cell.check(1000)) {
        Serial.println("[CELL] Not in service");
        state.clear(STATE_NET_READY | STATE_CELL_CONNECTED);
        break;
      }

      if (syncInterval > 10000 && millis() - teleClient.lastSyncTime > syncInterval) {
        Serial.println("[NET] Poor connection");
        timeoutsNet++;
        if (!teleClient.connect()) {
          connErrors++;
        }
      }

      if (connErrors >= MAX_CONN_ERRORS_RECONNECT) {
#if ENABLE_WIFI
        if (state.check(STATE_WIFI_CONNECTED)) {
          teleClient.wifi.end();
          state.clear(STATE_NET_READY | STATE_WIFI_CONNECTED);
          break;
        }
#endif
        if (state.check(STATE_CELL_CONNECTED)) {
          teleClient.cell.end();
          state.clear(STATE_NET_READY | STATE_CELL_CONNECTED);
          break;
        }
      }

      if (deviceTemp >= COOLING_DOWN_TEMP) {
        // device too hot, cool down by pause transmission
        Serial.print("HIGH DEVICE TEMP: ");
        Serial.println(deviceTemp);
        bufman.purge();
      }

    }
  }
}

/*******************************************************************************
  Implementing stand-by mode
*******************************************************************************/
void standby()
{
  state.set(STATE_STANDBY);

#if STORAGE == STORAGE_SD
  // Safety net: if s_ota_pending is set (e.g. esp_restart() failed in
  // performPullOtaCheck), apply the staged firmware now before shutting down.
  // Normally the device restarts immediately after staging and the boot-time
  // flash path handles this — this block should rarely execute.
  if (s_ota_pending && state.check(STATE_STORAGE_READY)) {
    s_ota_active = true;
    delay(OTA_TELEMETRY_YIELD_DELAY_MS); // give the telemetry task one scheduling cycle to yield
    if (performPullOtaFlash()) {
      // Flash succeeded; reboot timer is running — block here until it fires.
      while (true) delay(1000);
    }
    // Flash failed: clear flags and fall through to normal standby.
    s_ota_active = false;
    s_ota_pending = false;
  }
#endif

#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    logger.end();
  }
#endif

#if !GNSS_ALWAYS_ON && GNSS == GNSS_STANDALONE
  if (state.check(STATE_GPS_READY)) {
    Serial.println("[GNSS] OFF");
    sys.gpsEnd(true);
    state.clear(STATE_GPS_READY | STATE_GPS_ONLINE);
    gd = 0;
  }
#endif

  state.clear(STATE_WORKING | STATE_OBD_READY | STATE_STORAGE_READY);
  // this will put co-processor into sleep mode
#if ENABLE_OLED
  oled.print("STANDBY");
  delay(1000);
  oled.clear();
#endif
  Serial.println("STANDBY");
  obd.enterLowPowerMode();

  // Deep standby: use ESP32 deep sleep for lower power consumption.
  // The device restarts after the wake-up timer expires (nvsStandbyTimeS seconds,
  // minimum 5 s).  Wake-up fully reinitialises all subsystems.
  if (enableDeepStandby) {
    uint64_t sleep_us = ((nvsStandbyTimeS >= 5) ? (uint64_t)nvsStandbyTimeS : 180ULL) * 1000000ULL;
    Serial.print("DEEP_SLEEP ");
    Serial.print((unsigned)(sleep_us / 1000000ULL));
    Serial.println("s");
    esp_sleep_enable_timer_wakeup(sleep_us);
    esp_deep_sleep_start();
    // Never reached: device restarts from setup() after wake-up.
  }

#if ENABLE_MEMS
  calibrateMEMS();
  waitMotion(-1);
#elif ENABLE_OBD
  do {
    delay(5000);
  } while (obd.getVoltage() < JUMPSTART_VOLTAGE);
#else
  delay(5000);
#endif
  Serial.println("WAKEUP");
  sys.resetLink();
#if RESET_AFTER_WAKEUP
#if ENABLE_MEMS
  if (mems) mems->end();  
#endif
  ESP.restart();
#endif  
  state.clear(STATE_STANDBY);
}

/*******************************************************************************
  Tasks to perform in idle/waiting time
*******************************************************************************/
void genDeviceID(char* buf)
{
    uint64_t seed = ESP.getEfuseMac() >> 8;
    for (int i = 0; i < 8; i++, seed >>= 5) {
      byte x = (byte)seed & 0x1f;
      if (x >= 10) {
        x = x - 10 + 'A';
        switch (x) {
          case 'B': x = 'W'; break;
          case 'D': x = 'X'; break;
          case 'I': x = 'Y'; break;
          case 'O': x = 'Z'; break;
        }
      } else {
        x += '0';
      }
      buf[i] = x;
    }
    buf[8] = 0;
}

void showSysInfo()
{
  Serial.print("CPU:");
  Serial.print(ESP.getCpuFreqMHz());
  Serial.print("MHz FLASH:");
  Serial.print(ESP.getFlashChipSize() >> 20);
  Serial.println("MB");
  // ESP.getHeapSize() returns the total DRAM heap available to the application.
  // The ESP32's 520 KB SRAM is shared with the WiFi (~60 KB), BLE (~100 KB),
  // and FreeRTOS/driver stacks, so the application heap is typically ~230 KB.
  // PSRAM (external SPI RAM, present on ESP32-WROVER / Freematics ONE+ Model B)
  // is reported separately and is only used when BOARD_HAS_PSRAM is set at
  // compile time (see platformio.ini for details).
  Serial.print("RAM:");
  Serial.print(ESP.getHeapSize() >> 10);
  Serial.print("KB");
  if (psramInit()) {
    Serial.print(" PSRAM:");
    Serial.print(esp_spiram_get_size() >> 20);
    Serial.print("MB");
  }
  Serial.println();

  int rtc = rtc_clk_slow_freq_get();
  if (rtc) {
    Serial.print("RTC:");
    Serial.println(rtc);
  }

#if ENABLE_OLED
  oled.clear();
  oled.print("CPU:");
  oled.print(ESP.getCpuFreqMHz());
  oled.print("Mhz ");
  oled.print(getFlashSize() >> 10);
  oled.println("MB Flash");
#endif

  Serial.print("DEVICE ID:");
  Serial.println(devid);
#if ENABLE_OLED
  oled.print("DEVICE ID:");
  oled.println(devid);
#endif
  Serial.print("FW:");
  Serial.print(FIRMWARE_VERSION);
  Serial.print(" Built:");
  Serial.print(__DATE__);
  Serial.print(" ");
  Serial.println(__TIME__);
  if (nvsVersion[0]) {
    Serial.print("NVS:");
    Serial.println(nvsVersion);
  }
}

void loadConfig()
{
  size_t len;
  len = sizeof(apn);
  apn[0] = 0;
  nvs_get_str(nvs, "CELL_APN", apn, &len);
  if (!apn[0]) {
    strcpy(apn, CELL_APN);
  }

  len = sizeof(simPin);
  simPin[0] = 0;
  nvs_get_str(nvs, "SIM_PIN", simPin, &len);
  if (!simPin[0]) {
    strncpy(simPin, SIM_CARD_PIN, sizeof(simPin) - 1);
    simPin[sizeof(simPin) - 1] = 0;
  }

#if ENABLE_WIFI
  len = sizeof(wifiSSID);
  nvs_get_str(nvs, "WIFI_SSID", wifiSSID, &len);
  len = sizeof(wifiPassword);
  nvs_get_str(nvs, "WIFI_PWD", wifiPassword, &len);
#endif

  // Server settings provisioned via NVS (e.g. via HA integration config_nvs.bin).
  // Override the compile-time SERVER_HOST / SERVER_PORT defaults when present.
  len = sizeof(serverHost);
  serverHost[0] = 0;
  nvs_get_str(nvs, "SERVER_HOST", serverHost, &len);
  if (!serverHost[0]) {
    strncpy(serverHost, SERVER_HOST, sizeof(serverHost) - 1);
    serverHost[sizeof(serverHost) - 1] = 0;
  }
  uint16_t nvsPort = 0;
  nvs_get_u16(nvs, "SERVER_PORT", &nvsPort);
  if (nvsPort) serverPort = nvsPort;

  len = sizeof(webhookPath);
  webhookPath[0] = 0;
  nvs_get_str(nvs, "WEBHOOK_PATH", webhookPath, &len);

  // Cellular-specific server overrides (NVS keys CELL_HOST, CELL_PORT, CELL_PATH).
  // When present, these are used instead of SERVER_HOST / SERVER_PORT /
  // WEBHOOK_PATH for cellular (SIM7600) connections.  Provisioned by the HA
  // integration with hooks.nabu.casa when Nabu Casa cloud is active, so that
  // SIM7600 devices reach the cloud webhook endpoint rather than the Remote UI
  // proxy (*.ui.nabu.casa) which the SIM7600 TLS stack cannot handle.
  len = sizeof(cellServerHost);
  cellServerHost[0] = 0;
  nvs_get_str(nvs, "CELL_HOST", cellServerHost, &len);
  uint16_t nvsCellPort = 0;
  nvs_get_u16(nvs, "CELL_PORT", &nvsCellPort);
  if (nvsCellPort) cellServerPort = nvsCellPort;
  len = sizeof(cellWebhookPath);
  cellWebhookPath[0] = 0;
  nvs_get_str(nvs, "CELL_PATH", cellWebhookPath, &len);

  // Enable HTTP server at runtime when provisioned via config_nvs.bin.
  // Only has an effect when the firmware is compiled with ENABLE_HTTPD=1.
  uint8_t nvsHttpd = 0;
  if (nvs_get_u8(nvs, "ENABLE_HTTPD", &nvsHttpd) == ESP_OK) {
    enableHttpd = nvsHttpd;
  }

#if ENABLE_BLE
  // Enable/disable BLE at runtime.  NVS key ENABLE_BLE is written by the HA
  // integration (0 = off, 1 = on).  Disabling BLE frees ~100 KB of heap,
  // which prevents MBEDTLS_ERR_SSL_ALLOC_FAILED during the TLS handshake for
  // the HTTPS webhook.  The key is absent on un-provisioned devices so the
  // default (enableBle = 1) preserves backwards-compatible behaviour.
  uint8_t nvsBle = 1;
  if (nvs_get_u8(nvs, "ENABLE_BLE", &nvsBle) == ESP_OK) {
    enableBle = nvsBle;
  } else if (webhookPath[0]) {
    // ENABLE_BLE was not provisioned in NVS but webhook mode is active.
    // Auto-disable BLE so the ~100 KB it occupies is available for the TLS
    // handshake (prevents MBEDTLS_ERR_SSL_ALLOC_FAILED on hooks.nabu.casa).
    // Users who want BLE alongside webhooks can set ENABLE_BLE=1 explicitly.
    enableBle = 0;
  }
#endif

  // Enable verbose cellular debug logging at runtime.  NVS key CELL_DEBUG is
  // written by the HA config/options flow (0 = off, 1 = on).  When enabled the
  // firmware prints TX-Preview, hex-dump, AT+CCHSTATUS? and per-packet
  // "Incoming data" diagnostics to the serial console.  Default is 0 (off).
  uint8_t nvsCellDebug = 0;
  if (nvs_get_u8(nvs, "CELL_DEBUG", &nvsCellDebug) == ESP_OK) {
    cellNetDebug = nvsCellDebug;
  }

  // LED and buzzer behaviour overrides written by the HA config/options flow.
  // All default to 1 (enabled) when the NVS key is absent so un-provisioned
  // devices keep the original out-of-box behaviour.
  //
  // LED_RED_EN  – red/power LED (standby / power-on indicator)
  // LED_WHITE_EN – white/network LED (data-transmission indicator)
  // BEEP_EN     – short buzzer beep on each WiFi/cellular connect event
  uint8_t nvsLedRedEn = 1;
  if (nvs_get_u8(nvs, "LED_RED_EN", &nvsLedRedEn) == ESP_OK) {
    enableLedRed = nvsLedRedEn != 0;
  }
  uint8_t nvsLedWhiteEn = 1;
  if (nvs_get_u8(nvs, "LED_WHITE_EN", &nvsLedWhiteEn) == ESP_OK) {
    enableLedWhite = nvsLedWhiteEn != 0;
  }
  uint8_t nvsBeepEn = 1;
  if (nvs_get_u8(nvs, "BEEP_EN", &nvsBeepEn) == ESP_OK) {
    enableBeep = nvsBeepEn != 0;
  }

  // OBD querying enable/disable (NVS key OBD_EN, u8).
  // Defaults to 1 (on) so un-provisioned devices keep existing OBD behaviour.
  uint8_t nvsObdEn = 1;
  if (nvs_get_u8(nvs, "OBD_EN", &nvsObdEn) == ESP_OK) {
    enableObd = nvsObdEn != 0;
  }

  // CAN bus enable/disable (NVS key CAN_EN, u8).
  // Defaults to 0 (off); reserved for future CAN sniffing support.
  uint8_t nvsCanEn = 0;
  if (nvs_get_u8(nvs, "CAN_EN", &nvsCanEn) == ESP_OK) {
    enableCan = nvsCanEn != 0;
  }

  // Deep-standby mode (NVS key DEEP_STANDBY, u8, 0=off 1=on).
  // When enabled the device uses ESP32 deep sleep during standby.
  uint8_t nvsDeepStandby = 0;
  if (nvs_get_u8(nvs, "DEEP_STANDBY", &nvsDeepStandby) == ESP_OK) {
    enableDeepStandby = nvsDeepStandby != 0;
  }

  // Standby-time override (NVS key STANDBY_TIME, u16, seconds, 5-900).
  // 0 means "use compile-time STATIONARY_TIME_TABLE default" (currently 180 s).
  // Values below 5 are clamped to 0 (use default) for safety.
  uint16_t nvsStby = 0;
  if (nvs_get_u16(nvs, "STANDBY_TIME", &nvsStby) == ESP_OK) {
    nvsStandbyTimeS = (nvsStby >= 5) ? nvsStby : 0;
  }

  // Optional data-interval override (milliseconds). Minimum 500 ms to avoid
  // flooding the server or the SD card.  0 / missing = keep compile-time default.
  uint16_t nvsDataInterval = 0;
  if (nvs_get_u16(nvs, "DATA_INTERVAL", &nvsDataInterval) == ESP_OK && nvsDataInterval >= 500) {
    dataInterval = nvsDataInterval;
  }

  // Optional server-sync-interval override (seconds).  0 = keep default.
  uint16_t nvsSyncInterval = 0;
  if (nvs_get_u16(nvs, "SYNC_INTERVAL", &nvsSyncInterval) == ESP_OK && nvsSyncInterval > 0) {
    syncInterval = (int32_t)nvsSyncInterval * 1000;
  }

  // Pull-OTA configuration (firmware v5.2+).
  // OTA_TOKEN: secret path token; when set enables periodic firmware checks.
  len = sizeof(otaToken);
  otaToken[0] = 0;
  nvs_get_str(nvs, "OTA_TOKEN", otaToken, &len);

  // OTA_HOST: HA server for pull-OTA (may differ from serverHost).
  len = sizeof(otaHost);
  otaHost[0] = 0;
  nvs_get_str(nvs, "OTA_HOST", otaHost, &len);
  if (!otaHost[0] && otaToken[0]) {
    // Fall back to serverHost when no separate OTA_HOST is provisioned.
    strncpy(otaHost, serverHost, sizeof(otaHost) - 1);
    otaHost[sizeof(otaHost) - 1] = 0;
  }

  uint16_t nvsOtaPort = 0;
  nvs_get_u16(nvs, "OTA_PORT", &nvsOtaPort);
  if (nvsOtaPort) otaPort = nvsOtaPort;

  uint16_t nvsOtaInterval = 0;
  nvs_get_u16(nvs, "OTA_INTERVAL", &nvsOtaInterval);
  otaCheckIntervalS = nvsOtaInterval;

  // NVS settings version (NVS_VER key).  Written by the HA integration when
  // generating the NVS partition image.  Logged at boot so the user can verify
  // which settings version is active on the device (especially after a serial
  // flash or OTA NVS update).  Absent on devices never provisioned by HA.
  len = sizeof(nvsVersion);
  nvsVersion[0] = 0;
  nvs_get_str(nvs, "NVS_VER", nvsVersion, &len);

  // Vehicle identification (NVS keys VEHICLE_MAKE, VEHICLE_MODEL, VEHICLE_YEAR).
  // Optional – absent on devices not provisioned with vehicle info.
  size_t vlen = sizeof(vehicleMake);
  nvs_get_str(nvs, "VEHICLE_MAKE", vehicleMake, &vlen);
  vlen = sizeof(vehicleModel);
  nvs_get_str(nvs, "VEHICLE_MODEL", vehicleModel, &vlen);
  vlen = sizeof(vehicleYear);
  nvs_get_str(nvs, "VEHICLE_YEAR", vehicleYear, &vlen);

  // Vehicle-specific extra PIDs (NVS key VEHICLE_PIDS).
  // Comma-separated hex values, e.g. "22,23,5A".
  // Parse into vehicleObdData[] so processOBD() can poll them at tier 3.
  vlen = sizeof(vehiclePidsStr);
  vehiclePidsStr[0] = 0;
  nvs_get_str(nvs, "VEHICLE_PIDS", vehiclePidsStr, &vlen);
  vehicleObdDataCount = 0;
  if (vehiclePidsStr[0]) {
    char tmp[sizeof(vehiclePidsStr)];
    strncpy(tmp, vehiclePidsStr, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = 0;
    char *tok = strtok(tmp, ",");
    while (tok && vehicleObdDataCount < MAX_VEHICLE_PIDS) {
      byte pid = (byte)strtol(tok, nullptr, 16);
      // Skip PID 0x00 (the "PIDs supported [01-20]" support bitmap) – it is
      // handled internally by isValidPID() and not a pollable value PID.
      if (pid > 0) {
        vehicleObdData[vehicleObdDataCount].pid   = pid;
        vehicleObdData[vehicleObdDataCount].tier  = 3;
        vehicleObdData[vehicleObdDataCount].value = 0;
        vehicleObdData[vehicleObdDataCount].ts    = 0;
        vehicleObdDataCount++;
      }
      tok = strtok(nullptr, ",");
    }
    if (vehicleObdDataCount > 0) {
      Serial.printf("VEHICLE:%s %s %s pids=%d\n",
                    vehicleMake, vehicleModel, vehicleYear, vehicleObdDataCount);
    }
  }
}

// ---------------------------------------------------------------------------
// Pull-OTA check (Variant 1: authenticated token endpoint;
//                 Variant 2: /local/ public endpoint)
// ---------------------------------------------------------------------------
// Checks the pull-OTA metadata endpoint and, if a new firmware version is
// available, downloads and flashes it using the Arduino Update library.
//
// The metadata endpoint is:
//   GET https://{otaHost}:{otaPort}/api/freematics/ota_pull/{otaToken}/meta.json
//
// For Variant 2 (/local/ deployment) the same path structure is used:
//   GET https://{otaHost}:{otaPort}/local/FreematicsONE/{devid}/version.json
// The caller stores the appropriate prefix in otaToken (e.g. the /local/ path).
//
// Returns true if a firmware update was successfully applied (device will
// reboot shortly after), false otherwise.
// ---------------------------------------------------------------------------

// Shared chunk buffer used by both the download (to SD) and flash (from SD)
// phases.  See the declaration near the top of the file (after s_ota_pending).
// PULL_OTA_MIN_FW_SIZE / PULL_OTA_CHUNK_SIZE / PULL_OTA_CHUNK_TIMEOUT_MS /
// OTA_TELEMETRY_YIELD_DELAY_MS are also defined near the top.

#if STORAGE == STORAGE_SD
// ---------------------------------------------------------------------------
// _applyNvsFromSD()
//
// Writes a staged NVS partition image (/ota_nvs.bin) directly to the NVS
// flash partition so that updated settings (WiFi credentials, LED behaviour,
// BLE, data interval, etc.) take effect on the next boot without requiring a
// serial re-flash.
//
// Called by performPullOtaFlash() AFTER a successful firmware flash, just
// before the reboot timer fires.  If the NVS staging file does not exist the
// function returns true immediately (NVS update is optional).
//
// On any error the staging file is removed and false is returned; the caller
// logs the outcome and continues with the reboot (firmware was already
// flashed successfully, so only the settings update failed).
// ---------------------------------------------------------------------------
static bool _applyNvsFromSD()
{
  if (!SD.exists(OTA_NVS_PATH)) {
    return true; // no NVS update staged; not an error
  }

  File nvsFile = SD.open(OTA_NVS_PATH, FILE_READ);
  if (!nvsFile) {
    Serial.println("[OTA-PULL] Cannot open NVS staging file");
    SD.remove(OTA_NVS_PATH);
    return false;
  }
  size_t nvsSize = nvsFile.size();

  // Sanity check: the NVS image must be at least 4 KB and at most the full
  // partition size (20 KB).  Anything outside that range is corrupt.
  if (nvsSize < 4096 || nvsSize > 0x5000) {
    nvsFile.close();
    Serial.printf("[OTA-PULL] NVS staging file has invalid size: %u — skipping\n",
                  (unsigned)nvsSize);
    SD.remove(OTA_NVS_PATH);
    return false;
  }

  // Read the entire NVS image into a heap buffer BEFORE touching the NVS flash
  // partition.  This is critical: if we erased the partition first and then
  // encountered an SD read error mid-write, the device would reboot with a
  // blank NVS — losing WiFi credentials, OTA_TOKEN, and all other settings.
  // By buffering the full image first we guarantee that either (a) the SD read
  // succeeds and we can safely erase + write, or (b) we leave the existing NVS
  // intact and return false so the caller logs "rebooting with old NVS".
  //
  // Allocate nvsSize rounded up to a 4-byte boundary so the alignment padding
  // applied to the last write chunk (esp_partition_write requires 4-byte-aligned
  // sizes) never writes beyond the allocated region.
  size_t nvsBufSize = (nvsSize + 3) & ~3UL;
  uint8_t* nvsBuf = (uint8_t*)malloc(nvsBufSize);
  if (!nvsBuf) {
    nvsFile.close();
    Serial.println("[OTA-PULL] NVS: not enough RAM to buffer image — skipping NVS update");
    SD.remove(OTA_NVS_PATH);
    return false;
  }
  // Pre-fill the alignment-padding tail with 0xFF so it is ready for the write.
  if (nvsBufSize > nvsSize) {
    memset(nvsBuf + nvsSize, 0xFF, nvsBufSize - nvsSize);
  }

  size_t readTotal = 0;
  bool readOk = true;
  while (readTotal < nvsSize) {
    int toRead = (int)(nvsSize - readTotal);
    if (toRead > (int)PULL_OTA_CHUNK_SIZE) toRead = (int)PULL_OTA_CHUNK_SIZE;
    int n = nvsFile.read(nvsBuf + readTotal, toRead);
    if (n <= 0) {
      Serial.printf("[OTA-PULL] NVS SD read error at offset %u\n", (unsigned)readTotal);
      readOk = false;
      break;
    }
    readTotal += (size_t)n;
  }
  nvsFile.close();
  SD.remove(OTA_NVS_PATH);

  if (!readOk || readTotal != nvsSize) {
    free(nvsBuf);
    Serial.println("[OTA-PULL] NVS staging file read incomplete — NVS unchanged");
    return false;
  }

  const esp_partition_t* nvsPart = esp_partition_find_first(
      ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_NVS, "nvs");
  if (!nvsPart) {
    free(nvsBuf);
    Serial.println("[OTA-PULL] NVS partition not found in partition table");
    return false;
  }

  // Deinit the NVS library before touching the underlying flash so no
  // in-memory pages are written back after we erase the partition.
  nvs_flash_deinit();

  esp_err_t err = esp_partition_erase_range(nvsPart, 0, nvsPart->size);
  if (err != ESP_OK) {
    free(nvsBuf);
    Serial.printf("[OTA-PULL] NVS partition erase failed: %d\n", (int)err);
    return false;
  }

  // Write the buffered NVS image to the flash partition in PULL_OTA_CHUNK_SIZE
  // (4 KB) chunks.  The SD file has already been read and removed above.
  // The tail of nvsBuf was pre-filled with 0xFF so alignment padding for the
  // last chunk is already in place — no per-chunk memset is needed.
  size_t written = 0;
  bool writeOk = true;
  while (written < nvsSize) {
    size_t toWrite = nvsSize - written;
    if (toWrite > PULL_OTA_CHUNK_SIZE) toWrite = PULL_OTA_CHUNK_SIZE;
    // Round up to 4-byte boundary for esp_partition_write; tail bytes are 0xFF.
    size_t aligned = (toWrite + 3) & ~3UL;
    err = esp_partition_write(nvsPart, written, nvsBuf + written, aligned);
    if (err != ESP_OK) {
      Serial.printf("[OTA-PULL] NVS partition write failed at offset %u: %d\n",
                    (unsigned)written, (int)err);
      writeOk = false;
      break;
    }
    written += toWrite;
  }
  free(nvsBuf);

  if (!writeOk) {
    return false;
  }

  Serial.printf("[OTA-PULL] NVS settings applied: %u bytes written\n", (unsigned)written);
#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL NVS OK");
#endif
  return true;
}

// ---------------------------------------------------------------------------
// performPullOtaFlash()
//
// Reads the firmware binary staged on the SD card (/ota_fw.bin) and writes
// it to the OTA flash partition using the Arduino Update library.  Called by
// standby() at the next power-down / sleep transition — NEVER during active
// telemetry — so no live data is lost.
//
// Pre-conditions (checked here):
//   • s_ota_pending == true  (set by performPullOtaCheck() after download)
//   • OTA_META_PATH exists on SD and contains the expected byte count
//   • OTA_PENDING_PATH exists on SD and its size matches OTA_META_PATH
//
// Returns true if the flash succeeded and the reboot timer is running.
// On any error, staging files are cleaned up and false is returned so that
// standby() can clear s_ota_pending and continue normally.
// ---------------------------------------------------------------------------
static bool performPullOtaFlash()
{
  // --- Verify staging files ------------------------------------------------
  if (!SD.exists(OTA_PENDING_PATH)) {
    Serial.println("[OTA-PULL] Staged firmware not found on SD");
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_NOT_FOUND");
#endif
    SD.remove(OTA_META_PATH);
    return false;
  }

  // Read expected size from companion meta file.
  unsigned long expectedSize = 0;
  {
    File mf = SD.open(OTA_META_PATH, FILE_READ);
    if (mf) {
      char buf[16] = {0};
      mf.readBytesUntil('\n', buf, sizeof(buf) - 1);
      mf.close();
      expectedSize = strtoul(buf, nullptr, 10);
    }
  }
  {
    File ff = SD.open(OTA_PENDING_PATH, FILE_READ);
    unsigned long actual = ff ? (unsigned long)ff.size() : 0UL;
    if (ff) ff.close();
    if (expectedSize < PULL_OTA_MIN_FW_SIZE || actual != expectedSize) {
      Serial.printf("[OTA-PULL] SD staging size mismatch: file=%lu expected=%lu — removing\n",
                    actual, expectedSize);
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_SIZE");
#endif
      SD.remove(OTA_PENDING_PATH);
      SD.remove(OTA_META_PATH);
      return false;
    }
  }

  size_t fwSize = (size_t)expectedSize;
  Serial.printf("[OTA-PULL] Flashing staged firmware from SD: %u bytes\n", (unsigned)fwSize);
#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    char diag[48];
    snprintf(diag, sizeof(diag), "OTA-PULL FLASH START SIZE=%u", (unsigned)fwSize);
    logger.logEvent(diag);
  }
#endif

  if (!Update.begin(fwSize)) {
    Serial.printf("[OTA-PULL] Update.begin failed: %s\n", Update.errorString());
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=UPD_BEGIN");
#endif
    return false;
  }

  File fwFile = SD.open(OTA_PENDING_PATH, FILE_READ);
  if (!fwFile) {
    Serial.println("[OTA-PULL] Cannot open staged firmware for reading");
    Update.abort();
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_OPEN_READ");
#endif
    return false;
  }

  size_t written = 0;
  uint32_t t0 = millis();
  size_t lastLogAt = 0;

  while (written < fwSize) {
    int toRead = (int)(fwSize - written);
    if (toRead > (int)PULL_OTA_CHUNK_SIZE) toRead = (int)PULL_OTA_CHUNK_SIZE;
    int n = fwFile.read(s_otaChunkBuf, toRead);
    if (n <= 0) {
      Serial.printf("[OTA-PULL] SD read error at offset %u\n", (unsigned)written);
      Update.abort();
      fwFile.close();
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_READ");
#endif
      return false;
    }
    size_t w = Update.write(s_otaChunkBuf, (size_t)n);
    if (w != (size_t)n) {
      Serial.printf("[OTA-PULL] Flash write error at offset %u\n", (unsigned)written);
      Update.abort();
      fwFile.close();
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FLASH_WRITE");
#endif
      return false;
    }
    written += (size_t)n;

    // Log progress every 10%.
    if (written - lastLogAt >= (fwSize / 10 ? fwSize / 10 : 1)) {
      lastLogAt = written;
      Serial.printf("[OTA-PULL] Flash %u / %u bytes (%.0f%%) in %u ms\n",
                    (unsigned)written, (unsigned)fwSize,
                    100.0f * written / fwSize, (unsigned)(millis() - t0));
    }
  }
  fwFile.close();

  if (!Update.end()) {
    Serial.printf("[OTA-PULL] Update.end failed: %s\n", Update.errorString());
    SD.remove(OTA_PENDING_PATH);
    SD.remove(OTA_META_PATH);
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=UPD_END");
#endif
    return false;
  }

  // --- Flash successful: clean up SD, log, apply NVS settings if staged -----
  SD.remove(OTA_PENDING_PATH);
  SD.remove(OTA_META_PATH);

  Serial.printf("[OTA-PULL] Flash from SD successful: %u bytes in %u ms\n",
                (unsigned)written, (unsigned)(millis() - t0));

  // Apply NVS settings update if staged.  This is done AFTER a successful
  // firmware flash so a settings-write failure never prevents the firmware
  // update.  On failure the device still reboots into the new firmware
  // (with old NVS settings); the settings will be retried on the next OTA
  // check interval (the HA side keeps nvs_version unsynchronised until the
  // device successfully downloads and applies nvs.bin).
  {
    bool _nvsStaged = SD.exists(OTA_NVS_PATH);
    if (_applyNvsFromSD()) {
      if (_nvsStaged) {
        Serial.println("[OTA-PULL] Settings (NVS) updated successfully");
      } else {
        Serial.println("[OTA-PULL] No NVS settings staged — rebooting with firmware only");
      }
    } else {
      Serial.println("[OTA-PULL] Settings (NVS) update failed — rebooting with old NVS");
    }
  }

#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    char diag[64];
    snprintf(diag, sizeof(diag), "OTA-PULL FLASH OK FW=%s SIZE=%u",
             FIRMWARE_VERSION, (unsigned)written);
    logger.logEvent(diag);
    logger.flush();  // ensure log entry survives the reboot
  }
#endif

  // s_ota_active remains true; device reboots shortly.
  static esp_timer_handle_t s_ota_flash_timer = NULL;
  if (!s_ota_flash_timer) {
    esp_timer_create_args_t args = {};
    args.callback        = [](void*) { esp_restart(); };
    args.dispatch_method = ESP_TIMER_TASK;
    args.name            = "ota_flash_reboot";
    esp_timer_create(&args, &s_ota_flash_timer);
  } else {
    esp_timer_stop(s_ota_flash_timer);
  }
  esp_timer_start_once(s_ota_flash_timer, 1500000);
  return true;
}
#endif  // STORAGE == STORAGE_SD

// ---------------------------------------------------------------------------
// _maskOtaHost()
//
// Returns a privacy-safe representation of an OTA hostname for serial
// logging.  Shows only the first 8 characters followed by "..." when the
// hostname is longer than 12 characters, preventing NabuCasa subdomain IDs
// from appearing verbatim in serial output.
// ---------------------------------------------------------------------------
static String _maskOtaHost(const char* host) {
  if (!host || !host[0]) return String("(none)");
  size_t n = strlen(host);
  if (n > 12) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%.8s...", host);
    return String(buf);
  }
  return String(host);
}

// ---------------------------------------------------------------------------
// performPullOtaCheck()
//
// Fetches the pull-OTA metadata endpoint and, when a newer firmware version
// is available, downloads it.  Works over WiFi only.
//
// OTA over cellular is not supported: TLS on SIM7600E-H modems is unreliable
// (TLS error 15 against Cloudflare and Nabu Casa endpoints) and cannot be
// resolved with reasonable effort.  Use WiFi (or a mobile hotspot) for OTA.
//
// For STORAGE == STORAGE_SD the binary is saved to the SD card staging file
// (OTA_PENDING_PATH) and the flash is DEFERRED to the next standby
// transition.  s_ota_pending is set to true on a successful download so
// that standby() calls performPullOtaFlash().
//
// For other storage configurations (STORAGE_NONE / STORAGE_SPIFFS) the old
// direct-flash path is used as a fallback.
//
// Returns true only when the direct-flash path has started (reboot imminent).
// Returns false in all other cases, including the SD-staging success case
// (caller must NOT block waiting for a reboot when false is returned).
// ---------------------------------------------------------------------------
bool performPullOtaCheck()
{
  if (!otaToken[0] || !otaHost[0]) return false;

  // OTA is only supported over WiFi.  Cellular is not supported because
  // TLS on SIM7600E-H modems cannot reliably connect to the OTA endpoint
  // (TLS error 15 against Cloudflare / Nabu Casa Remote UI domains).
#if ENABLE_WIFI
  if (!WiFi.isConnected()) return false;
#else
  return false;  // No WiFi compiled in — OTA unavailable
#endif

#if STORAGE == STORAGE_SD
  // If a firmware is already staged on SD (from a previous download that set
  // s_ota_pending before the esp_restart() fired), the restart did not happen
  // yet.  Trigger it now so the boot-time flash runs cleanly.
  if (s_ota_pending) {
    Serial.println("[OTA-PULL] Firmware already staged on SD, restarting to flash");
    esp_restart();
    return false;  // unreachable
  }
#endif

  // ---- Step 1: Fetch metadata JSON ----------------------------------------
  // Build the metadata path: /api/freematics/ota_pull/{token}/meta.json
  char metaPath[384];
  snprintf(metaPath, sizeof(metaPath),
           "/api/freematics/ota_pull/%s/meta.json", otaToken);

  Serial.printf("[OTA-PULL] URL: https://%s:%u/api/freematics/ota_pull/%.8s.../meta.json\n",
                _maskOtaHost(otaHost).c_str(), (unsigned)otaPort, otaToken);

  char metaBuf[2048];
  int metaBytes = 0;
  char* metaBody = nullptr;

#if ENABLE_WIFI
  // WifiHTTP::open() handles all session-reuse and heap-guard logic:
  //   • Same host as telemetry: reuse the existing TLS session (zero cost).
  //   • Different host, heap OK: stop() + connect() atomically.
  //   • Low heap: Guard 1 or Guard 2 fires, returns false → caller restarts WiFi.
  if (!teleClient.wifi.open(otaHost, otaPort)) {
    Serial.printf("[OTA-PULL] Cannot connect to %s:%u\n", _maskOtaHost(otaHost).c_str(), (unsigned)otaPort);
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=CONNECT");
#endif
    return false;
  }

  if (!teleClient.wifi.send(METHOD_GET, metaPath)) {
    Serial.println("[OTA-PULL] META send failed");
    teleClient.wifi.close();
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=META_SEND");
#endif
    return false;
  }

  metaBody = teleClient.wifi.receive(metaBuf, sizeof(metaBuf) - 1, &metaBytes);
  if (!metaBody || teleClient.wifi.code() != 200) {
    Serial.printf("[OTA-PULL] META HTTP %u\n", (unsigned)teleClient.wifi.code());
    teleClient.wifi.close();
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) {
      char _ota_diag[48];
      snprintf(_ota_diag, sizeof(_ota_diag), "OTA-PULL ERR=META_HTTP%d", (int)teleClient.wifi.code());
      logger.logEvent(_ota_diag);
    }
#endif
    return false;
  }
  metaBuf[metaBytes < (int)sizeof(metaBuf) - 1 ? metaBytes : (int)sizeof(metaBuf) - 1] = '\0';
  // Do NOT close the WiFi connection here: keep it alive so both the next
  // telemetry packet and the next OTA check (60 s later) can reuse the same
  // TLS session.  receive() has already updated m_state (HTTP_CONNECTED when
  // the server sent keep-alive, HTTP_DISCONNECTED when it sent Connection:close).
  // In the keep-alive case this avoids one needless TLS teardown+handshake cycle
  // per OTA check interval.  In the close case open() will call client.stop()
  // immediately before client.connect(), preventing heap fragmentation by other
  // tasks from grabbing the freed TLS block between the two calls.
#endif  // ENABLE_WIFI

  // ---- Parse metadata JSON ------------------------------------------------

  // Parse "available": true / false
  if (!strstr(metaBody, "\"available\":true") && !strstr(metaBody, "\"available\": true")) {
    Serial.println("[OTA-PULL] No update available");
    return false;
  }

  // Parse optional nvs_only flag — set by the HA server when the firmware
  // binary was already delivered (version matches in ota_pull_state.json) but
  // the NVS settings partition is outdated (e.g. WiFi credentials or LED/beep
  // state changed, or nvs.bin failed to download alongside the firmware in a
  // previous cycle due to heap fragmentation after the large firmware transfer).
  // In this mode the device skips firmware download entirely, fetches only the
  // small NVS binary with a fresh heap (no prior fragmentation), applies it
  // directly to the NVS flash partition, and restarts to activate the settings.
  bool nvsOnly = (strstr(metaBody, "\"nvs_only\":true")  != nullptr ||
                  strstr(metaBody, "\"nvs_only\": true") != nullptr);

  // Parse optional nvs_url field (present in both normal and nvs_only updates).
  char nvsPath[256] = "";
  {
    char* nvsField = strstr(metaBody, "\"nvs_url\":");
    if (nvsField) {
      char* start = strchr(nvsField + 10, '"');
      if (start) {
        start++;
        char* end = strchr(start, '"');
        if (end && (size_t)(end - start) < sizeof(nvsPath) - 1) {
          memcpy(nvsPath, start, end - start);
          nvsPath[end - start] = '\0';
        }
      }
    }
  }

  // ---- NVS-only update path -----------------------------------------------
  // Entered when firmware is current but NVS settings are outdated.
  // Downloads only the NVS binary (heap is fresh — no prior firmware download),
  // applies it directly, and restarts to activate the new settings.
#if STORAGE == STORAGE_SD
  if (nvsOnly) {
    if (!state.check(STATE_STORAGE_READY)) {
      Serial.println("[OTA-PULL] NVS-only: SD not ready, skipping");
      return false;
    }
    Serial.println("[OTA-PULL] NVS-only update: downloading settings binary");
    if (SD.exists(OTA_NVS_PATH)) SD.remove(OTA_NVS_PATH);
    if (nvsPath[0]) {
#if ENABLE_WIFI
      if (teleClient.wifi.open(otaHost, otaPort) &&
          teleClient.wifi.send(METHOD_GET, nvsPath)) {
        int _nvsCL = 0;
        int _nvsHC = teleClient.wifi.receiveHeaders(&_nvsCL);
        if (_nvsHC == 200 && _nvsCL > 0) {
          File _nvsFile = SD.open(OTA_NVS_PATH, FILE_WRITE);
          if (_nvsFile) {
            WiFiClientSecure& _nvsRaw = teleClient.wifi.rawClient();
            size_t _nvsWr = 0, _nvsExp = (size_t)_nvsCL;
            bool _nvsOk = true;
            while (_nvsWr < _nvsExp) {
              uint32_t _t1 = millis();
              while (!_nvsRaw.available() && millis() - _t1 < PULL_OTA_CHUNK_TIMEOUT_MS) delay(1);
              if (!_nvsRaw.available()) { _nvsOk = false; break; }
              int _nr = (int)(_nvsExp - _nvsWr);
              if (_nr > (int)PULL_OTA_CHUNK_SIZE) _nr = (int)PULL_OTA_CHUNK_SIZE;
              int _n = _nvsRaw.read(s_otaChunkBuf, _nr);
              if (_n <= 0) { _nvsOk = false; break; }
              if ((size_t)_nvsFile.write(s_otaChunkBuf, (size_t)_n) != (size_t)_n) { _nvsOk = false; break; }
              _nvsWr += (size_t)_n;
            }
            _nvsFile.close();
            if (!_nvsOk || _nvsWr != _nvsExp) {
              Serial.println("[OTA-PULL] NVS download incomplete — settings unchanged");
              SD.remove(OTA_NVS_PATH);
            } else {
              Serial.printf("[OTA-PULL] NVS staged: %u bytes\n", (unsigned)_nvsWr);
            }
          }
        } else {
          Serial.printf("[OTA-PULL] NVS HTTP %d — settings unchanged\n", _nvsHC);
        }
        teleClient.wifi.close();
      } else {
        Serial.println("[OTA-PULL] NVS connect/send failed — settings unchanged");
        teleClient.wifi.close();
      }
#endif  // ENABLE_WIFI
    }
    // Only restart if NVS was successfully staged on SD.  If the download
    // failed leave the device running and let it retry on the next interval.
    if (!SD.exists(OTA_NVS_PATH)) {
      Serial.println("[OTA-PULL] NVS-only: download failed, will retry on next check");
      return false;
    }
    if (_applyNvsFromSD()) {
      Serial.println("[OTA-PULL] Settings (NVS) applied — restarting");
      esp_restart();
      return false;  // unreachable
    } else {
      // Apply failed (e.g. RAM allocation error, SD read error, flash write
      // error).  The NVS partition is unchanged; leave the device running so
      // it retries the download + apply on the next OTA check interval.
      Serial.println("[OTA-PULL] Settings (NVS) apply failed — will retry on next check");
      return false;
    }
  }
#endif  // STORAGE == STORAGE_SD
  if (nvsOnly) {
    // No SD storage available — cannot download NVS binary; skip silently.
    Serial.println("[OTA-PULL] NVS-only update skipped (no SD storage)");
    return false;
  }

  // Parse firmware "size" field.
  size_t fwSize = 0;
  char* sizeField = strstr(metaBody, "\"size\":");
  if (!sizeField) {
    Serial.println("[OTA-PULL] META: missing size field");
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=META_NOSIZE");
#endif
    return false;
  }
  fwSize = (size_t)atol(sizeField + 7);
  if (fwSize < PULL_OTA_MIN_FW_SIZE) { // sanity check: firmware must be at least 64 KB
    Serial.printf("[OTA-PULL] META: implausible size %u\n", (unsigned)fwSize);
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=META_SIZE");
#endif
    return false;
  }

  Serial.printf("[OTA-PULL] Update available: %u bytes\n", (unsigned)fwSize);
#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    char _ota_diag[48];
    snprintf(_ota_diag, sizeof(_ota_diag), "OTA-PULL START SIZE=%u", (unsigned)fwSize);
    logger.logEvent(_ota_diag);
  }
#endif

  // Parse optional sha256 field for post-download integrity verification.
  // When present, the downloaded firmware file is checked against this digest
  // immediately after the download loop — before the companion meta file is
  // written.  A mismatch (e.g. due to Transfer-Encoding: chunked manglings
  // or cellular bit-errors) is caught here and the staging file is removed so
  // the next OTA interval triggers a clean retry.  Missing field → skip check.
  char fwSha256Hex[65] = "";
  {
    char* sf = strstr(metaBody, "\"sha256\":");
    if (sf) {
      char* s = strchr(sf + 9, '"');
      if (s) {
        s++;
        char* e = strchr(s, '"');
        if (e && (size_t)(e - s) == 64) {
          memcpy(fwSha256Hex, s, 64);
          fwSha256Hex[64] = '\0';
          // Validate: all 64 chars must be valid hex [0-9a-fA-F] (upper or lower).
          // Non-hex content (e.g. malformed meta) is treated as absent (skip verify).
          for (int _i = 0; _i < 64; _i++) {
            char _c = fwSha256Hex[_i];
            if (!((_c >= '0' && _c <= '9') || (_c >= 'a' && _c <= 'f') ||
                  (_c >= 'A' && _c <= 'F'))) {
              fwSha256Hex[0] = '\0';
              break;
            }
          }
        }
      }
    }
  }

  // ---- Step 2: Download firmware ------------------------------------------
  char fwPath[384];
  snprintf(fwPath, sizeof(fwPath),
           "/api/freematics/ota_pull/%s/firmware.bin", otaToken);

#if STORAGE == STORAGE_SD
  // --- SD-staging path (default): download to /ota_fw.bin, flash at standby -
  // This leaves active telemetry running; no data is lost.
  if (state.check(STATE_STORAGE_READY)) {
    // a. Clean up any leftover files.
    if (SD.exists(OTA_PENDING_PATH)) SD.remove(OTA_PENDING_PATH);
    if (SD.exists(OTA_META_PATH)) SD.remove(OTA_META_PATH);

    File fwFile = SD.open(OTA_PENDING_PATH, FILE_WRITE);
    if (!fwFile) {
      Serial.println("[OTA-PULL] Cannot create SD staging file");
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_OPEN");
#endif
      return false;
    }

    size_t written = 0;
    uint32_t dlStart = millis();
    size_t lastLogAt = 0;
    bool dlOk = true;

    // Streaming SHA256 context — updated with every chunk written to SD.
    // Verification happens after the download loop and before the meta file
    // is written, so a corrupted download is detected without any flash attempt.
    mbedtls_sha256_context sha256Ctx;
    bool doSha256 = (fwSha256Hex[0] != '\0');
    if (doSha256) {
      mbedtls_sha256_init(&sha256Ctx);
      mbedtls_sha256_starts_ret(&sha256Ctx, 0);
    }


#if ENABLE_WIFI
    if (!teleClient.wifi.open(otaHost, otaPort)) {
      Serial.printf("[OTA-PULL] FW connect failed to %s:%u\n", _maskOtaHost(otaHost).c_str(), (unsigned)otaPort);
      fwFile.close();
      SD.remove(OTA_PENDING_PATH);
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FW_CONNECT");
#endif
      return false;
    }

    if (!teleClient.wifi.send(METHOD_GET, fwPath)) {
      Serial.println("[OTA-PULL] FW send failed");
      teleClient.wifi.close();
      fwFile.close();
      SD.remove(OTA_PENDING_PATH);
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FW_SEND");
#endif
      return false;
    }

    int contentLength = 0;
    int httpCode = teleClient.wifi.receiveHeaders(&contentLength);
    if (httpCode != 200) {
      Serial.printf("[OTA-PULL] FW HTTP %d\n", httpCode);
      teleClient.wifi.close();
      fwFile.close();
      SD.remove(OTA_PENDING_PATH);
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) {
        char _ota_diag[48];
        snprintf(_ota_diag, sizeof(_ota_diag), "OTA-PULL ERR=FW_HTTP%d", httpCode);
        logger.logEvent(_ota_diag);
      }
#endif
      return false;
    }
    if (contentLength > 0 && (size_t)contentLength != fwSize) {
      Serial.printf("[OTA-PULL] FW size mismatch: meta=%u header=%d\n",
                    (unsigned)fwSize, contentLength);
      fwSize = (size_t)contentLength;
    }

    WiFiClientSecure& rawSock = teleClient.wifi.rawClient();

    while (written < fwSize) {
      uint32_t chunkStart = millis();
      while (!rawSock.available() && millis() - chunkStart < PULL_OTA_CHUNK_TIMEOUT_MS) delay(1);
      if (!rawSock.available()) {
        Serial.printf("[OTA-PULL] Recv timeout at offset %u\n", (unsigned)written);
#if STORAGE != STORAGE_NONE
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=RECV_TIMEOUT");
#endif
        dlOk = false;
        break;
      }
      int toRead = (int)(fwSize - written);
      if (toRead > (int)PULL_OTA_CHUNK_SIZE) toRead = (int)PULL_OTA_CHUNK_SIZE;
      int n = rawSock.read(s_otaChunkBuf, toRead);
      if (n <= 0) {
        Serial.printf("[OTA-PULL] Read error at offset %u\n", (unsigned)written);
#if STORAGE != STORAGE_NONE
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=RECV_READ");
#endif
        dlOk = false;
        break;
      }
      size_t nw = fwFile.write(s_otaChunkBuf, (size_t)n);
      if (nw != (size_t)n) {
        // First write attempt failed or was incomplete; retry once.
        Serial.printf("[OTA-PULL] SD write retry at offset %u (got %u/%u)\n",
                      (unsigned)written, (unsigned)nw, (unsigned)n);
        delay(50);
        if (nw < (size_t)n) {
          size_t nw2 = fwFile.write(s_otaChunkBuf + nw, (size_t)n - nw);
          nw += nw2;
        }
        if (nw != (size_t)n) {
          Serial.printf("[OTA-PULL] SD write error at offset %u\n", (unsigned)written);
#if STORAGE != STORAGE_NONE
          if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SD_WRITE");
#endif
          dlOk = false;
          break;
        }
        Serial.printf("[OTA-PULL] SD write retry succeeded at offset %u\n", (unsigned)written);
      }
      written += (size_t)n;
      if (doSha256) mbedtls_sha256_update_ret(&sha256Ctx, s_otaChunkBuf, (size_t)n);
      if (written - lastLogAt >= (fwSize / 10 ? fwSize / 10 : 1)) {
        lastLogAt = written;
        Serial.printf("[OTA-PULL] %u / %u bytes (%.0f%%) in %u ms\n",
                      (unsigned)written, (unsigned)fwSize,
                      100.0f * written / fwSize, (unsigned)(millis() - dlStart));
      }
    }
    fwFile.close();
    teleClient.wifi.close();
#endif  // ENABLE_WIFI

    if (!dlOk || written != fwSize) {
      Serial.printf("[OTA-PULL] Download incomplete (%u / %u bytes) — staging file removed\n",
                    (unsigned)written, (unsigned)fwSize);
      SD.remove(OTA_PENDING_PATH);
      if (doSha256) mbedtls_sha256_free(&sha256Ctx);
      return false;
    }

    // Verify SHA256 of the downloaded firmware against the expected digest from
    // meta.json.  Done BEFORE writing the companion meta file so that a corrupt
    // download (e.g. chunked-encoding artefacts from the reverse-proxy, or a
    // partial transfer) is detected immediately and the staging file is removed
    // — the next OTA check interval will retry with a clean download.
    if (doSha256) {
      static const int SHA256_DIGEST_BYTES = 32;  // SHA-256 produces a 256-bit (32-byte) digest
      uint8_t digest[SHA256_DIGEST_BYTES];
      mbedtls_sha256_finish_ret(&sha256Ctx, digest);
      mbedtls_sha256_free(&sha256Ctx);
      char actualHex[SHA256_DIGEST_BYTES * 2 + 1];
      for (int i = 0; i < SHA256_DIGEST_BYTES; i++) snprintf(actualHex + i * 2, 3, "%02x", digest[i]);
      actualHex[SHA256_DIGEST_BYTES * 2] = '\0';
      if (strncmp(actualHex, fwSha256Hex, SHA256_DIGEST_BYTES * 2) != 0) {
        Serial.printf("[OTA-PULL] SHA256 mismatch — staging file removed (retry at next interval)\n"
                      "[OTA-PULL]   expected: %s\n"
                      "[OTA-PULL]   actual:   %s\n",
                      fwSha256Hex, actualHex);
#if STORAGE != STORAGE_NONE
        if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=SHA256");
#endif
        SD.remove(OTA_PENDING_PATH);
        return false;
      }
      Serial.println("[OTA-PULL] SHA256 OK");
    }

    // Notify HA that the firmware was downloaded and verified on the device.
    // This is a WiFi-only, best-effort call — OTA proceeds even if it fails.
    // The HA server only updates "OTA letzte Übertragung" upon receiving this
    // request, ensuring the status reflects a device-confirmed download rather
    // than merely a completed server-side transmission.
#if ENABLE_WIFI
    // After streaming a large firmware binary over TLS, the mbedTLS heap is
    // often fragmented below TLS_MIN_FREE_HEAP (~34 KB max block after close).
    // Restart WiFi to coalesce freed TLS/TCP buffers so the confirm request
    // and any subsequent NVS download can open a fresh TLS session.
    if (ESP.getMaxAllocHeap() < TLS_MIN_FREE_HEAP) {
      Serial.printf("[OTA-PULL] Heap fragmented (%u bytes), restarting WiFi\n",
                    (unsigned)ESP.getMaxAllocHeap());
      teleClient.wifi.end();
      teleClient.wifi.begin(wifiSSID, wifiPassword);
      if (!teleClient.wifi.setup(WIFI_JOIN_TIMEOUT)) {
        Serial.println("[OTA-PULL] WiFi reconnect timeout after heap recovery");
      }
    }
    {
      char _confirmPath[128];
      snprintf(_confirmPath, sizeof(_confirmPath),
               "/api/freematics/ota_pull/%s/ota_confirm", otaToken);
      if (teleClient.wifi.open(otaHost, otaPort) &&
          teleClient.wifi.send(METHOD_GET, _confirmPath)) {
        int _confirmCL = 0;
        int _confirmCode = teleClient.wifi.receiveHeaders(&_confirmCL);
        Serial.printf("[OTA-PULL] Confirm %s (HTTP %d)\n",
                      _confirmCode == 200 ? "OK" : "FAILED", _confirmCode);
      } else {
        Serial.println("[OTA-PULL] Confirm request failed (non-fatal)");
      }
      teleClient.wifi.close();
    }
#endif

    // Write companion meta file: expected byte count for integrity check.
    {
      File metaFile = SD.open(OTA_META_PATH, FILE_WRITE);
      if (metaFile) {
        char metaBufOut[16];
        snprintf(metaBufOut, sizeof(metaBufOut), "%u\n", (unsigned)fwSize);
        metaFile.print(metaBufOut);
        metaFile.close();
      }
    }

    // ---- Step 3 (optional): Download NVS settings binary -------------------
    if (SD.exists(OTA_NVS_PATH)) SD.remove(OTA_NVS_PATH);
    if (nvsPath[0]) {
      Serial.printf("[OTA-PULL] Downloading NVS settings from %s\n", nvsPath);
#if ENABLE_WIFI
      if (teleClient.wifi.open(otaHost, otaPort) &&
          teleClient.wifi.send(METHOD_GET, nvsPath)) {
        int nvsContentLen = 0;
        int nvsHttpCode = teleClient.wifi.receiveHeaders(&nvsContentLen);
        if (nvsHttpCode == 200 && nvsContentLen > 0) {
          File nvsFile = SD.open(OTA_NVS_PATH, FILE_WRITE);
          if (nvsFile) {
            WiFiClientSecure& rawSock2 = teleClient.wifi.rawClient();
            size_t nvsWritten = 0;
            size_t nvsExpected = (size_t)nvsContentLen;
            bool nvsOk = true;
            while (nvsWritten < nvsExpected) {
              uint32_t t1 = millis();
              while (!rawSock2.available() && millis() - t1 < PULL_OTA_CHUNK_TIMEOUT_MS) delay(1);
              if (!rawSock2.available()) { nvsOk = false; break; }
              int toRead = (int)(nvsExpected - nvsWritten);
              if (toRead > (int)PULL_OTA_CHUNK_SIZE) toRead = (int)PULL_OTA_CHUNK_SIZE;
              int nr = rawSock2.read(s_otaChunkBuf, toRead);
              if (nr <= 0) { nvsOk = false; break; }
              if ((size_t)nvsFile.write(s_otaChunkBuf, (size_t)nr) != (size_t)nr) { nvsOk = false; break; }
              nvsWritten += (size_t)nr;
            }
            nvsFile.close();
            if (nvsOk && nvsWritten == nvsExpected) {
              Serial.printf("[OTA-PULL] NVS staged: %u bytes\n", (unsigned)nvsWritten);
#if STORAGE != STORAGE_NONE
              if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL NVS DL OK");
#endif
            } else {
              Serial.println("[OTA-PULL] NVS download incomplete — skipping settings update");
              SD.remove(OTA_NVS_PATH);
            }
          }
        } else {
          Serial.printf("[OTA-PULL] NVS HTTP %d — skipping settings update\n", nvsHttpCode);
        }
        teleClient.wifi.close();
      } else {
        Serial.println("[OTA-PULL] NVS connect/send failed — skipping settings update");
        teleClient.wifi.close();
      }
#endif  // ENABLE_WIFI
    }  // nvsPath[0]

    s_ota_pending = true;
    Serial.printf("[OTA-PULL] Download complete: %u bytes in %u ms\n"
                  "[OTA-PULL] Firmware staged on SD (%s) — restarting to flash\n",
                  (unsigned)written, (unsigned)(millis() - dlStart), OTA_PENDING_PATH);
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) {
      char _ota_diag[64];
      snprintf(_ota_diag, sizeof(_ota_diag), "OTA-PULL DL OK SIZE=%u", (unsigned)fwSize);
      logger.logEvent(_ota_diag);
    }
#endif
    // Restart immediately so the device boots with a clean heap.  The boot-time
    // staging check (setup(), just after SD init) will detect /ota_fw.bin and
    // /ota_meta.txt and call performPullOtaFlash() before any TLS session is
    // opened, ensuring the flash and optional NVS update succeed reliably.
    // This also resolves the "Low heap" WiFi/LTE failure loop that would
    // otherwise block all network connections until the next natural standby.
    esp_restart();
    return false;  // unreachable: esp_restart() does not return
  }
#endif  // STORAGE == STORAGE_SD

  // ---- Fallback: stream directly to flash (STORAGE_NONE / STORAGE_SPIFFS) --
#if ENABLE_WIFI
  // Signal the telemetry task to pause WiFi I/O before Update.begin().
  s_ota_active = true;
  delay(1500);

  if (!teleClient.wifi.open(otaHost, otaPort)) {
    Serial.printf("[OTA-PULL] FW connect failed to %s:%u\n", _maskOtaHost(otaHost).c_str(), (unsigned)otaPort);
    s_ota_active = false;
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FW_CONNECT");
#endif
    return false;
  }

  if (!teleClient.wifi.send(METHOD_GET, fwPath)) {
    Serial.println("[OTA-PULL] FW send failed");
    teleClient.wifi.close();
    s_ota_active = false;
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FW_SEND");
#endif
    return false;
  }

  int contentLength = 0;
  int httpCode = teleClient.wifi.receiveHeaders(&contentLength);
  if (httpCode != 200) {
    Serial.printf("[OTA-PULL] FW HTTP %d\n", httpCode);
    teleClient.wifi.close();
    s_ota_active = false;
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) {
      char _ota_diag[48];
      snprintf(_ota_diag, sizeof(_ota_diag), "OTA-PULL ERR=FW_HTTP%d", httpCode);
      logger.logEvent(_ota_diag);
    }
#endif
    return false;
  }
  if (contentLength > 0 && (size_t)contentLength != fwSize) {
    Serial.printf("[OTA-PULL] FW size mismatch: meta=%u header=%d\n",
                  (unsigned)fwSize, contentLength);
    fwSize = (size_t)contentLength;
  }

  if (!Update.begin(fwSize)) {
    Serial.printf("[OTA-PULL] Update.begin failed: %s\n", Update.errorString());
    teleClient.wifi.close();
    s_ota_active = false;
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=UPD_BEGIN");
#endif
    return false;
  }

  WiFiClientSecure& rawSock = teleClient.wifi.rawClient();
  size_t written = 0;
  uint32_t dlStart = millis();
  size_t lastLogAt = 0;

  while (written < fwSize) {
    uint32_t chunkStart = millis();
    while (!rawSock.available() && millis() - chunkStart < PULL_OTA_CHUNK_TIMEOUT_MS) delay(1);
    if (!rawSock.available()) {
      Serial.printf("[OTA-PULL] Recv timeout at offset %u\n", (unsigned)written);
      Update.abort();
      teleClient.wifi.close();
      s_ota_active = false;
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=RECV_TIMEOUT");
#endif
      return false;
    }

    int toRead = (int)(fwSize - written);
    if (toRead > (int)PULL_OTA_CHUNK_SIZE) toRead = (int)PULL_OTA_CHUNK_SIZE;
    int n = rawSock.read(s_otaChunkBuf, toRead);
    if (n <= 0) {
      Serial.printf("[OTA-PULL] Read error at offset %u\n", (unsigned)written);
      Update.abort();
      teleClient.wifi.close();
      s_ota_active = false;
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=RECV_READ");
#endif
      return false;
    }

    size_t w = Update.write(s_otaChunkBuf, (size_t)n);
    if (w != (size_t)n) {
      Serial.printf("[OTA-PULL] Flash write error at offset %u\n", (unsigned)written);
      Update.abort();
      teleClient.wifi.close();
      s_ota_active = false;
#if STORAGE != STORAGE_NONE
      if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=FLASH_WRITE");
#endif
      return false;
    }
    written += (size_t)n;

    if (written - lastLogAt >= (fwSize / 10 ? fwSize / 10 : 1)) {
      lastLogAt = written;
      Serial.printf("[OTA-PULL] %u / %u bytes (%.0f%%) in %u ms\n",
                    (unsigned)written, (unsigned)fwSize,
                    100.0f * written / fwSize, (unsigned)(millis() - dlStart));
    }
  }

  teleClient.wifi.close();
  Serial.printf("[OTA-PULL] Download complete: %u bytes in %u ms\n",
                (unsigned)written, (unsigned)(millis() - dlStart));

  if (!Update.end()) {
    Serial.printf("[OTA-PULL] Update.end failed: %s\n", Update.errorString());
    s_ota_active = false;
#if STORAGE != STORAGE_NONE
    if (state.check(STATE_STORAGE_READY)) logger.logEvent("OTA-PULL ERR=UPD_END");
#endif
    return false;
  }

  Serial.println("[OTA-PULL] Flash successful, rebooting in 1.5 s");
#if STORAGE != STORAGE_NONE
  if (state.check(STATE_STORAGE_READY)) {
    char _ota_diag[64];
    snprintf(_ota_diag, sizeof(_ota_diag),
             "OTA-PULL OK FW=%s SIZE=%u", FIRMWARE_VERSION, (unsigned)written);
    logger.logEvent(_ota_diag);
  }
#endif
  // Notify HA that firmware was written to flash (best-effort, WiFi-only).
  // The HA server only updates "OTA letzte Übertragung" upon receiving this
  // request, so the attribute accurately reflects a device-confirmed flash.
  {
    char _confirmPath[128];
    snprintf(_confirmPath, sizeof(_confirmPath),
             "/api/freematics/ota_pull/%s/ota_confirm", otaToken);
    if (teleClient.wifi.open(otaHost, otaPort) &&
        teleClient.wifi.send(METHOD_GET, _confirmPath)) {
      int _confirmCL = 0;
      int _confirmCode = teleClient.wifi.receiveHeaders(&_confirmCL);
      Serial.printf("[OTA-PULL] Confirm %s (HTTP %d)\n",
                    _confirmCode == 200 ? "OK" : "FAILED", _confirmCode);
    } else {
      Serial.println("[OTA-PULL] Confirm request failed (non-fatal)");
    }
    teleClient.wifi.close();
  }
  // s_ota_active remains true; device reboots shortly.
  static esp_timer_handle_t s_pull_ota_timer = NULL;
  if (!s_pull_ota_timer) {
    esp_timer_create_args_t args = {};
    args.callback        = [](void*) { esp_restart(); };
    args.dispatch_method = ESP_TIMER_TASK;
    args.name            = "pull_ota_restart";
    esp_timer_create(&args, &s_pull_ota_timer);
  } else {
    esp_timer_stop(s_pull_ota_timer);
  }
  esp_timer_start_once(s_pull_ota_timer, 1500000);
  return true;
#endif  // ENABLE_WIFI
  return false;
}

void processBLE(int timeout)
{
#if ENABLE_BLE
  if (!enableBle) {
    if (timeout) delay(timeout);
    return;
  }
  static byte echo = 0;
  char* cmd;
  if (!(cmd = ble_recv_command(timeout))) {
    return;
  }

  char *p = strchr(cmd, '\r');
  if (p) *p = 0;
  char buf[48];
  int bufsize = sizeof(buf);
  int n = 0;
  if (echo) n += snprintf(buf + n, bufsize - n, "%s\r", cmd);
  Serial.print("[BLE] ");
  Serial.print(cmd);
  if (!strcmp(cmd, "UPTIME") || !strcmp(cmd, "TICK")) {
    n += snprintf(buf + n, bufsize - n, "%lu", millis());
  } else if (!strcmp(cmd, "BATT")) {
    n += snprintf(buf + n, bufsize - n, "%.2f", (float)(analogRead(A0) * 42) / 4095);
  } else if (!strcmp(cmd, "RESET")) {
#if STORAGE
    logger.end();
#endif
    ESP.restart();
    // never reach here
  } else if (!strcmp(cmd, "OFF")) {
    state.set(STATE_STANDBY);
    state.clear(STATE_WORKING);
    n += snprintf(buf + n, bufsize - n, "OK");
  } else if (!strcmp(cmd, "ON")) {
    state.clear(STATE_STANDBY);
    n += snprintf(buf + n, bufsize - n, "OK");
  } else if (!strcmp(cmd, "ON?")) {
    n += snprintf(buf + n, bufsize - n, "%u", state.check(STATE_STANDBY) ? 0 : 1);
  } else if (!strcmp(cmd, "APN?")) {
    n += snprintf(buf + n, bufsize - n, "%s", *apn ? apn : "DEFAULT");
  } else if (!strncmp(cmd, "APN=", 4)) {
    n += snprintf(buf + n, bufsize - n, nvs_set_str(nvs, "CELL_APN", strcmp(cmd + 4, "DEFAULT") ? cmd + 4 : "") == ESP_OK
        && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
    loadConfig();
  } else if (!strcmp(cmd, "PIN?")) {
    n += snprintf(buf + n, bufsize - n, "%s", *simPin ? "SET" : "NONE");
  } else if (!strncmp(cmd, "PIN=", 4)) {
    n += snprintf(buf + n, bufsize - n, nvs_set_str(nvs, "SIM_PIN", strcmp(cmd + 4, "CLEAR") ? cmd + 4 : "") == ESP_OK
        && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
    loadConfig();
  } else if (!strcmp(cmd, "NET_OP")) {
    if (state.check(STATE_WIFI_CONNECTED)) {
#if ENABLE_WIFI
      n += snprintf(buf + n, bufsize - n, "%s", wifiSSID[0] ? wifiSSID : "-");
#endif
    } else {
      snprintf(buf + n, bufsize - n, "%s", netop.length() ? netop.c_str() : "-");
      char *p = strchr(buf + n, ' ');
      if (p) *p = 0;
      n += strlen(buf + n);
    }
  } else if (!strcmp(cmd, "NET_IP")) {
    n += snprintf(buf + n, bufsize - n, "%s", ip.length() ? ip.c_str() : "-");
  } else if (!strcmp(cmd, "NET_PACKET")) {
      n += snprintf(buf + n, bufsize - n, "%u", teleClient.txCount);
  } else if (!strcmp(cmd, "NET_DATA")) {
      n += snprintf(buf + n, bufsize - n, "%u", teleClient.txBytes);
  } else if (!strcmp(cmd, "NET_RATE")) {
      n += snprintf(buf + n, bufsize - n, "%u", teleClient.startTime ? (unsigned int)((uint64_t)(teleClient.txBytes + teleClient.rxBytes) * 3600 / (millis() - teleClient.startTime)) : 0);
  } else if (!strcmp(cmd, "RSSI")) {
    n += snprintf(buf + n, bufsize - n, "%d", rssi);
#if ENABLE_WIFI
  } else if (!strcmp(cmd, "SSID?")) {
    n += snprintf(buf + n, bufsize - n, "%s", wifiSSID[0] ? wifiSSID : "-");
  } else if (!strncmp(cmd, "SSID=", 5)) {
    const char* p = cmd + 5;
    n += snprintf(buf + n, bufsize - n, nvs_set_str(nvs, "WIFI_SSID", strcmp(p, "-") ? p : "") == ESP_OK
        && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
    loadConfig();
  } else if (!strcmp(cmd, "WPWD?")) {
    n += snprintf(buf + n, bufsize - n, "%s", wifiPassword[0] ? wifiPassword : "-");
  } else if (!strncmp(cmd, "WPWD=", 5)) {
    const char* p = cmd + 5;
    n += snprintf(buf + n, bufsize - n, nvs_set_str(nvs, "WIFI_PWD", strcmp(p, "-") ? p : "") == ESP_OK
        && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
    loadConfig();
  } else if (!strncmp(cmd, "OTA_TOKEN=", 10)) {
    // Provision (or clear) the pull-OTA authentication token in NVS.
    // Use "-" or empty string to clear the token (disables OTA checks).
    // Also updates the runtime variable so the next OTA check fires without
    // a reboot (assuming OTA_INTERVAL is also set and otaHost is reachable).
    const char* p = cmd + 10;
    const bool clr = (p[0] == '\0' || (p[0] == '-' && p[1] == '\0'));
    esp_err_t e = nvs_set_str(nvs, "OTA_TOKEN", clr ? "" : p);
    if (e == ESP_OK) e = nvs_commit(nvs);
    if (e == ESP_OK) {
      size_t tlen = sizeof(otaToken);
      otaToken[0] = 0;
      nvs_get_str(nvs, "OTA_TOKEN", otaToken, &tlen);
      // Ensure otaHost is set so performPullOtaCheck() can open a connection.
      // If no dedicated OTA_HOST key is stored, fall back to serverHost.
      if (!otaHost[0] && otaToken[0]) {
        strncpy(otaHost, serverHost, sizeof(otaHost) - 1);
        otaHost[sizeof(otaHost) - 1] = 0;
      }
    }
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
  } else if (!strncmp(cmd, "OTA_HOST=", 9)) {
    // Set the hostname (or IP) of the HA server that serves the pull-OTA
    // endpoint.  Stored in NVS as OTA_HOST and applied at runtime.
    // Use "-" to clear (firmware then falls back to serverHost).
    const char* p = cmd + 9;
    const bool clr = (p[0] == '-' && p[1] == '\0');
    esp_err_t e = nvs_set_str(nvs, "OTA_HOST", clr ? "" : p);
    if (e == ESP_OK) e = nvs_commit(nvs);
    if (e == ESP_OK) {
      size_t hlen = sizeof(otaHost);
      otaHost[0] = 0;
      nvs_get_str(nvs, "OTA_HOST", otaHost, &hlen);
      // Same fallback as OTA_TOKEN handler: use serverHost when OTA_HOST is cleared.
      if (!otaHost[0] && otaToken[0]) {
        strncpy(otaHost, serverHost, sizeof(otaHost) - 1);
        otaHost[sizeof(otaHost) - 1] = 0;
      }
    }
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
  } else if (!strncmp(cmd, "OTA_INTERVAL=", 13)) {
    // Set the pull-OTA check interval in seconds (0 = disable).
    // Applied at runtime so the next check fires after this interval,
    // without requiring a reboot.
    uint16_t interval = (uint16_t)atoi(cmd + 13);
    esp_err_t e = nvs_set_u16(nvs, "OTA_INTERVAL", interval);
    if (e == ESP_OK) e = nvs_commit(nvs);
    if (e == ESP_OK) otaCheckIntervalS = interval;
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
#else
  } else if (!strcmp(cmd, "SSID?") || !strcmp(cmd, "WPWD?")) {
    n += snprintf(buf + n, bufsize - n, "-");
#endif
#if ENABLE_MEMS
  } else if (!strcmp(cmd, "TEMP")) {
    n += snprintf(buf + n, bufsize - n, "%d", (int)deviceTemp);
  } else if (!strcmp(cmd, "ACC")) {
    n += snprintf(buf + n, bufsize - n, "%.1f/%.1f/%.1f", acc[0], acc[1], acc[2]);
  } else if (!strcmp(cmd, "GYRO")) {
    n += snprintf(buf + n, bufsize - n, "%.1f/%.1f/%.1f", gyr[0], gyr[1], gyr[2]);
  } else if (!strcmp(cmd, "GF")) {
    n += snprintf(buf + n, bufsize - n, "%f", (float)sqrt(acc[0]*acc[0] + acc[1]*acc[1] + acc[2]*acc[2]));
#endif
  } else if (!strcmp(cmd, "ATE0")) {
    echo = 0;
    n += snprintf(buf + n, bufsize - n, "OK");
  } else if (!strcmp(cmd, "ATE1")) {
    echo = 1;
    n += snprintf(buf + n, bufsize - n, "OK");
  } else if (!strcmp(cmd, "FS")) {
    n += snprintf(buf + n, bufsize - n, "%u",
#if STORAGE == STORAGE_NONE
    0
#else
    logger.size()
#endif
      );
  } else if (!memcmp(cmd, "01", 2)) {
    byte pid = hex2uint8(cmd + 2);
    for (byte i = 0; i < sizeof(obdData) / sizeof(obdData[0]); i++) {
      if (obdData[i].pid == pid) {
        n += snprintf(buf + n, bufsize - n, "%d", obdData[i].value);
        pid = 0;
        break;
      }
    }
    if (pid) {
      int value;
      if (obd.readPID(pid, value)) {
        n += snprintf(buf + n, bufsize - n, "%d", value);
      } else {
        n += snprintf(buf + n, bufsize - n, "N/A");
      }
    }
  } else if (!strcmp(cmd, "VIN")) {
    n += snprintf(buf + n, bufsize - n, "%s", vin[0] ? vin : "N/A");
  } else if (!strcmp(cmd, "LAT") && gd) {
    n += snprintf(buf + n, bufsize - n, "%f", gd->lat);
  } else if (!strcmp(cmd, "LNG") && gd) {
    n += snprintf(buf + n, bufsize - n, "%f", gd->lng);
  } else if (!strcmp(cmd, "ALT") && gd) {
    n += snprintf(buf + n, bufsize - n, "%d", (int)gd->alt);
  } else if (!strcmp(cmd, "SAT") && gd) {
    n += snprintf(buf + n, bufsize - n, "%u", (unsigned int)gd->sat);
  } else if (!strcmp(cmd, "SPD") && gd) {
    n += snprintf(buf + n, bufsize - n, "%d", (int)(gd->speed * 1852 / 1000));
  } else if (!strcmp(cmd, "CRS") && gd) {
    n += snprintf(buf + n, bufsize - n, "%u", (unsigned int)gd->heading);
  } else if (!strncmp(cmd, "LED_WHITE=", 10)) {
    // Enable (1) or disable (0) the white/network LED at runtime and in NVS.
    uint8_t v = (uint8_t)atoi(cmd + 10);
    enableLedWhite = (v != 0);
    esp_err_t e = nvs_set_u8(nvs, "LED_WHITE_EN", v);
    if (e == ESP_OK) e = nvs_commit(nvs);
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
  } else if (!strncmp(cmd, "LED_RED=", 8)) {
    // Enable (1) or disable (0) the red/power LED at runtime and in NVS.
    uint8_t v = (uint8_t)atoi(cmd + 8);
    enableLedRed = (v != 0);
    esp_err_t e = nvs_set_u8(nvs, "LED_RED_EN", v);
    if (e == ESP_OK) e = nvs_commit(nvs);
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
  } else if (!strncmp(cmd, "BEEP=", 5)) {
    // Enable (1) or disable (0) the connection beep at runtime and in NVS.
    uint8_t v = (uint8_t)atoi(cmd + 5);
    enableBeep = (v != 0);
    esp_err_t e = nvs_set_u8(nvs, "BEEP_EN", v);
    if (e == ESP_OK) e = nvs_commit(nvs);
    n += snprintf(buf + n, bufsize - n, e == ESP_OK ? "OK" : "ERR");
  } else {
    n += snprintf(buf + n, bufsize - n, "ERROR");
  }
  Serial.print(" -> ");
  Serial.println((p = strchr(buf, '\r')) ? p + 1 : buf);
  if (n < bufsize - 1) {
    buf[n++] = '\r';
  } else {
    n = bufsize - 1;
  }
  buf[n] = 0;
  ble_send_response(buf, n, cmd);
#else
  if (timeout) delay(timeout);
#endif
}

// ---------------------------------------------------------------------------
// printOtaStatus()
//
// Prints the current pull-OTA configuration to the serial console.  Called
// at boot from setup() and after any live OTA config update via the HTTP
// control API (OTA_TOKEN=, OTA_HOST=, OTA_INTERVAL= commands) so users see
// the current OTA state immediately without needing to reboot.
//
// Outputs one of:
//   OTA:disabled                                    – OTA_TOKEN not in NVS
//   OTA:TOKEN=38f90170... HOST=… PORT=… INTERVAL=Xs – fully active
//   OTA:TOKEN=38f90170... HOST=… PORT=… INTERVAL=0s (checks disabled)
//                                                   – token set, INTERVAL=0
// The first 8 hex characters of the token are shown so it is recognisable
// in the serial log without exposing the full 64-character secret.
// ---------------------------------------------------------------------------
void printOtaStatus()
{
  if (otaToken[0]) {
    // Show only the first 8 hex chars of the token so the log entry is
    // unambiguous (no angle-bracket confusion) while keeping the secret safe.
    char _tok8[9];
    strncpy(_tok8, otaToken, 8);
    _tok8[8] = '\0';
    Serial.printf("OTA:TOKEN=%s... HOST=%s PORT=%u INTERVAL=%us%s\n",
                  _tok8,
                  otaHost[0] ? _maskOtaHost(otaHost).c_str() : "(server fallback)",
                  (unsigned)otaPort,
                  (unsigned)otaCheckIntervalS,
                  otaCheckIntervalS == 0 ? " (checks disabled)" : "");
  } else {
    Serial.println("OTA:disabled");
  }
}

void setup()
{
  // Drive the LED pin LOW immediately so that the GPIO output register
  // retained from a previous run (HIGH when the device was in standby)
  // does not keep the red LED on for several hundred milliseconds while
  // NVS is being initialised and loadConfig() is called.  The correct
  // on/off state based on the NVS LED_RED_EN setting is applied further
  // below, after loadConfig() has run.
#ifdef PIN_LED
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
#endif

  delay(500);

  // Initialize NVS.  Only erase and reinitialize for the two errors that ESP-IDF
  // documents as requiring a full partition erase: no free pages (partition is
  // full) and new-version-found (written by a newer NVS implementation).
  // For all other errors the partition may still be partially readable; erasing
  // it would destroy provisioned WiFi/server credentials unnecessarily and
  // prevent WiFi from connecting on subsequent boots.
  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    if (nvs_flash_erase() == ESP_OK) {
      err = nvs_flash_init();
    }
  }
  if (err == ESP_OK && nvs_open("storage", NVS_READWRITE, &nvs) == ESP_OK) {
    loadConfig();
  }

#if ENABLE_OLED
  oled.begin();
  oled.setFontSize(FONT_SIZE_SMALL);
#endif
  // initialize USB serial
  Serial.begin(115200);

  // Set the LED to the state determined by the NVS LED_RED_EN setting loaded
  // above.  When LED_RED_EN=1 (default) the LED is driven HIGH as a visual
  // power-on / initialising indicator; when LED_RED_EN=0 it stays LOW.
#ifdef PIN_LED
  digitalWrite(PIN_LED, enableLedRed ? HIGH : LOW);
#endif

  // generate unique device ID
  genDeviceID(devid);

#if CONFIG_MODE_TIMEOUT
  configMode();
#endif

#if LOG_EXT_SENSORS == 1
  pinMode(PIN_SENSOR1, INPUT);
  pinMode(PIN_SENSOR2, INPUT);
#elif LOG_EXT_SENSORS == 2
  adc1_config_width(ADC_WIDTH_BIT_12);
  adc1_config_channel_atten(ADC1_CHANNEL_0, ADC_ATTEN_DB_11);
  adc1_config_channel_atten(ADC1_CHANNEL_1, ADC_ATTEN_DB_11);
#endif

  // show system information
  showSysInfo();

  bufman.init();
  
  //Serial.print(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) >> 10);
  //Serial.println("KB");

#if ENABLE_OBD
  if (sys.begin()) {
    Serial.print("TYPE:");
    Serial.println(sys.devType);
    obd.begin(sys.link);
  }
#else
  sys.begin(false, true);
#endif

#if ENABLE_MEMS
if (!state.check(STATE_MEMS_READY)) do {
  Serial.print("MEMS:");
  mems = new ICM_42627;
  byte ret = mems->begin();
  if (ret) {
    state.set(STATE_MEMS_READY);
    Serial.println("ICM-42627");
    break;
  }
  delete mems;
  mems = new ICM_20948_I2C;
  ret = mems->begin();
  if (ret) {
    state.set(STATE_MEMS_READY);
    Serial.println("ICM-20948");
    break;
  } 
  delete mems;
  /*
  mems = new MPU9250;
  ret = mems->begin();
  if (ret) {
    state.set(STATE_MEMS_READY);
    Serial.println("MPU-9250");
    break;
  }
  */
  mems = 0;
  Serial.println("NO");
} while (0);
#endif

#if ENABLE_HTTPD
  if (enableHttpd) {
    IPAddress ip;
    if (serverSetup(ip)) {
      Serial.print("HTTPD:");
      Serial.println(ip);
#if ENABLE_OLED
      oled.println(ip);
#endif
    } else {
      Serial.println("HTTPD:NO");
    }
  }
#endif

  state.set(STATE_WORKING);

#if ENABLE_BLE
  if (enableBle) {
    // init BLE
    ble_init("FreematicsPlus");
  }
#endif

  // Print pull-OTA configuration so users can verify NVS provisioning via the
  // serial console.  This makes silent failures immediately obvious:
  // "OTA:disabled"        → OTA_TOKEN not in NVS (re-flash with HA serial-flash button).
  // "INTERVAL=0 (checks disabled)" → token set but OTA_INTERVAL not provisioned;
  //                           re-flash or use Send Config to set OTA_INTERVAL > 0.
  printOtaStatus();

  // initialize components
  initialize();

  // initialize network and maintain connection.
  // Stack of 16 KB gives mbedTLS / WiFiClientSecure enough room for the TLS
  // handshake (typically 4–6 KB of stack) on top of the task's own frames.
  subtask.create(telemetry, "telemetry", 2, 16384);

#ifdef PIN_LED
  digitalWrite(PIN_LED, LOW);
#endif
}

void loop()
{
  // error handling
  if (!state.check(STATE_WORKING)) {
    standby();
#ifdef PIN_LED
    if (enableLedRed) digitalWrite(PIN_LED, HIGH);
#endif
    initialize();
#ifdef PIN_LED
    digitalWrite(PIN_LED, LOW);
#endif
    return;
  }

  // collect and log data
  process();
}
