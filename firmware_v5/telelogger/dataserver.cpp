/*************************************************************************
* Vehicle Telemetry Data Logger for Freematics ONE+
*
* Developed by Stanley Huang <stanley@freematics.com.au>
* Distributed under BSD license
* Visit https://freematics.com/products/freematics-one-plus for more info
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
* THE SOFTWARE.
*
* Implemented HTTP APIs:
* /api/info - device info
* /api/live - live data (OBD/GPS/MEMS)
* /api/control - issue a control command
* /api/list - list of log files
* /api/log/<file #> - raw CSV format log file
* /api/delete/<file #> - delete file
* /api/data/<file #>?pid=<PID in hex> - JSON array of PID data
* /api/ota - OTA firmware update (raw binary POST, Content-Type: application/octet-stream)
*************************************************************************/

#include <SPI.h>
#include <FS.h>
#include <SD.h>
#include <SPIFFS.h>
#include <FreematicsPlus.h>
#include <WiFi.h>
#include <SPIFFS.h>
#include <apps/sntp/sntp.h>
#include <esp_spi_flash.h>
#include <esp_err.h>
#include <esp_timer.h>
#include <Update.h>
#include <httpd.h>
#include "config.h"

#if ENABLE_HTTPD

#define WIFI_TIMEOUT 5000

extern uint32_t fileid;
#if ENABLE_WIFI
extern char wifiSSID[];
extern char wifiPassword[];
#endif

extern "C"
{
uint8_t temprature_sens_read();
uint32_t hall_sens_read();
}

HttpParam httpParam;

int handlerLiveData(UrlHandlerParam* param);

extern nvs_handle_t nvs;
extern void loadConfig();

uint16_t hex2uint16(const char *p);

