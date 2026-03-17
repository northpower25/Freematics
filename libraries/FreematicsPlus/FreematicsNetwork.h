/*************************************************************************
* Telematics Data Logger Class
* Distributed under BSD license
* Developed by Stanley Huang https://www.facebook.com/stanleyhuangyc
*************************************************************************/

#ifndef FREEMATICS_NETWORK
#define FREEMATICS_NETWORK

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiClientSecure.h>

#include "esp_system.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include "FreematicsBase.h"

#define XBEE_BAUDRATE 115200
#define HTTP_CONN_TIMEOUT 5000
// TLS handshake over cellular can take longer than a data exchange; allow
// up to 15 seconds before declaring the connection attempt failed.
#define HTTP_TLS_HANDSHAKE_TIMEOUT 15000
// Minimum expected duration (ms) for a TLS 1.2 handshake over a cellular
// link (TCP 3-way + TLS exchange with a remote server).  +CCHOPEN:0,0
// arriving faster than this is suspicious and may indicate a plain TCP
// connection that silently bypassed the SSL layer.  Used as a hard-reject
// threshold in open(): any +CCHOPEN response arriving in less than this many
// milliseconds causes the session to be closed and open() to return false.
// Some SIM7600E-H firmware revisions silently fall back to plain TCP even
// with the explicit 5-param ssl_ctx_id form; accepting such sessions leads to
// repeated "400 The plain HTTP request was sent to HTTPS port" responses.
//
// 150 ms is chosen to be safely above the plain-TCP fast-path (typically
// <100 ms: modem acknowledges AT+CCHOPEN + TCP connect without TLS overhead)
// while accepting legitimate TLS handshakes to cloud endpoints such as
// hooks.nabu.casa (AWS ALB, EU) which complete in ~150–400 ms over cellular.
// The previous 300 ms threshold was too aggressive: it falsely rejected real
// TLS connections to hooks.nabu.casa when combined with Connection: close
// (which forces a new TLS handshake for every packet), breaking all cellular
// telemetry delivery.
#define MIN_TLS_HANDSHAKE_MS 150

// Runtime cellular debug flag.  Set to 1 via NVS key CELL_DEBUG (written by
// the HA config/options flow) to enable verbose cellular diagnostic logging:
// TX-Preview, hex-dump, AT+CCHSTATUS? and per-packet "Incoming data" lines.
// Controlled at runtime so no firmware recompile is needed.  Default is 0.
extern uint8_t cellNetDebug;

#define RECV_BUF_SIZE 512

// Minimum total free DRAM required before attempting a new TLS handshake.
// A TLS session (mbedTLS context, handshake buffers, etc.) uses roughly
// 20–50 KB spread across many small allocations.  When the heap is already
// fragmented by prior TLS teardown/creation cycles, individual allocations
// inside mbedtls_ssl_setup() etc. fail with MBEDTLS_ERR_SSL_ALLOC_FAILED
// (-32512), breaking ALL subsequent HTTPS connections until the WiFi stack
// is restarted.  This threshold gives a conservative safety margin so that
// WifiHTTP::open() declines the connect attempt early (without tearing down
// the existing session) and the caller can request a WiFi restart instead.
// mbedTLS allocates two ~16.5 KB TLS record buffers (IN and OUT) sequentially
// inside mbedtls_ssl_setup(); both must fit in a single contiguous DRAM block
// because they are allocated back-to-back from the same heap region.
// Values below ~34 KB will consistently fail.
// 36 KB is chosen as the guard threshold: it sits 2 KB above the ~34 KB
// minimum, giving a small safety margin while still being comfortably below
// the ~37–40 KB max block that is typically available after the OTA meta-check
// TLS session is released via wifi.close() early in performPullOtaCheck().
// The previous 38 KB threshold was too close to the post-close max block:
// if the meta-check TLS teardown left just 37 KB (e.g. a small WiFi-driver
// allocation happened to sit at the boundary of the freed region), Guard 2
// fired immediately and telemetry could not re-establish its TLS session.
// ESP.getMaxAllocHeap() returns the largest single contiguous free block,
// which is the correct metric for fragmentation detection (total free heap
// can be high while no individual block is large enough for TLS).
#define TLS_MIN_FREE_HEAP (36 * 1024)

typedef enum {
  METHOD_GET = 0,
  METHOD_POST,
} HTTP_METHOD;

typedef enum {
    HTTP_DISCONNECTED = 0,
    HTTP_CONNECTED,
    HTTP_SENT,
    HTTP_ERROR,
} HTTP_STATES;

typedef struct {
    float lat;
    float lng;
    uint8_t year; /* year past 2000, e.g. 15 for 2015 */
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
} NET_LOCATION;

class HTTPClient
{
public:
    HTTP_STATES state() { return m_state; }
    uint16_t code() { return m_code; }
protected:
    String genHeader(HTTP_METHOD method, const char* path, const char* payload, int payloadSize);
    // Generate an HTTP request header with an optional Authorization: Bearer header.
    // When bearerToken is non-null and non-empty it is appended before the
    // terminal CRLF-CRLF so the server can authenticate the request.
    String genHeaderWithAuth(HTTP_METHOD method, const char* path,
                             const char* payload, int payloadSize,
                             const char* bearerToken);
    HTTP_STATES m_state = HTTP_DISCONNECTED;
    uint16_t m_code = 0;
    String m_host;
};

