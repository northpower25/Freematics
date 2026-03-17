#include <FreematicsPlus.h>
#include "telestore.h"

void CStorage::log(uint16_t pid, uint8_t values[], uint8_t count)
{
    char buf[256];
    byte n = snprintf(buf, sizeof(buf), "%X%c%u", pid, m_delimiter, (unsigned int)values[0]);
    for (byte m = 1; m < count; m++) {
        n += snprintf(buf + n, sizeof(buf) - n, ";%u", (unsigned int)values[m]);
    }
    dispatch(buf, n);
}

void CStorage::log(uint16_t pid, uint16_t values[], uint8_t count)
{
    char buf[256];
    byte n = snprintf(buf, sizeof(buf), "%X%c%u", pid, m_delimiter, (unsigned int)values[0]);
    for (byte m = 1; m < count; m++) {
        n += snprintf(buf + n, sizeof(buf) - n, ";%u", (unsigned int)values[m]);
    }
    dispatch(buf, n);
}

void CStorage::log(uint16_t pid, uint32_t values[], uint8_t count)
{
    char buf[256];
    byte n = snprintf(buf, sizeof(buf), "%X%c%u", pid, m_delimiter, values[0]);
    for (byte m = 1; m < count; m++) {
        n += snprintf(buf + n, sizeof(buf) - n, ";%u", values[m]);
    }
    dispatch(buf, n);
}

void CStorage::log(uint16_t pid, int32_t values[], uint8_t count)
{
    char buf[256];
    byte n = snprintf(buf, sizeof(buf), "%X%c%d", pid, m_delimiter, values[0]);
    for (byte m = 1; m < count; m++) {
        n += snprintf(buf + n, sizeof(buf) - n, ";%d", values[m]);
    }
    dispatch(buf, n);
}

void CStorage::log(uint16_t pid, float values[], uint8_t count, const char* fmt)
{
    char buf[256];
    char *p = buf + snprintf(buf, sizeof(buf), "%X%c", pid, m_delimiter);
    for (byte m = 0; m < count && (p - buf) < sizeof(buf) - 3; m++) {
        if (m > 0) *(p++) = ';';
        int l = snprintf(p, sizeof(buf) - (p - buf), fmt, values[m]);
        char *q = strchr(p, '.');
        if (q && atoi(q + 1) == 0) {
            *q = 0;
            if (*p == '-' && *(p + 1) == '0') {
                *p = '0';
                *(++p) = 0;
            } else {
                p = q;
            }
        } else {
            p += l;
        }
    }
    dispatch(buf, (int)(p - buf));
}

void CStorage::timestamp(uint32_t ts)
{
    log(PID_TIMESTAMP, &ts, 1);
}

void CStorage::dispatch(const char* buf, byte len)
{
    // output data via serial
    Serial.write((uint8_t*)buf, len);
    Serial.write(' ');
    m_samples++;
}

byte CStorage::checksum(const char* data, int len)
{
    byte sum = 0;
    for (int i = 0; i < len; i++) sum += data[i];
    return sum;
}

void CStorageRAM::dispatch(const char* buf, byte len)
{
    // reserve some space for checksum
    int remain = m_cacheSize - m_cacheBytes - len - 3;
    if (remain < 0) {
        // m_cache full
        return;
    }
    // store data in m_cache
    memcpy(m_cache + m_cacheBytes, buf, len);
    m_cacheBytes += len;
    m_cache[m_cacheBytes++] = ',';
    m_samples++;
}

void CStorageRAM::header(const char* devid)
{
    m_cacheBytes = sprintf(m_cache, "%s#", devid);
}

void CStorageRAM::tailer()
{
    if (m_cache[m_cacheBytes - 1] == ',') m_cacheBytes--;
    m_cacheBytes += sprintf(m_cache + m_cacheBytes, "*%X", (unsigned int)checksum(m_cache, m_cacheBytes));
}

void CStorageRAM::untailer()
{
    char *p = strrchr(m_cache, '*');
    if (p) {
        *p = ',';
        m_cacheBytes = p + 1 - m_cache;
    }
}

void FileLogger::dispatch(const char* buf, byte len)
{
    if (m_id == 0) return;

    if (m_file.write((uint8_t*)buf, len) != len) {
        // try again
        if (m_file.write((uint8_t*)buf, len) != len) {
            Serial.println("Error writing. End file logging.");
            end();
            return;
        }
    }
    m_file.write('\n');
    m_size += (len + 1);
}

void FileLogger::logEvent(const char* text)
{
    // Prefix with PID 0xFE so the line is properly formatted for CSV yet
    // never matched by normal data queries (handlerLogData skips unknown PIDs).
    // The raw /api/log file view shows the full human-readable text.
    // 160 bytes = 4 ("FE,") + up to 155 chars of text + NUL; callers format
    // their message into diag[128] so the combined length is always ≤ 132.
    char buf[160];
    int n = snprintf(buf, sizeof(buf), "FE,%s", text);
    if (n > 0 && n < (int)sizeof(buf)) {
        dispatch(buf, (byte)n);
    }
}

int FileLogger::getFileID(File& root)
{
    if (root) {
        File file;
        int id = 0;
        while(file = root.openNextFile()) {
            char *p = strrchr(file.name(), '/');
            unsigned int n = atoi(p ? p + 1 : file.name());
            if (n > id) id = n;
        }
        return id + 1;
    } else {
        return 0;
    }
}