int handlerInfo(UrlHandlerParam* param)
{
    char *buf = param->pucBuffer;
    int bufsize = param->bufSize;
    int bytes = snprintf(buf, bufsize, "{\"httpd\":{\"uptime\":%u,\"clients\":%u,\"requests\":%u,\"traffic\":%u},\n",
        (unsigned int)millis(), httpParam.stats.clientCount, (unsigned int)httpParam.stats.reqCount, (unsigned int)(httpParam.stats.totalSentBytes >> 10));

    time_t now;
    time(&now);
    struct tm timeinfo = { 0 };
    localtime_r(&now, &timeinfo);
    if (timeinfo.tm_year) {
        bytes += snprintf(buf + bytes, bufsize - bytes, "\"rtc\":{\"date\":\"%04u-%02u-%02u\",\"time\":\"%02u:%02u:%02u\"},\n",
        timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
        timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    }

    int deviceTemp = (int)temprature_sens_read() * 165 / 255 - 40;
    bytes += snprintf(buf + bytes, bufsize - bytes, "\"cpu\":{\"temperature\":%d,\"magnetic\":%d},\n",
        deviceTemp, hall_sens_read());

#if STORAGE == STORAGE_SPIFFS
    bytes += snprintf(buf + bytes, bufsize - bytes, "\"spiffs\":{\"total\":%u,\"used\":%u}",
        SPIFFS.totalBytes(), SPIFFS.usedBytes());
#else
    bytes += snprintf(buf + bytes, bufsize - bytes, "\"sd\":{\"total\":%llu,\"used\":%llu}",
        SD.totalBytes(), SD.usedBytes());
#endif

    if (bytes < bufsize - 1) buf[bytes++] = '}';

    param->contentLength = bytes;
    param->contentType=HTTPFILETYPE_JSON;
    return FLAG_DATA_RAW;
}

class LogDataContext {
public:
    File file;
    uint32_t tsStart;
    uint32_t tsEnd;
    uint16_t pid;
};

int handlerLogFile(UrlHandlerParam* param)
{
    LogDataContext* ctx = (LogDataContext*)param->hs->ptr;
    param->contentType = HTTPFILETYPE_TEXT;
    if (ctx) {
		if (!param->pucBuffer) {
			// connection to be closed, final calling, cleanup
			ctx->file.close();
            delete ctx;
			param->hs->ptr = 0;
			return 0;
		}
    } else {
        int id = 0;
        if (param->pucRequest[0] == '/') {
            id = atoi(param->pucRequest + 1);
        }
        sprintf(param->pucBuffer, "/DATA/%u.CSV", id == 0 ? fileid : id);
        ctx = new LogDataContext;
#if STORAGE == STORAGE_SPIFFS
        ctx->file = SPIFFS.open(param->pucBuffer, FILE_READ);
#else
        ctx->file = SD.open(param->pucBuffer, FILE_READ);
#endif
        if (!ctx->file) {
            strcat(param->pucBuffer, " not found");
            param->contentLength = strlen(param->pucBuffer);
            delete ctx;
            return FLAG_DATA_RAW;
        }
        param->hs->ptr = (void*)ctx;
    }

    if (!ctx->file.available()) {
        // EOF
        return 0;
    }
    param->contentLength = ctx->file.readBytes(param->pucBuffer, param->bufSize);
    param->contentType = HTTPFILETYPE_TEXT;
    return FLAG_DATA_STREAM;
}

int handlerLogData(UrlHandlerParam* param)
{
    uint32_t duration = 0;
    LogDataContext* ctx = (LogDataContext*)param->hs->ptr;
    param->contentType = HTTPFILETYPE_JSON;
    if (ctx) {
		if (!param->pucBuffer) {
			// connection to be closed, final calling, cleanup
			ctx->file.close();
            delete ctx;
			param->hs->ptr = 0;
			return 0;
		}
    } else {
        int id = 0;
        if (param->pucRequest[0] == '/') {
            id = atoi(param->pucRequest + 1);
        }
        sprintf(param->pucBuffer, "/DATA/%u.CSV", id == 0 ? fileid : id);
        ctx = new LogDataContext;
#if STORAGE == STORAGE_SPIFFS
        ctx->file = SPIFFS.open(param->pucBuffer, FILE_READ);
#else
        ctx->file = SD.open(param->pucBuffer, FILE_READ);
#endif
        if (!ctx->file) {
            param->contentLength = sprintf(param->pucBuffer, "{\"error\":\"Data file not found\"}");
            delete ctx;
            return FLAG_DATA_RAW;
        }
        ctx->pid = mwGetVarValueHex(param->pxVars, "pid", 0);
        ctx->tsStart = mwGetVarValueInt(param->pxVars, "start", 0);
        ctx->tsEnd = 0xffffffff;
        duration = mwGetVarValueInt(param->pxVars, "duration", 0);
        if (ctx->tsStart && duration) {
            ctx->tsEnd = ctx->tsStart + duration;
            duration = 0;
        }
        param->hs->ptr = (void*)ctx;
        // JSON head
        param->contentLength = sprintf(param->pucBuffer, "[");
    }
    
    int len = 0;
    char buf[64];
    uint32_t ts = 0;

    for (;;) {
        int c = ctx->file.read();
        if (c == -1) {
            if (param->contentLength == 0) {
                // EOF
                return 0;
            }
            // JSON tail
            if (param->pucBuffer[param->contentLength - 1] == ',') param->contentLength--;
            param->pucBuffer[param->contentLength++] = ']';
            break;
        }
        if (c == '\n') {
            // line end, process the line
            buf[len] = 0;
            char *value = strchr(buf, ',');
            if (value++) {
                uint16_t pid = hex2uint16(buf);
                if (pid == 0) {
                    // timestamp
                    ts = atoi(value);
                    if (duration) {
                        ctx->tsEnd = ts + duration;
                        duration = 0;
                    }
                } else if (pid == ctx->pid && ts >= ctx->tsStart && ts < ctx->tsEnd) {
                    // generate json array element
                    param->contentLength += snprintf(param->pucBuffer + param->contentLength, param->bufSize - param->contentLength,
                        "[%u,%s],", ts, value);
                }
            }
            len = 0;
            if (param->contentLength + 32 > param->bufSize) break;
        } else if (len < sizeof(buf) - 1) {
            buf[len++] = c;
        }
    }
    return FLAG_DATA_STREAM;
}

int handlerLogList(UrlHandlerParam* param)
{
    char *buf = param->pucBuffer;
    int bufsize = param->bufSize;
    File file;
#if STORAGE == STORAGE_SPIFFS
    File root = SPIFFS.open("/");
#elif STORAGE == STORAGE_SD
    File root = SD.open("/DATA");
#endif
    int n = snprintf(buf, bufsize, "[");
    if (root) {
        while(file = root.openNextFile()) {
            const char *fn = file.name();
            // Handle both full-path ("/DATA/83.CSV") and basename-only ("83.CSV")
            // returned by different versions of the Arduino ESP32 SD library.
            const char *p = strrchr(fn, '/');
            if (p) fn = p + 1;
            unsigned int size = file.size();
            unsigned int id = atoi(fn);
            if (id) {
                Serial.print(fn);
                Serial.print(' ');
                Serial.print(size);
                Serial.println(" bytes");
                n += snprintf(buf + n, bufsize - n, "{\"id\":%u,\"size\":%u",
                    id, size);
                if (id == fileid) {
                    n += snprintf(buf + n, bufsize - n, ",\"active\":true");
                }
                n += snprintf(buf + n, bufsize - n, "},");
            }
        }
        if (n > 0 && buf[n - 1] == ',') n--;
    }
    n += snprintf(buf + n, bufsize - n, "]");
    param->contentType=HTTPFILETYPE_JSON;
    param->contentLength = n;
    return FLAG_DATA_RAW;
}

int handlerLogDelete(UrlHandlerParam* param)
{
    int id = 0;
    if (param->pucRequest[0] == '/') {
        id = atoi(param->pucRequest + 1);
    }
    sprintf(param->pucBuffer, "/DATA/%u.CSV", id);
    if (id == fileid) {
        strcat(param->pucBuffer, " still active");
    } else {
#if STORAGE == STORAGE_SPIFFS
        bool removal = SPIFFS.remove(param->pucBuffer);
#else
        bool removal = SD.remove(param->pucBuffer);
#endif
        if (removal) {
            strcat(param->pucBuffer, " deleted");
        } else {
            strcat(param->pucBuffer, " not found");
        }
    }
    param->contentLength = strlen(param->pucBuffer);
    param->contentType = HTTPFILETYPE_TEXT;
    return FLAG_DATA_RAW;
}

int handlerControl(UrlHandlerParam* param)
{
    char *buf = param->pucBuffer;
    int bufsize = param->bufSize;
    const char* cmd = mwGetVarValue(param->pxVars, "cmd", "");
    int n = 0;

    if (!*cmd) {
        n = snprintf(buf, bufsize, "ERR");
#if ENABLE_WIFI
    } else if (!strncmp(cmd, "SSID=", 5)) {
        const char* p = cmd + 5;
        n = snprintf(buf, bufsize, "%s",
            nvs_set_str(nvs, "WIFI_SSID", strcmp(p, "-") ? p : "") == ESP_OK
            && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
        loadConfig();
    } else if (!strncmp(cmd, "WPWD=", 5)) {
        const char* p = cmd + 5;
        n = snprintf(buf, bufsize, "%s",
            nvs_set_str(nvs, "WIFI_PWD", strcmp(p, "-") ? p : "") == ESP_OK
            && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
        loadConfig();
#endif
    } else if (!strncmp(cmd, "APN=", 4)) {
        n = snprintf(buf, bufsize, "%s",
            nvs_set_str(nvs, "CELL_APN", strcmp(cmd + 4, "DEFAULT") ? cmd + 4 : "") == ESP_OK
            && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
        loadConfig();
    } else if (!strncmp(cmd, "PIN=", 4)) {
        n = snprintf(buf, bufsize, "%s",
            nvs_set_str(nvs, "SIM_PIN", strcmp(cmd + 4, "CLEAR") ? cmd + 4 : "") == ESP_OK
            && nvs_commit(nvs) == ESP_OK ? "OK" : "ERR");
        loadConfig();
    } else if (!strcmp(cmd, "RESET")) {
        n = snprintf(buf, bufsize, "OK");
        param->contentLength = n;
        param->contentType = HTTPFILETYPE_TEXT;
        ESP.restart();
    } else {
        n = snprintf(buf, bufsize, "ERR");
    }

    param->contentLength = n;
    param->contentType = HTTPFILETYPE_TEXT;
    return FLAG_DATA_RAW;
}

// ---------------------------------------------------------------------------
// OTA firmware update handler
// Accepts a raw binary POST (Content-Type: application/octet-stream).
// The HTTP server buffers only the first MAX_POST_PAYLOAD_SIZE (4 KB) bytes
// before calling the handler; the rest of the firmware is streamed directly
// from the socket using recv() so that large binaries (>1 MB) work without
// exhausting the device heap.
// After a successful flash the device reboots via a one-shot esp_timer so the
// HTTP 200 response reaches the client before the reset.
// ---------------------------------------------------------------------------
static void ota_restart_cb(void*) {
    esp_restart();
}

int handlerOTA(UrlHandlerParam* param) {
    char* buf     = param->pucBuffer;
    int   bufsize = param->bufSize;

    // The httpd caps param->payloadSize at MAX_POST_PAYLOAD_SIZE (4 KB) before
    // calling this handler.  Read the true Content-Length from the raw HTTP
    // request headers so we know how many bytes to expect in total.
    // strcasestr handles all capitalisation variants per RFC 7230.
    const char* cl = strcasestr(param->hs->buffer, "Content-Length:");
    size_t fw_size = 0;
    if (cl) {
        cl += 15;
        while (*cl == ' ') cl++;
        fw_size = (size_t)atol(cl);
    }
    if (fw_size == 0) {
        param->contentLength = snprintf(buf, bufsize,
            "ERR: missing Content-Length");
        param->contentType = HTTPFILETYPE_TEXT;
        return FLAG_DATA_RAW;
    }

    Serial.printf("[OTA] Starting update: %u bytes\n", (unsigned)fw_size);

    if (!Update.begin(fw_size)) {
        param->contentLength = snprintf(buf, bufsize,
            "ERR: Update.begin failed: %s", Update.errorString());
        param->contentType = HTTPFILETYPE_TEXT;
        return FLAG_DATA_RAW;
    }

    // Write the first chunk that the httpd already buffered (up to 4 KB).
    size_t written = 0;
    if (param->pucPayload && param->payloadSize > 0) {
        size_t first_chunk = (param->payloadSize < fw_size)
                             ? (size_t)param->payloadSize : fw_size;
        size_t w = Update.write((uint8_t*)param->pucPayload, first_chunk);
        if (w != first_chunk) {
            Update.abort();
            param->contentLength = snprintf(buf, bufsize,
                "ERR: write error at offset 0 (%u/%u written)",
                (unsigned)w, (unsigned)first_chunk);
            param->contentType = HTTPFILETYPE_TEXT;
            return FLAG_DATA_RAW;
        }
        written = w;
    }

    // Stream the remaining bytes directly from the socket to flash.
    // The socket is set non-blocking by the httpd (O_NONBLOCK), so we must
    // use select() before each recv() to wait for data without spinning.
    // Use a larger buffer (4 KB instead of 512 B) for better throughput.
    uint8_t recv_buf[4096];
    int sock = param->hs->socket;
    while (written < fw_size) {
        size_t remaining = fw_size - written;
        int to_read = (int)(remaining < sizeof(recv_buf)
                            ? remaining : sizeof(recv_buf));
        // Wait up to 30 s for the next data chunk.  For a local-network WiFi
        // connection this should be reached in milliseconds; the generous
        // timeout guards against brief network pauses.
        fd_set rfds;
        struct timeval tv;
        FD_ZERO(&rfds);
        FD_SET(sock, &rfds);
        tv.tv_sec  = 30;
        tv.tv_usec = 0;
        if (select(sock + 1, &rfds, NULL, NULL, &tv) <= 0) {
            Update.abort();
            param->contentLength = snprintf(buf, bufsize,
                "ERR: recv timeout at offset %u (remaining %u)",
                (unsigned)written, (unsigned)remaining);
            param->contentType = HTTPFILETYPE_TEXT;
            return FLAG_DATA_RAW;
        }
        int n = recv(sock, recv_buf, to_read, 0);
        if (n <= 0) {
            Update.abort();
            param->contentLength = snprintf(buf, bufsize,
                "ERR: recv failed at offset %u (remaining %u)",
                (unsigned)written, (unsigned)remaining);
            param->contentType = HTTPFILETYPE_TEXT;
            return FLAG_DATA_RAW;
        }
        size_t w = Update.write(recv_buf, (size_t)n);
        if (w != (size_t)n) {
            Update.abort();
            param->contentLength = snprintf(buf, bufsize,
                "ERR: flash write error at offset %u", (unsigned)written);
            param->contentType = HTTPFILETYPE_TEXT;
            return FLAG_DATA_RAW;
        }
        written += (size_t)n;
    }

    // -----------------------------------------------------------------------
    // Phase 1 complete: all bytes received.  Verify the byte count before
    // triggering the actual flash commit.
    // -----------------------------------------------------------------------
    Serial.printf("[OTA] Upload complete: %u/%u bytes received\n",
                  (unsigned)written, (unsigned)fw_size);

    if (written != fw_size) {
        // Should never happen given the loop condition, but guard defensively.
        Update.abort();
        param->contentLength = snprintf(buf, bufsize,
            "ERR: upload incomplete (%u/%u bytes)",
            (unsigned)written, (unsigned)fw_size);
        param->contentType = HTTPFILETYPE_TEXT;
        return FLAG_DATA_RAW;
    }

    // -----------------------------------------------------------------------
    // Phase 2: commit the flash.  Update.end() validates the written image
    // (MD5 checksum) and marks the OTA partition as the next boot target.
    // -----------------------------------------------------------------------
    Serial.println("[OTA] Validating and committing flash…");
    if (!Update.end()) {
        param->contentLength = snprintf(buf, bufsize,
            "ERR: Update.end failed: %s", Update.errorString());
        param->contentType = HTTPFILETYPE_TEXT;
        return FLAG_DATA_RAW;
    }

    Serial.println("[OTA] Flash successful, rebooting in 1.5 s");

    // Schedule a reboot 1.5 s from now so the HTTP 200 response is sent and
    // acknowledged by the client before the TCP connection drops.
    static esp_timer_handle_t s_ota_timer = NULL;
    if (!s_ota_timer) {
        esp_timer_create_args_t args = {};
        args.callback         = ota_restart_cb;
        args.dispatch_method  = ESP_TIMER_TASK;
        args.name             = "ota_restart";
        esp_timer_create(&args, &s_ota_timer);
    } else {
        // Stop any previously armed timer (e.g., a second OTA completed before
        // the first reboot fired) before re-arming.
        esp_timer_stop(s_ota_timer);
    }
    esp_timer_start_once(s_ota_timer, 1500000); // 1.5 s in microseconds

    strcpy(buf, "OK");
    param->contentLength = 2;
    param->contentType   = HTTPFILETYPE_TEXT;
    return FLAG_DATA_RAW;
}

UrlHandler urlHandlerList[]={
    {"api/live", handlerLiveData},
    {"api/info", handlerInfo},
    {"api/control", handlerControl},
    {"api/ota", handlerOTA},
#if STORAGE != STORAGE_NONE
    {"api/list", handlerLogList},
    {"api/data", handlerLogData},
    {"api/log", handlerLogFile},
    {"api/delete", handlerLogDelete},
#endif
    {0}
};

void obtainTime()
{
    sntp_setoperatingmode(SNTP_OPMODE_POLL);
    sntp_setservername(0, (char*)"pool.ntp.org");
    sntp_init();
}

void serverProcess(int timeout)
{
    mwHttpLoop(&httpParam, timeout);
}

bool serverSetup(IPAddress& ip)
{
#if NET_DEVICE == NET_WIFI || ENABLE_WIFI
    WiFi.mode(WIFI_AP_STA);
#else
    WiFi.mode(WIFI_AP);
#endif

    bool staConnected = false;
#if ENABLE_WIFI
    // Try to connect to the home WiFi network first so the HTTPD is
    // reachable on the local network IP rather than the AP fallback IP.
    if (wifiSSID[0]) {
        Serial.print("[WIFI] Joining SSID:");
        Serial.println(wifiSSID);
        WiFi.begin(wifiSSID, wifiPassword);
        for (uint32_t t = millis(); millis() - t < WIFI_JOIN_TIMEOUT;) {
            if (WiFi.status() == WL_CONNECTED) break;
            delay(50);
        }
        if (WiFi.status() == WL_CONNECTED) {
            staConnected = true;
            ip = WiFi.localIP();
        } else {
            Serial.println("[WIFI] STA timeout, starting AP");
        }
    }
#endif
    if (!staConnected) {
        WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
        ip = WiFi.softAPIP();
    }

    mwInitParam(&httpParam, 80, "/spiffs");
    httpParam.pxUrlHandler = urlHandlerList;
    // Limit to 2 simultaneous clients to reduce peak heap usage.
    // With HTTP_BUFFER_SIZE = 4 KB, two connections consume only 8 KB versus
    // the 64 KB that four 16 KB buffers would have needed.
    httpParam.maxClients = 2;

    if (mwServerStart(&httpParam)) {
        return false;
    }

#if NET_DEVICE == NET_WIFI
    obtainTime();
#endif
    return true;
}

#else

void serverProcess(int timeout)
{
    delay(timeout);
}

#endif