class ClientWIFI
{
public:
    bool begin(const char* ssid, const char* password);
    void end();
    bool setup(unsigned int timeout = 5000);
    String getIP();
    int getSignal() { return 0; }
    const char* deviceName() { return "WiFi"; }
    void listAPs();
    bool connected() { return WiFi.isConnected(); }
    int RSSI() { return WiFi.RSSI(); }
protected:
};

class WifiUDP : public ClientWIFI
{
public:
    bool open(const char* host, uint16_t port);
    void close();
    bool send(const char* data, unsigned int len);
    int receive(char* buffer, int bufsize, unsigned int timeout = 100);
    String queryIP(const char* host);
private:
    IPAddress udpIP;
    uint16_t udpPort;
    WiFiUDP udp;
};

class WifiHTTP : public HTTPClient, public ClientWIFI
{
public:
    bool open(const char* host = 0, uint16_t port = 0);
    void close();
    bool send(HTTP_METHOD method, const char* path, const char* payload = 0, int payloadSize = 0);
    char* receive(char* buffer, int bufsize, int* pbytes = 0, unsigned int timeout = HTTP_CONN_TIMEOUT);
    // Expose the underlying TLS socket so callers can stream a large response
    // body (e.g. a firmware binary) in chunks without buffering it all at once.
    // Used by performPullOtaCheck() in telelogger.ino.
    WiFiClientSecure& rawClient() { return client; }
    // Parse the HTTP response headers that are already in the socket, return the
    // HTTP status code and (via *contentLength) the Content-Length value.
    // Leaves the socket positioned at the first byte of the body.
    // Returns -1 on timeout or parse failure.
    int receiveHeaders(int* contentLength, unsigned int timeout = HTTP_CONN_TIMEOUT);
private:
    WiFiClientSecure client;
};

typedef enum {
    CELL_SIM7600 = 0,
    CELL_SIM7670 = 1,
    CELL_SIM7070 = 2,
    CELL_SIM5360 = 3
} CELL_TYPE;

class CellSIMCOM
{
public:
    virtual bool begin(CFreematics* device);
    virtual void end();
    virtual bool setup(const char* apn, const char* username = 0, const char* password = 0, unsigned int timeout = 60000);
    virtual bool setGPS(bool on);
    virtual String getIP();
    int RSSI();
    String getOperatorName();
    bool checkSIM(const char* pin = 0);
    virtual String queryIP(const char* host);
    virtual bool getLocation(GPS_DATA** pgd);
    bool check(unsigned int timeout = 0);
    char* getBuffer();
    const char* deviceName() { return m_model; }
    char IMEI[16] = {0};
protected:
    bool sendCommand(const char* cmd, unsigned int timeout = 1000, const char* expected = 0);
    virtual void inbound();
    virtual void checkGPS();
    float parseDegree(const char* s);
    char* m_buffer = 0;
    char m_model[12] = {0};
    CFreematics* m_device = 0;
    GPS_DATA* m_gps = 0;
    CELL_TYPE m_type = CELL_SIM7600;
    int m_incoming = 0;
};

class CellUDP : public CellSIMCOM
{
public:
    bool open(const char* host, uint16_t port);
    bool close();
    bool send(const char* data, unsigned int len);
    char* receive(int* pbytes = 0, unsigned int timeout = 5000);
protected:
    String udpIP;
    uint16_t udpPort = 0;
};

class CellHTTP : public HTTPClient, public CellSIMCOM
{
public:
    void init();
    bool open(const char* host = 0, uint16_t port = 0);
    bool close();
    bool send(HTTP_METHOD method, const char* host, uint16_t port, const char* path, const char* payload = 0, int payloadSize = 0);
    char* receive(int* pbytes = 0, unsigned int timeout = HTTP_CONN_TIMEOUT);
    // Streaming receive for large responses (SIM7600 only).
    // receiveHeaders() reads the first data chunk from the modem socket, parses
    // the HTTP status code and Content-Length header, and buffers any body bytes
    // already present in that chunk so they are returned by the first
    // receiveBodyBytes() call without an additional AT command round-trip.
    // Returns the HTTP status code (e.g. 200), or -1 on failure / unsupported modem.
    int receiveHeaders(int* contentLength = 0, unsigned int timeout = HTTP_CONN_TIMEOUT);
    // Read the next chunk of the response body after receiveHeaders().
    // Returns the number of bytes written to buf (> 0), 0 at end-of-stream,
    // or -1 on error / unsupported modem type.
    int receiveBodyBytes(char* buf, int maxLen, unsigned int timeout = HTTP_CONN_TIMEOUT);
protected:
    // Override to detect +CHTTPSCLSE: URCs that arrive during any AT command
    // and mark the session disconnected before send() tries to use it.
    void inbound() override;
private:
    // Body bytes buffered during receiveHeaders() that have not yet been
    // returned by receiveBodyBytes().  m_buffer[0..m_streamBodyLen-1] holds
    // the initial body slice; m_streamBodyPos is the next unread offset.
    // Both are reset to 0 at the start of each receiveHeaders() call.
    int m_streamBodyLen = 0;
    int m_streamBodyPos = 0;
};

#endif