bool SDLogger::init()
{
    SPI.begin();
    if (SD.begin(PIN_SD_CS, SPI, SPI_FREQ)) {
        unsigned int total = SD.totalBytes() >> 20;
        unsigned int used = SD.usedBytes() >> 20;
        Serial.print("SD:");
        Serial.print(total);
        Serial.print(" MB total, ");
        Serial.print(used);
        Serial.println(" MB used");
        return true;
    } else {
        Serial.println("NO SD CARD");
        return false;
    }
}

uint32_t SDLogger::begin()
{
    File root = SD.open("/DATA");
    m_id = getFileID(root);
    if (m_id == 0) {
        SD.mkdir("/DATA");
        m_id = 1;
    }
    char path[24];
    sprintf(path, "/DATA/%u.CSV", m_id);
    Serial.print("File: ");
    Serial.println(path);
    m_file = SD.open(path, FILE_WRITE);
    if (!m_file) {
        Serial.println("File error");
        m_id = 0;
    }
    m_dataCount = 0;
    return m_id;
}

void SDLogger::flush()
{
    char path[24];
    sprintf(path, "/DATA/%u.CSV", m_id);
    m_file.close();
    m_file = SD.open(path, FILE_APPEND);
    if (!m_file) {
        Serial.println("File error");
    }
}

bool SDLogger::purge()
{
    // Check if cleanup is needed: only purge when SD is >= 80% full.
    uint64_t total = SD.totalBytes();
    if (total == 0) return false;
    uint64_t used = SD.usedBytes();
    // free < 20% of total → trigger purge
    if (total - used >= total / 5) return false;  // still >= 20% free

    // Build a sorted list of file IDs under /DATA (ascending = oldest first).
    // We collect up to 512 IDs to avoid dynamic allocation; in practice the
    // directory never has that many files before space is exhausted.
    static const int MAX_IDS = 512;
    uint32_t ids[MAX_IDS];
    int count = 0;

    File root = SD.open("/DATA");
    if (!root) return false;
    File file;
    while ((file = root.openNextFile()) && count < MAX_IDS) {
        const char* name = file.name();
        // name may include the path prefix depending on ESP32 Arduino version
        const char* slash = strrchr(name, '/');
        const char* base = slash ? slash + 1 : name;
        unsigned int n = (unsigned int)atoi(base);
        if (n != 0) ids[count++] = n;
        file.close();
    }
    root.close();

    if (count == 0) return false;

    // Sort ascending (insertion sort — small count, runs on MCU).
    for (int i = 1; i < count; i++) {
        uint32_t key = ids[i];
        int j = i - 1;
        while (j >= 0 && ids[j] > key) { ids[j + 1] = ids[j]; j--; }
        ids[j + 1] = key;
    }

    // Close the active log file once before the deletion loop so the SPI bus
    // is not interleaved between remove() calls and file re-opens.  We reopen
    // it once after all deletions are done.
    bool wasOpen = (m_id != 0);
    if (wasOpen) m_file.close();

    // Delete the oldest 20% of files (at least 1), skipping the active file.
    int toDelete = count / 5;
    if (toDelete < 1) toDelete = 1;
    bool any = false;
    char path[24];
    for (int i = 0; i < count && toDelete > 0; i++) {
        if (ids[i] == m_id) continue;  // never delete the currently open file
        sprintf(path, "/DATA/%u.CSV", ids[i]);
        if (SD.remove(path)) {
            Serial.print("[SD] Purged ");
            Serial.println(path);
            any = true;
            toDelete--;
        }
        // Re-check free space — stop early if we freed enough.
        uint64_t t2 = SD.totalBytes();
        uint64_t u2 = SD.usedBytes();
        if (t2 > 0 && t2 - u2 >= t2 / 5) break;
    }

    // Reopen the active log file now that all deletions are complete.
    if (wasOpen) {
        sprintf(path, "/DATA/%u.CSV", m_id);
        m_file = SD.open(path, FILE_APPEND);
        if (!m_file) m_id = 0;
    }
    return any;
}

bool SPIFFSLogger::init()
{
    bool mounted = SPIFFS.begin();
    if (!mounted) {
        Serial.println("Formatting SPIFFS...");
        mounted = SPIFFS.begin(true);
    }
    if (mounted) {
        Serial.print("SPIFFS:");
        Serial.print(SPIFFS.totalBytes());
        Serial.print(" bytes total, ");
        Serial.print(SPIFFS.usedBytes());
        Serial.println(" bytes used");
    } else {
        Serial.println("No SPIFFS");
    }
    return mounted;
}

uint32_t SPIFFSLogger::begin()
{
    File root = SPIFFS.open("/");
    m_id = getFileID(root);
    char path[24];
    sprintf(path, "/DATA/%u.CSV", m_id);
    Serial.print("File: ");
    Serial.println(path);
    m_file = SPIFFS.open(path, FILE_WRITE);
    if (!m_file) {
        Serial.println("File error");
        m_id = 0;
    }
    m_dataCount = 0;
    return m_id;
}

void SPIFFSLogger::purge()
{
    // remove oldest file when unused space is insufficient
    File root = SPIFFS.open("/");
    File file;
    int idx = 0;
    while(file = root.openNextFile()) {
        if (!strncmp(file.name(), "/DATA/", 6)) {
            unsigned int n = atoi(file.name() + 6);
            if (n != 0 && (idx == 0 || n < idx)) idx = n;
        }
    }
    if (idx) {
        m_file.close();
        char path[32];
        sprintf(path, "/DATA/%u.CSV", idx);
        SPIFFS.remove(path);
        Serial.print(path);
        Serial.println(" removed");
        sprintf(path, "/DATA/%u.CSV", m_id);
        m_file = SPIFFS.open(path, FILE_APPEND);
        if (!m_file) m_id = 0;
    }
}
