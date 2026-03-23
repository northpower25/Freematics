/*************************************************************************
* Base class for Freematics telematics products
* Distributed under BSD license
* Visit https://freematics.com for more information
* (C)2017-2018 Stanley Huang <stanley@freematics.com.au
*************************************************************************/

#ifndef FREEMATICS_BASE
#define FREEMATICS_BASE

#include <Arduino.h>

// non-OBD/custom PIDs (no mode number)
#define PID_GPS_LATITUDE 0xA
#define PID_GPS_LONGITUDE 0xB
#define PID_GPS_ALTITUDE 0xC
#define PID_GPS_SPEED 0xD
#define PID_GPS_HEADING 0xE
#define PID_GPS_SAT_COUNT 0xF
#define PID_GPS_TIME 0x10
#define PID_GPS_DATE 0x11
#define PID_GPS_HDOP 0x12
#define PID_ACC 0x20
#define PID_GYRO 0x21
#define PID_COMPASS 0x22
#define PID_BATTERY_VOLTAGE 0x24
#define PID_ORIENTATION 0x25

// custom PIDs
#define PID_TIMESTAMP 0
#define PID_TRIP_DISTANCE 0x30
#define PID_DATA_SIZE 0x80
#define PID_CSQ 0x81
#define PID_DEVICE_TEMP 0x82
#define PID_DEVICE_HALL 0x83
// Runtime NVS settings reported back in telemetry so HA can track live state.
// 0 = disabled/off, 1 = enabled/on.
#define PID_LED_WHITE_STATE 0x84  // enableLedWhite: white/network LED runtime state
#define PID_BEEP_STATE      0x85  // enableBeep: connection-beep runtime state
// SD card status PIDs: sent periodically in telemetry so HA can display SD
// presence and usage even when the device is not directly reachable via HTTP.
// Values are in MiB (1 MiB = 2^20 bytes).  sd_total_mb == 0 means no SD card.
#define PID_SD_TOTAL_MB     0x86  // total SD capacity in MiB (0 = no card / not ready)
#define PID_SD_FREE_MB      0x87  // free SD space in MiB
// Active transport indicator: sent on change (and after every reconnect) so
// Home Assistant can distinguish WiFi from cellular packets and correctly
// update the "WiFi letzte Verbindung" / "LTE letzte Verbindung" timestamps.
// Value: 1 = WiFi (STATE_WIFI_CONNECTED), 2 = Cellular (SIM7600/LTE).
#define PID_CONN_TYPE       0x88  // active transport: 1=WiFi, 2=Cellular
// Runtime OBD / CAN enable state, standby-time override, and deep-standby mode,
// reported once per session so Home Assistant can show Konfig vs IST-Status.
#define PID_OBD_STATE       0x89  // enableObd: 1=OBD querying active, 0=disabled
#define PID_CAN_STATE       0x8a  // enableCan: 1=CAN bus active, 0=disabled
#define PID_STANDBY_TIME    0x8b  // nvsStandbyTimeS: standby timeout in seconds (u16; 0=firmware default 180 s)
#define PID_DEEP_STANDBY    0x8c  // enableDeepStandby: 1=deep sleep on standby, 0=normal standby
#define PID_EXT_SENSOR1 0x90
#define PID_EXT_SENSOR2 0x91

typedef struct {
	float pitch;
	float yaw;
	float roll;
} ORIENTATION;

typedef struct {
	uint32_t ts;
	uint32_t date;
	uint32_t time;
	float lat;
	float lng;
	float alt; /* meter */
	float speed; /* knot */
	uint16_t heading; /* degree */
	uint8_t hdop;
	uint8_t sat;
	uint16_t sentences;
	uint16_t errors;
} GPS_DATA;

class CLink
{
public:
	virtual ~CLink() {}
	virtual bool begin(unsigned int baudrate = 0, int rxPin = 0, int txPin = 0) { return true; }
	virtual void end() {}
	// send command and receive response
	virtual int sendCommand(const char* cmd, char* buf, int bufsize, unsigned int timeout) { return 0; }
	// receive data from SPI
	virtual int receive(char* buffer, int bufsize, unsigned int timeout) { return 0; }
	// write data to SPI
	virtual bool send(const char* str) { return false; }
	virtual int read() { return -1; }
};

class CFreematics
{
public:
	virtual void begin() {}
	// start xBee UART communication
	virtual bool xbBegin(unsigned long baudrate = 115200L, int pinRx = 0, int pinTx = 0) = 0;
	virtual void xbEnd() {}
	// read data to xBee UART
	virtual int xbRead(char* buffer, int bufsize, unsigned int timeout = 1000) = 0;
	// send data to xBee UART
	virtual void xbWrite(const char* cmd) = 0;
  // send data to xBee UART
	virtual void xbWrite(const char* data, int len) = 0;
	// receive data from xBee UART (returns 0/1/2)
	virtual int xbReceive(char* buffer, int bufsize, unsigned int timeout = 1000, const char** expected = 0, byte expectedCount = 0) = 0;
	// purge xBee UART buffer
	virtual void xbPurge() = 0;
	// toggle xBee module power
	virtual void xbTogglePower(unsigned int duration = 500) = 0;
};

#endif
