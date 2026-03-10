/*************************************************************************
* Helper classes for various network communication devices
* Distributed under BSD license
* Visit https://freematics.com for more inform
on
* (C)2012-2021 Developed by Stanley Huang <stanley@freematics.com.au>
*************************************************************************/

#include <Arduino.h>
#include "FreematicsBase.h"
#include "FreematicsNetwork.h"

// Runtime cellular debug flag – set to 1 via NVS key CELL_DEBUG (written by
// the HA config/options flow).  Declared extern in FreematicsNetwork.h so
// telelogger.ino can read it from NVS and assign it after loadConfig().
uint8_t cellNetDebug = 0;

String HTTPClient::genHeader(HTTP_METHOD method, const char* path, const char* payload, int payloadSize)
{
  String header;
  // generate a simplest HTTP header
  header = method == METHOD_GET ? "GET " : "POST ";
  // Normalise path: strip scheme and host if a caller accidentally passes a
  // full URL ("https://host/path") or a host-prefixed path ("host/path").
  // AWS ELB (hooks.nabu.casa) returns "400 Bad Request" for absolute-form
  // request lines.
  String p = path ? String(path) : String("/");
  // 1. Strip scheme (e.g. "https://") if present.
  int schemeEnd = p.indexOf("://");
  if (schemeEnd >= 0) p = p.substring(schemeEnd + 3);
  // 2. If the result does not start with '/' it still has a host (and optional
  //    port) prefix — e.g. "hooks.nabu.casa/gAAAA..." or "host:443/path".
  //    Find the first '/' and take everything from there as the path.
  if (!p.startsWith("/")) {
    int slashPos = p.indexOf('/');
    if (slashPos >= 0) {
      p = p.substring(slashPos);  // includes the leading '/'
    } else {
      p = "/";  // host with no path → use root
    }
  }
  header += p;
  header += " HTTP/1.1\r\nHost: ";
  header += m_host;
  // Use Connection: close to ensure the server closes the TCP session after
  // each response.  This avoids keep-alive edge cases (un-drained buffers,
  // stale sessions) that are particularly problematic over cellular links.
  header += "\r\nConnection: close";
  if (method != METHOD_GET) {
    header += "\r\nContent-Type: application/json\r\nContent-Length: ";
    header += String(payloadSize);
  }
  header += "\r\n\r\n";
  return header;
}

/*******************************************************************************
  Implementation for WiFi (on top of Arduino WiFi library)
*******************************************************************************/

bool ClientWIFI::setup(unsigned int timeout)
{
  for (uint32_t t = millis(); millis() - t < timeout;) {
    if (WiFi.status() == WL_CONNECTED) {
      return true;
    }
    delay(50);
  }
  return false;
}

String ClientWIFI::getIP()
{
  return WiFi.localIP().toString();
}

bool ClientWIFI::begin(const char* ssid, const char* password)
{
  //listAPs();
#ifndef ARDUINO_ESP32C3_DEV
  // Set TX power before begin so the full connection handshake (auth + DHCP)
  // uses this power level. 17 dBm gives reliable range without maximum
  // interference to the co-located cellular radio.
  WiFi.setTxPower(WIFI_POWER_17dBm);
#endif
  WiFi.begin(ssid, password);
  return true;
}

void ClientWIFI::end()
{
  WiFi.disconnect(true);
}

void ClientWIFI::listAPs()
{
  int n = WiFi.scanNetworks();
  if (n <= 0) {
      Serial.println("No WiFi AP found");
  } else {
      Serial.println("Nearby WiFi APs:");
      for (int i = 0; i < n; ++i) {
          // Print SSID and RSSI for each network found
          Serial.print(i + 1);
          Serial.print(": ");
          Serial.print(WiFi.SSID(i));
          Serial.print(" (");
          Serial.print(WiFi.RSSI(i));
          Serial.println("dB)");
      }
  }
}

bool WifiUDP::open(const char* host, uint16_t port)
{
  if (udp.beginPacket(host, port)) {
    udpIP = udp.remoteIP();
    udpPort = port;
    if (udp.endPacket()) {
      return true;
    }
  }
  return false;
}

bool WifiUDP::send(const char* data, unsigned int len)
{
  if (udp.beginPacket(udpIP, udpPort)) {
    if (udp.write((uint8_t*)data, len) == len && udp.endPacket()) {
      return true;
    }
  }
  return false;
}

int WifiUDP::receive(char* buffer, int bufsize, unsigned int timeout)
{
  uint32_t t = millis();
  do {
    int bytes = udp.parsePacket();
    if (bytes > 0) {
      bytes = udp.read(buffer, bufsize);
      return bytes;
    }
    delay(1);
  } while (millis() - t < timeout);
  return 0;
}

String WifiUDP::queryIP(const char* host)
{
  return udpIP.toString();
}

void WifiUDP::close()
{
  udp.stop();
}

bool WifiHTTP::open(const char* host, uint16_t port)
{
  if (!host) return true;
  // Ensure any previous (possibly failed) TLS session is fully torn down
  // before starting a new handshake.  WiFiClientSecure::connect() does not
  // always release the mbedTLS context on a partially-initialised connection,
  // leading to memory leaks across retries and ultimately causing
  // MBEDTLS_ERR_SSL_ALLOC_FAILED / RSA BIGNUM alloc failures.
  client.stop();
  client.setInsecure(); // skip certificate verification for HTTPS
  if (client.connect(host, port)) {
    m_state = HTTP_CONNECTED;
    m_host = host;
    return true;
  } else {
    m_state = HTTP_ERROR;
    return false;
  }
}

void WifiHTTP::close()
{
  client.stop();
  m_state = HTTP_DISCONNECTED;
}

bool WifiHTTP::send(HTTP_METHOD method, const char* path, const char* payload, int payloadSize)
{
  String header = genHeader(method, path, payload, payloadSize);
  int len = header.length();
  if (client.write((const uint8_t*)header.c_str(), len) != (size_t)len) {
    m_state = HTTP_DISCONNECTED;
    return false;
  }
  if (payloadSize) {
    if (client.write((const uint8_t*)payload, payloadSize) != (size_t)payloadSize) {
      m_state = HTTP_ERROR;
      return false;
    }
  }
  m_state = HTTP_SENT;
  return true;
}

char* WifiHTTP::receive(char* buffer, int bufsize, int* pbytes, unsigned int timeout)
{
  int bytes = 0;
  int contentBytes = 0;
  int contentLen = 0;
  char* content = 0;
  bool keepAlive = true;

  for (uint32_t t = millis(); millis() - t < timeout && bytes < bufsize; ) {
    if (!client.available()) {
      delay(1);
      continue;
    }
    buffer[bytes++] = client.read();
    buffer[bytes] = 0;
    if (content) {
      if (++contentBytes == contentLen) break;
    } else if (strstr(buffer, "\r\n\r\n")) {
      // parse HTTP header
      char *p = strstr(buffer, "HTTP/1.");
      if (p) m_code = atoi(p + 9);
      keepAlive = strstr(buffer, ": close\r\n") == 0;
      p = strstr(buffer, "Content-Length: ");
      if (!p) p = strstr(buffer, "Content-length: ");
      if (p) {
        contentLen = atoi(p + 16);
      }
      content = buffer + bytes;
      if (contentLen == 0) break; // empty body – return immediately
    }
  }
  if (!content) {
    m_state = HTTP_ERROR;
    close(); // prevent socket leak on timeout
    return 0;
  }

  m_state = HTTP_CONNECTED;
  if (pbytes) *pbytes = contentBytes;
  if (!keepAlive) close();
  return content;
}

/*******************************************************************************
  SIM7600/SIM7070/SIM5360
*******************************************************************************/
bool CellSIMCOM::begin(CFreematics* device)
{
  if (!getBuffer()) {
    Serial.println("[CELL] OOM: buffer allocation failed");
    return false;
  }
  m_device = device;
  for (byte n = 0; n < 30; n++) {
    device->xbTogglePower(200);
    device->xbPurge();
    if (!check(2000)) continue;
    if (sendCommand("ATE0\r") && sendCommand("ATI\r")) {
      // retrieve module info
      //Serial.print(m_buffer);
      char *p = strstr(m_buffer, "Model:");
      if (!p) {
        sendCommand("AT+SIMCOMATI\r");
        p = strstr(m_buffer, "QCN:");
        if (p) {
          char *q = strchr(p += 4, '_');
          if (q) {
            int l = q - p;
            if (l >= sizeof(m_model)) l = sizeof(m_model) - 1;
            memcpy(m_model, p, l);
            m_model[l] = 0;
          }
        }
        m_type = CELL_SIM7070;
      } else {
        p += 7;
        char *q = strchr(p, '_');
        if (q) p = q + 1;
        for (int i = 0; i < sizeof(m_model) - 1 && p[i] && p[i] != '\r' && p[i] != '\n'; i++) {
            m_model[i] = p[i];
        } 
        if (strstr(m_model, "5360"))
          m_type = CELL_SIM5360;
        else if (strstr(m_model, "7670"))
          m_type = CELL_SIM7670;
        else
          m_type = CELL_SIM7600;
      }
      p = strstr(m_buffer, "IMEI:");
      if (p) strncpy(IMEI, p[5] == ' ' ? p + 6 : p + 5, sizeof(IMEI) - 1);
      return true;
    }
  }
  end();
  return false;
}

void CellSIMCOM::end()
{
  setGPS(false);
  if (m_type == CELL_SIM7070) {
    if (!sendCommand("AT+CPOWD=1\r", 1000, "NORMAL POWER DOWN")) {
      if (m_device) m_device->xbTogglePower(2510);
    } else {
      delay(1500);
    }
  } else {
    if (!sendCommand("AT+CPOF\r")) {
      if (m_device) m_device->xbTogglePower(2510);
    } else {
      delay(1500);
    }
  }
}

bool CellSIMCOM::setup(const char* apn, const char* username, const char* password, unsigned int timeout)
{
  if (!m_buffer) return false;
  uint32_t t = millis();
  bool success = false;

  if (m_type == CELL_SIM7070) {
    do {
      do {
        success = false;
        sendCommand("AT+CFUN=1\r");
        do {
          delay(500);
          if (sendCommand("AT+CGREG?\r",1000, "+CGREG: 0,")) {
            char *p = strstr(m_buffer, "+CGREG: 0,");
            if (p) {
              char ret = *(p + 10);
              success = ret == '1' || ret == '5';
            }
          }
        } while (!success && millis() - t < timeout);
        if (!success) break;
        success = sendCommand("AT+CGACT?\r", 1000, "+CGACT: 1,");
        break;
      } while (millis() - t < timeout);
      if (!success) break;

      sendCommand("AT+CGNAPN\r");
      if (apn && *apn) {
        if (username && password) {
          sprintf(m_buffer, "AT+CNCFG=0,0,\"%s\",\"%s\",\"%s\",3\r", apn, username, password);
        } else {
          sprintf(m_buffer, "AT+CNCFG=0,0,\"%s\"\r", apn);
        }
        sendCommand(m_buffer);
      }
      sendCommand("AT+CNACT=0,1\r");
      sendCommand("AT+CNSMOD?\r");
      sendCommand("AT+CSCLK=0\r");
    } while(0);
  } else {
    do {
      // Flush any stale UART data (leftover OK, URCs from checkSIM, etc.) so that
      // the first AT+CPSI? response is not mixed with unrelated earlier traffic.
      m_device->xbPurge();
      do {
        // Flush any URCs that arrived during the previous poll interval
        // (e.g. +CREG, +CEREG registration URCs) so they do not compete
        // with the AT+CPSI? response inside the 500 ms xbReceive window.
        m_device->xbPurge();
        m_device->xbWrite("AT+CPSI?\r");
        m_buffer[0] = 0;
        const char* answers[] = {"NO SERVICE", ",Online", ",Offline", ",Low Power Mode"};
        int ret = m_device->xbReceive(m_buffer, RECV_BUF_SIZE, 500, answers, 4);
        if (ret == 2) {
          success = true;
          break;
        }
        // ret == 4 → ",Low Power Mode": modem cannot register in this state.
        // ret == -1 → unexpected data (e.g. registration URCs that don't match any
        //             expected pattern): do NOT break – just retry on the next poll
        //             cycle so those stray bytes do not abort the search prematurely.
        if (ret == 4) break;
        delay(500);
      } while (millis() - t < timeout);
      if (!success) break;

      success = false;
      do {
        delay(100);
        if (sendCommand("AT+CREG?\r", 1000, "+CREG: 0,")) {
          char *p = strstr(m_buffer, "+CREG: 0,");
          // Fix operator-precedence: ensure all three registration states (home=1,
          // roaming=5, SMS-only=6) are guarded by the null-check on p.
          success = p && (*(p + 9) == '1' || *(p + 9) == '5' || *(p + 9) == '6');
        }
      } while (!success && millis() - t < timeout);
      if (!success) break;
      
      /*
      if (m_type == CELL_SIM7600) {
        success = false;
        do {
          delay(100);
          if (sendCommand("AT+CGREG?\r",1000, "+CGREG: 0,")) {
            char *p = strstr(m_buffer, "+CGREG: 0,");
            success = (p && (*(p + 10) == '1' || *(p + 10) == '5'));
          }
        } while (!success && millis() - t < timeout);
        if (!success) break;
      }
      */


      if (m_type == CELL_SIM7670) {
        if (apn && *apn) {
          sprintf(m_buffer, "AT+CGDCONT=1,\"IP\",\"%s\"\r", apn);
          sendCommand(m_buffer);
        }
      } else {
        if (apn && *apn) {
          sprintf(m_buffer, "AT+CGSOCKCONT=1,\"IP\",\"%s\"\r", apn);
          sendCommand(m_buffer);
          if (username && password) {
            sprintf(m_buffer, "AT+CSOCKAUTH=1,1,\"%s\",\"%s\"\r", username, password);
            sendCommand(m_buffer);
          }
        }
        sendCommand("AT+CSOCKSETPN=1\r");
        sendCommand("AT+CIPMODE=0\r");
      }
      sendCommand("AT+NETOPEN\r");
    } while(0);
  }
  if (!success) Serial.println(m_buffer);
  return success;
}

bool CellSIMCOM::setGPS(bool on)
{
  if (on) {
    if (m_type == CELL_SIM7070) {
      sendCommand("AT+CGNSPWR=1\r");
      sendCommand("AT+CGNSMOD=1,1,0,0,0\r");
      if (sendCommand("AT+CGNSINF\r", 1000, "+CGNSINF:")) {
        if (!m_gps) {
          m_gps = new GPS_DATA;
          memset(m_gps, 0, sizeof(GPS_DATA));
        }
        return true;
      }
    } else {
      sendCommand("AT+CVAUXV=61\r", 100);
      sendCommand("AT+CVAUXS=1\r", 100);
      for (byte n = 0; n < 3; n++) {
        if ((sendCommand("AT+CGPS=1,1\r") && sendCommand("AT+CGPSINFO=1\r")) || sendCommand("AT+CGPS?\r", 100, "+CGPS: 1")) {
          if (!m_gps) {
            m_gps = new GPS_DATA;
            memset(m_gps, 0, sizeof(GPS_DATA));
          }
          return true;
        }
        sendCommand("AT+CGPS=0\r", 100);
      }
    }
  } else if (m_gps) {
    if (m_type == CELL_SIM7070) {
      sendCommand("AT+CGNSPWR=0\r");
    } else {
      //sendCommand("AT+CVAUXS=0\r");
      sendCommand("AT+CGPS=0\r", 100);
    }
    GPS_DATA *g = m_gps;
    m_gps = 0;
    delete g;
    return true;
  }
  return false;
}

bool CellSIMCOM::getLocation(GPS_DATA** pgd)
{
  if (m_gps) {
      if (pgd) *pgd = m_gps;
      return m_gps->ts != 0;
  } else {
      return false;
  }
}

String CellSIMCOM::getIP()
{
  if (m_type == CELL_SIM7070) {
    sendCommand("AT+CNACT=0,1\r");
    for (int i = 0; i < 30; i++) {
      delay(500);
      if (sendCommand("AT+CNACT?\r", 1000)) {
        char *ip = strstr(m_buffer, "+CNACT:");
        if (ip) {
          ip = strchr(ip, '\"');
          if (ip++ && *ip != '0') {
            char *q = strchr(ip, '\"');
            if (q) *q = 0;
            return ip;
          }
        }
      }
    }
  } else {
    uint32_t t = millis();
    do {
      if (sendCommand("AT+IPADDR\r", 3000, "\r\nOK\r\n")) {
        char *p = strstr(m_buffer, "+IPADDR:");
        if (p) {
          char *ip = p + 9;
          if (*ip != '0') {
            char *q = strchr(ip, '\r');
            if (q) *q = 0;
            return ip;
          }
        }
      }
      if (m_type == CELL_SIM7670) break;
      delay(500);
    } while (millis() - t < 15000);
  } 
  return "";
}

int CellSIMCOM::RSSI()
{
  if (sendCommand("AT+CSQ\r")) {
      char *p = strchr(m_buffer, ':');
      if (p) {
        int csq = atoi(p + 2);
        if (csq != 99) {
          return csq * 2 - 113;
        }
      }
  }
  return 0;
}

String CellSIMCOM::getOperatorName()
{
  if (sendCommand("AT+COPS?\r")) {
      char *p = strstr(m_buffer, ",\"");
      if (p) {
          p += 2;
          char *s = strchr(p, '\"');
          if (s) *s = 0;
          return p;
      }
  }
  return "";
}

bool CellSIMCOM::check(unsigned int timeout)
{
  uint32_t t = millis();
  do {
      if (sendCommand("AT\rAT\r", 250)) return true;
  } while (millis() - t < timeout);
  return false;
}

bool CellSIMCOM::checkSIM(const char* pin)
{
  bool success;
  if (pin && *pin) {
    snprintf(m_buffer, RECV_BUF_SIZE, "AT+CPIN=\"%s\"\r", pin);
    sendCommand(m_buffer);
  }
  for (byte n = 0; n < 20 && !(success = sendCommand("AT+CPIN?\r", 500, ": READY")); n++);
  if (!success) {
    // avoid SIM card lockout
    sendCommand("AT+RPMPARAM=0\r");
    success = sendCommand("AT+CPIN?\r", 500, ": READY");
  }
  return success;  
}

String CellSIMCOM::queryIP(const char* host)
{
  if (m_type == CELL_SIM7070) {
    sprintf(m_buffer, "AT+CDNSGIP=\"%s\",1,3000\r", host);
    if (sendCommand(m_buffer, 10000, "+CDNSGIP:")) {
      char *p = strstr(m_buffer, host);
      if (p) {
        p = strstr(p, "\",\"");
        if (p) {
          char *ip = p + 3;
          p = strchr(ip, '\"');
          if (p) *p = 0;
          return ip;
        }
      }
    }
  } else {
    sprintf(m_buffer, "AT+CDNSGIP=\"%s\"\r", host);
    if (sendCommand(m_buffer, 10000)) {
      char *p = strstr(m_buffer, host);
      if (p) {
        p = strstr(p, ",\"");
        if (p) {
          char *ip = p + 2;
          p = strchr(ip, '\"');
          if (p) *p = 0;
          return ip;
        }
      }
    }
  }
  return "";
}

bool CellSIMCOM::sendCommand(const char* cmd, unsigned int timeout, const char* expected)
{
  if (!m_buffer) return false;
  if (cmd) {
    m_device->xbWrite(cmd);
    delay(10);
  }
  m_buffer[0] = 0;
  const char* answers[] = {"\r\nOK", "\r\nERROR"};
  byte ret = m_device->xbReceive(m_buffer, RECV_BUF_SIZE, timeout, expected ? &expected : answers, expected ? 1 : 2);
  inbound();
  return ret == 1;
}

float CellSIMCOM::parseDegree(const char* s)
{
  char *p;
  unsigned long left = atol(s);
  unsigned long tenk_minutes = (left % 100UL) * 100000UL;
  if ((p = strchr(s, '.')))
  {
    unsigned long mult = 10000;
    while (isdigit(*++p))
    {
      tenk_minutes += mult * (*p - '0');
      mult /= 10;
    }
  }
  return (left / 100) + (float)tenk_minutes / 6 / 1000000;
}

void CellSIMCOM::checkGPS()
{
  if (!m_gps) return;
  // check and parse GPS data
  if (m_type == CELL_SIM7070) {
    if (sendCommand("AT+CGNSINF\r", 100, "+CGNSINF:")) do {
      char *p;
      if (!(p = strchr(m_buffer, ':'))) break;
      p += 2;
      if (strncmp(p, "1,1,", 4)) break;
      p += 4;
      m_gps->time = atol(p + 8) * 100 + atoi(p + 15);
      *(p + 8) = 0;
      int day = atoi(p + 6);
      *(p + 6) = 0;
      int month = atoi(p + 4);
      *(p + 4) = 0;
      int year = atoi(p + 2);
      m_gps->date = year + month * 100 + day * 10000;
      if (!(p = strchr(p + 9, ','))) break;
      m_gps->lat = atof(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->lng = atof(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->alt = atof(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->speed = atof(++p) * 1000 / 1852;
      if (!(p = strchr(p, ','))) break;
      m_gps->heading = atoi(++p);
      m_gps->ts = millis();
    } while (0);
  }
}

void CellSIMCOM::inbound()
{
  if (m_type == CELL_SIM7070) {
    if (strstr(m_buffer, "+CADATAIND: 0") || strstr(m_buffer, "+SHREAD:")) {
      m_incoming = 1;
    }
  } else {
    char *p;
    if (m_gps && (p = strstr(m_buffer, "+CGPSINFO:"))) do {
      if (!(p = strchr(p, ':'))) break;
      if (*(++p) == ',') break;
      m_gps->lat = parseDegree(p);
      if (!(p = strchr(p, ','))) break;
      if (*(++p) == 'S') m_gps->lat = -m_gps->lat;
      if (!(p = strchr(p, ','))) break;
      m_gps->lng = parseDegree(++p);
      if (!(p = strchr(p, ','))) break;
      if (*(++p) == 'W') m_gps->lng = -m_gps->lng;
      if (!(p = strchr(p, ','))) break;
      m_gps->date = atoi(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->time = atof(++p) * 100;
      if (!(p = strchr(p, ','))) break;
      m_gps->alt = atof(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->speed = atof(++p);
      if (!(p = strchr(p, ','))) break;
      m_gps->heading = atoi(++p);
      m_gps->ts = millis();
    } while (0);

    // SIM5360 / old SIM7600 firmware: "+CHTTPSRECV EVENT,<conid>"  → contains "RECV EVENT"
    // Newer SIM7600 firmware:          "+CHTTPSRECV: EVENT,<conid>" → contains "+CHTTPSRECV: EVENT"
    // SIM7600 CCH (raw SSL socket):    "+CCHRECV: <session>,<len>"  → e.g. "+CCHRECV: 0,148"
    //   or "+CCHRECV:<session>,<len>" (no-space firmware variant).
    //   We always use session 0 (AT+CCHOPEN=0 / AT+CCHRECV=0), so matching
    //   "+CCHRECV: 0," / "+CCHRECV:0," is unambiguous and does not conflict
    //   with "+CCHRECV: DATA,0,<len>" responses (which start with "DATA").
    // All must set m_incoming so that CellHTTP::receive() proceeds without a
    // full timeout waiting for a URC that was already buffered.
    if (strstr(m_buffer, "+IPD") || strstr(m_buffer, "RECV EVENT") ||
        strstr(m_buffer, "+CHTTPSRECV: EVENT") ||
        strstr(m_buffer, "+CCHRECV: 0,") || strstr(m_buffer, "+CCHRECV:0,")) {
      if (cellNetDebug) Serial.println("[CELL] Incoming data");
      m_incoming = 1;
    }
  }
}

char* CellSIMCOM::getBuffer()
{
  if (!m_buffer) m_buffer = (char*)malloc(RECV_BUF_SIZE);
  return m_buffer;
}

bool CellUDP::open(const char* host, uint16_t port)
{
  if (host) {
    udpIP = queryIP(host);
    if (!udpIP.length()) {
      udpIP = host;
    }
    udpPort = port;
  }
  if (!udpIP.length()) return false;
  if (m_type == CELL_SIM7070) {
    sendCommand("AT+CNACT=0,1\r");
    sendCommand("AT+CACID=0\r");
    sprintf(m_buffer, "AT+CAOPEN=0,0,\"UDP\",\"%s\",%u\r", udpIP.c_str(), udpPort);
    if (!sendCommand(m_buffer, 3000)) {
      Serial.println(m_buffer);
      return false;
    }
    return true;
  } else {
    sprintf(m_buffer, "AT+CIPOPEN=0,\"UDP\",\"%s\",%u,8000\r", udpIP.c_str(), udpPort);
    if (!sendCommand(m_buffer, 3000)) {
      Serial.println(m_buffer);
      return false;
    }
    return true;
  }
}

bool CellUDP::close()
{
  if (m_type == CELL_SIM7070) {
    sendCommand("AT+CACLOSE=0\r");
    return sendCommand("AT+CNACT=0,0\r");
  } else {
    return sendCommand("AT+CIPCLOSE=0\r");
  }
}

bool CellUDP::send(const char* data, unsigned int len)
{
  if (m_type == CELL_SIM7070) {
    sendCommand("AT+CASTATE?\r");
    sprintf(m_buffer, "AT+CASEND=0,%u\r", len);
    sendCommand(m_buffer, 100, "\r\n>");
    if (sendCommand(data, 1000)) return true;
  } else {
    int n = sprintf(m_buffer, "AT+CIPSEND=0,%u,\"%s\",%u\r", len, udpIP.c_str(), udpPort);
    m_device->xbWrite(m_buffer, n);
    delay(10);
    m_device->xbWrite(data, len);
    const char* answers[] = {"\r\nERROR", "OK\r\n\r\n+CIPSEND:", "\r\nRECV FROM:"};
    byte ret = m_device->xbReceive(m_buffer, RECV_BUF_SIZE, 1000, answers, 3);
    if (ret > 1) return true;
  }
  return false;
}

char* CellUDP::receive(int* pbytes, unsigned int timeout)
{
  if (m_type == CELL_SIM7070) {
    if (!m_incoming && timeout) sendCommand(0, timeout, "+CADATAIND: 0");
    if (!m_incoming) return 0;
    m_incoming = 0;
    if (sendCommand("AT+CARECV=0,384\r", timeout)) {
      char *p = strstr(m_buffer, "+CARECV: ");
      if (p) {
        if (pbytes) *pbytes = atoi(p + 9);
        p = strchr(m_buffer, ',');
        return p ? p + 1 : m_buffer;
      }
    }
  } else {
    if (!m_incoming && timeout) sendCommand(0, timeout, "+IPD");
    if (m_incoming) {
      m_incoming = 0;
      char *p = strstr(m_buffer, "+IPD");
      if (p) {
        *p = '-'; // mark this datagram as checked
        int len = atoi(p + 4);
        if (pbytes) *pbytes = len;
        p = strchr(p, '\n');
        if (p) {
          if (strlen(++p) > len) *(p + len) = 0;
          return p;
        }
      }
    }
  }  
  return 0;
}

void CellHTTP::init()
{
  if (m_type == CELL_SIM7670) {
    sendCommand("AT+CSSLCFG=\"sslversion\",0,4\r");
    sendCommand("AT+CSSLCFG=\"authmode\",0,0\r");
  } else if (m_type == CELL_SIM7600) {
    // Use AT+CCH (raw SSL client socket) instead of the AT+CHTTPS HTTPS stack.
    // Root cause of +CHTTPS_PEER_CLOSED on Cloudflare / nabu.casa:
    //   The SIM7600E-H CHTTPS stack unconditionally advertises h2 (HTTP/2) in
    //   the TLS ClientHello ALPN extension, regardless of AT+CSSLCFG settings.
    //   When Cloudflare selects h2 it immediately sends an HTTP/2 Connection
    //   Preface (SETTINGS frame).  The CHTTPS stack cannot process HTTP/2 and
    //   closes the session (+CHTTPS_PEER_CLOSED) before AT+CHTTPSSEND can run.
    //   AT+CCHOPEN uses SSL context 0 (configured by AT+CSSLCFG below) which
    //   correctly honours the alpnprotocol restriction to "http/1.1", so
    //   Cloudflare negotiates HTTP/1.1 and the connection stays open for
    //   AT+CCHSEND.  All other AT+CSSLCFG settings (sslversion, authmode,
    //   ignorertctime) apply to the CCH interface in the same way as before.
    //
    // Enable automatic time zone update from the network (NITZ). The modem RTC
    // is updated when the network provides time, ensuring TLS certificate
    // validity checks pass. AT+CSSLCFG="ignorertctime" provides belt-and-
    // suspenders, but some SIM7600E-H firmware revisions do not honour it; CTZU
    // guarantees the RTC is correct regardless of firmware behaviour.
    sendCommand("AT+CTZU=1\r");
    // Query and log the current modem RTC so that time-related TLS failures
    // (certificate "not yet valid") are visible in the console output.
    // NITZ sync happens asynchronously after cell registration; the year
    // reported here must be >= 2024 for certificates to validate.
    // AT+CSSLCFG="ignorertctime",n,1 provides a belt-and-suspenders bypass,
    // but some SIM7600E-H firmware revisions silently ignore it.
    // Use default OK/ERROR termination so the full +CCLK: response line is
    // guaranteed to be in the buffer before we search for it.
    // Response format: +CCLK: "YY/MM/DD,HH:MM:SS±TZ"
    // p+7 points past "+CCLK: " (6-char token + 1 space) to the quoted time.
    if (sendCommand("AT+CCLK?\r", 1000)) {
      char *p = strstr(m_buffer, "+CCLK:");
      if (p) {
        Serial.print("[CELL] RTC: ");
        char *eol = strchr(p, '\r');
        if (!eol) eol = strchr(p, '\n');
        if (eol) *eol = 0;
        Serial.println(p + 7);  // skip "+CCLK: " (6 chars + 1 space)
      }
    }
    sendCommand("AT+CCHSTOP\r");
    // Helper to apply SSL context 0 and 1 settings.  Called both before and
    // after AT+CCHSTART: some SIM7600E-H firmware versions re-initialise the
    // SSL context at CCHSTART time, clearing any previously configured
    // AT+CSSLCFG settings.  Re-applying afterwards guarantees they take
    // effect regardless of firmware behaviour — the same approach used for
    // AT+CHTTPSSTART.  Both SSL context 0 and 1 are configured because some
    // SIM7600E-H firmware revisions map AT+CCHOPEN session 0 to SSL context 1
    // instead of context 0.  Without alpnprotocol="http/1.1", the modem
    // advertises h2 and Cloudflare / nabu.casa negotiate HTTP/2, then
    // immediately close the connection (+CCH_PEER_CLOSED) because the modem
    // has no HTTP/2 stack.
    auto applySslCfg = [this]() {
      // Apply SSL settings to both context 0 and context 1.
      // Some SIM7600E-H firmware revisions map AT+CCHOPEN session 0 to
      // SSL context 1 instead of context 0; configuring both guarantees
      // the correct settings are in place regardless of firmware variant.
      for (int ctx = 0; ctx <= 1; ctx++) {
        // Use TLS 1.2 (sslversion=3) rather than "TLS 1.2 or higher"
        // (sslversion=4).  Some SIM7600E-H firmware revisions have a bug
        // where TLS 1.3 negotiation fails silently and the modem falls back
        // to a plain TCP connection instead of returning an error.  Restricting
        // to TLS 1.2 avoids this regression; hooks.nabu.casa (AWS ALB) fully
        // supports TLS 1.2.
        sprintf(m_buffer, "AT+CSSLCFG=\"sslversion\",%d,3\r", ctx);
        sendCommand(m_buffer);
        sprintf(m_buffer, "AT+CSSLCFG=\"authmode\",%d,0\r", ctx);
        sendCommand(m_buffer);
        sprintf(m_buffer, "AT+CSSLCFG=\"ignorertctime\",%d,1\r", ctx);
        sendCommand(m_buffer);
        sprintf(m_buffer, "AT+CSSLCFG=\"alpnprotocol\",%d,\"http/1.1\"\r", ctx);
        sendCommand(m_buffer);
      }
    };
    applySslCfg();
    if (!sendCommand("AT+CCHSTART\r")) {
      Serial.print("[CELL] CCHSTART failed:");
      Serial.println(m_buffer);
      m_state = HTTP_ERROR;
      return;
    }
    // Enable proactive +CCHRECV: <session>,<len> URCs when data arrives on any
    // session.  Without this (CCHRECVMODE=0, the modem default), the modem
    // never sends the URC and receive() would have to rely solely on the
    // +CCH_PEER_CLOSED: URC to know that data is available — a race-prone path.
    // With CCHRECVMODE=1 the receive() URC wait resolves immediately when the
    // server response arrives, regardless of whether the connection is kept
    // alive or closed.  If this firmware revision does not support the command
    // it returns ERROR, which is silently ignored; the race-condition fix in
    // receive() below serves as belt-and-suspenders in that case.
    sendCommand("AT+CCHRECVMODE=1\r");
    applySslCfg();
  } else if (m_type != CELL_SIM7070) {
    sendCommand("AT+CHTTPSSTOP\r");
    sendCommand("AT+CHTTPSSTART\r");
  }
}

bool CellHTTP::open(const char* host, uint16_t port)
{
  if (m_type == CELL_SIM7070) {
    sendCommand("AT+CNACT=0,1\r");
    sendCommand("AT+CACID=0\r");

    bool useSSL = (port == 443);
    if (useSSL) {
      sendCommand("AT+SHSSL=1,\"\"\r");
      sendCommand("AT+CSSLCFG=\"ignorertctime\",1,1\r");    
      sendCommand("AT+CSSLCFG=\"SSLVERSION\",1,3\r");
      sprintf(m_buffer, "AT+CSSLCFG=\"sni\",1,\"%s\"\r", host);
      sendCommand(m_buffer);
    }

    sprintf(m_buffer, "AT+SHCONF=\"URL\",\"%s://%s:%u\"\r", useSSL ? "https" : "http", host, port);
    if (!sendCommand(m_buffer)) {
      return false;
    }
    sendCommand("AT+SHCONF=\"HEADERLEN\",256\r");
    sendCommand("AT+SHCONF=\"BODYLEN\",1024\r");
    sendCommand("AT+SHCONN\r", HTTP_CONN_TIMEOUT);
    if (sendCommand("AT+SHSTATE?\r")) {
      if (strstr(m_buffer, "+SHSTATE: 1")) {
        m_state = HTTP_CONNECTED;
        m_host = host;
        sendCommand("AT+SHCHEAD\r");
        sendCommand("AT+SHAHEAD=\"User-Agent\",\"curl/7.47.0\"\r"); 
        sendCommand("AT+SHAHEAD=\"Cache-control\",\"no-cache\"\r");
        sendCommand("AT+SHAHEAD=\"Connection\",\"keep-alive\"\r");
        sendCommand("AT+SHAHEAD=\"Accept\",\"*/*\"\r");
        m_state = HTTP_CONNECTED;
        return true;
      }
    }
  } else if (m_type == CELL_SIM7670) {
    sendCommand("AT+HTTPINIT\r");
    sendCommand("AT+HTTPPARA=\"SSLCFG\",0\r");
    return true;
  } else if (m_type == CELL_SIM7600) {
    // AT+CCHOPEN uses SSL context 0 or 1 configured by init() (authmode=0,
    // sslversion=3, ignorertctime=1, alpnprotocol="http/1.1").
    // client_type=2 → SSL client; session ID 0 is used throughout.
    memset(m_buffer, 0, RECV_BUF_SIZE);
    Serial.printf("[CELL] Connecting to %s:%u\n", host, port);
    // Flush stale UART bytes accumulated since init() — in particular async
    // +CCHCLOSE: URCs generated by AT+CCHSTOP.  Without this purge those
    // URCs can end up in the +CCHOPEN: receive window and trigger inbound()
    // to set m_state=HTTP_DISCONNECTED before we can inspect the TLS result.
    m_device->xbPurge();
    // Set SNI (Server Name Indication) for SSL contexts 0 and 1 before
    // connecting.  Unlike AT+CHTTPSOPSE (which derives SNI from the URL
    // parameter), AT+CCHOPEN is a raw SSL socket and does NOT automatically
    // set SNI from its hostname argument on all SIM7600E-H firmware revisions.
    // Without SNI, Cloudflare / nabu.casa cannot route the TLS connection to
    // the correct origin server and closes it immediately after the handshake —
    // the +CCH_PEER_CLOSED: URC then arrives before send() can transmit.
    // Both SSL context 0 and 1 are configured because some SIM7600E-H firmware
    // versions map AT+CCHOPEN session 0 to SSL context 1 instead of context 0.
    // (SIM7070 already sets SNI explicitly; see its open() branch above.)
    sprintf(m_buffer, "AT+CSSLCFG=\"sni\",0,\"%s\"\r", host);
    sendCommand(m_buffer);
    sprintf(m_buffer, "AT+CSSLCFG=\"sni\",1,\"%s\"\r", host);
    sendCommand(m_buffer);
    // Use AT+CCHOPEN with client_type=2 (SSL client) and explicit ssl_ctx_id to
    // ensure a TLS connection that uses the SSL context configured above by
    // AT+CSSLCFG.  client_type=1 is plain TCP: despite older comments calling it
    // "SSL", the SIMCom AT-command manual (SIM7500/SIM7600/SIM7800 V3.00, ch.
    // 10.2) and the SSL Application Note document that SSL client = type 2.
    // Using type 1 caused every POST to arrive at the server as cleartext, which
    // responded with "400 The plain HTTP request was sent to HTTPS port".
    //
    // Try order:
    //   1. client_type=2, ssl_ctx_id=0 (preferred; explicit SSL on context 0)
    //   2. client_type=2, ssl_ctx_id=1 (some firmware map session 0 → context 1)
    // The 4-param form (no explicit ssl_ctx_id) has been removed because it
    // silently falls back to plain TCP on some SIM7600E-H firmware revisions
    // and was the primary cause of "400 plain HTTP to HTTPS port" errors.
    //
    // IMPORTANT: cchOpenStart is reset just before each individual AT+CCHOPEN
    // command so that handshakeMs measures only the time for THAT attempt.
    // Recording it once before all attempts caused a timing-mask bug:
    // each failed attempt adds up to 1 second of delay, so even a near-instant
    // plain-TCP response on the fallback appeared to take > MIN_TLS_HANDSHAKE_MS.
    bool cchOpenOk = false;
    // Attempt 1: 5-param with client_type=2 (SSL client), ssl_ctx_id=0.
    // client_type=2 is the SSL/TLS client mode on SIM7600.  Using client_type=1
    // opens a plain-TCP connection, causing the server to see unencrypted HTTP
    // on port 443 and respond with "400 The plain HTTP request was sent to HTTPS
    // port".  The SIMCom AT-command manual (SIM7500/SIM7600/SIM7800, ch. 10.2)
    // and the SSL Application Note confirm that SSL client = type 2.
    sprintf(m_buffer, "AT+CCHOPEN=0,\"%s\",%u,2,0\r", host, port);
    uint32_t cchOpenStart = millis();
    cchOpenOk = sendCommand(m_buffer, 1000);
    if (!cchOpenOk) {
      // Attempt 2: 5-param with client_type=2 (SSL client), ssl_ctx_id=1.
      // Some SIM7600E-H firmware revisions internally map CCH session 0 to
      // SSL context 1 rather than context 0; the explicit ctx_id=1 binding
      // forces use of the correctly configured context on those revisions.
      sprintf(m_buffer, "AT+CCHOPEN=0,\"%s\",%u,2,1\r", host, port);
      cchOpenStart = millis();
      cchOpenOk = sendCommand(m_buffer, 1000);
    }
    if (!cchOpenOk) {
      // Both 5-param forms failed — firmware does not support CCHOPEN or the
      // SSL context is not ready.  Abort rather than risking a plain-TCP session.
      Serial.println(m_buffer);
      m_state = HTTP_ERROR;
      return false;
    }
    // Reset m_state AFTER consuming the CCHOPEN OK response (which may have
    // carried late-arriving stale URCs into inbound()).  From this point on,
    // only URCs belonging to the new TLS session should influence the
    // connected/disconnected verdict.
    m_state = HTTP_CONNECTED;
    if (sendCommand(0, HTTP_TLS_HANDSHAKE_TIMEOUT, "+CCHOPEN:")) {
      // +CCHOPEN: <sessionid>,<error>  (error=0 → success)
      char *p = strstr(m_buffer, "+CCHOPEN:");
      if (p) {
        char *comma = strchr(p, ',');
        int err = comma ? atoi(comma + 1) : -1;
        if (err == 0) {
          // Timing diagnostic: a TLS 1.2 handshake with a remote server
          // (TCP 3-way + TLS exchange) takes at least a few hundred ms on
          // cellular links.  cchOpenStart was reset to millis() immediately
          // before the successful AT+CCHOPEN command, so handshakeMs reflects
          // only that specific attempt (not the accumulated delay of earlier
          // failed attempts which could mask a near-instant plain-TCP response).
          // A fast response (below MIN_TLS_HANDSHAKE_MS) means
          // plain TCP is almost certain (known SIM7600E-H firmware bug):
          // reject the session outright to prevent cleartext HTTP reaching
          // port 443.  Proceeding with a suspected plain-TCP session causes
          // "400 The plain HTTP request was sent to HTTPS port" on every POST;
          // rejecting here lets the caller's retry loop call cell.init() +
          // cell.open() again, which re-applies SSL context configuration.
          uint32_t handshakeMs = millis() - cchOpenStart;
          if (handshakeMs < MIN_TLS_HANDSHAKE_MS) {
            // Too-fast response = plain TCP suspected.
            Serial.printf("[CELL] ERR: +CCHOPEN in %ums – plain TCP suspected, rejecting\n",
                          handshakeMs);
            sendCommand("AT+CCHCLOSE=0\r", 1000, "+CCHCLOSE:");
            m_state = HTTP_DISCONNECTED;
            return false;
          } else {
            Serial.printf("[CELL] TLS handshake: %ums\n", handshakeMs);
          }
          m_host = host;
          // m_state was set to HTTP_CONNECTED above; inbound() will have
          // changed it to HTTP_DISCONNECTED if +CCH_PEER_CLOSED: or
          // +CCHCLOSE: arrived in the same buffer as +CCHOPEN:0,0.
          // The 500 ms drain below catches any close URC that arrives
          // shortly after the handshake completes (e.g. if ALPN is
          // unexpectedly negotiated as h2 and the peer sends GOAWAY).
          sendCommand(0, 500);  // drain UART; inbound() watches for +CCHCLOSE/+CCH_PEER_CLOSED
          if (m_state != HTTP_CONNECTED) {
            Serial.println("[CELL] Session closed immediately after TLS");
            return false;
          }
          // Diagnostic: query CCH session status to verify the SSL context is
          // active on the modem side.  Not all SIM7600E-H firmware revisions
          // support AT+CCHSTATUS? — an ERROR response is harmless and logged.
          if (cellNetDebug) {
            if (sendCommand("AT+CCHSTATUS?\r", 500)) {
              Serial.print("[CELL] CCHSTATUS: ");
              Serial.println(m_buffer);
            }
          }
          return true;
        }
        Serial.print("[CELL] TLS error:");
        Serial.println(err);
      }
    }
  } else {
    // SIM5360 legacy: use AT+CHTTPS* HTTPS stack
    memset(m_buffer, 0, RECV_BUF_SIZE);
    Serial.printf("[CELL] Connecting to %s:%u\n", host, port);
    sprintf(m_buffer, "AT+CHTTPSOPSE=\"%s\",%u,%u\r", host, port, port == 443 ? 1 : 0);
    if (sendCommand(m_buffer, 1000)) {
      if (sendCommand(0, HTTP_TLS_HANDSHAKE_TIMEOUT, "+CHTTPSOPSE:")) {
        char *p = strstr(m_buffer, "+CHTTPSOPSE:");
        if (p) {
          char *comma = strchr(p, ',');
          int err;
          if (comma) {
            err = atoi(comma + 1);
          } else {
            err = atoi(p + strlen("+CHTTPSOPSE:"));
          }
          if (err == 0) {
            m_state = HTTP_CONNECTED;
            m_host = host;
            sendCommand(0, 100);  // drain UART; inbound() watches for close
            if (m_state != HTTP_CONNECTED) {
              Serial.println("[CELL] Session closed immediately after TLS");
              return false;
            }
            return true;
          }
          Serial.print("[CELL] TLS error:");
          Serial.println(err);
        }
      }
    }
  }
  Serial.println(m_buffer);
  m_state = HTTP_ERROR;
  return false;
}

bool CellHTTP::close()
{
  m_state = HTTP_DISCONNECTED;
  if (m_type == CELL_SIM7070) {
    return sendCommand("AT+SHDISC\r");
  } else if (m_type == CELL_SIM5360) {
    return sendCommand("AT+CHTTPSCLSE\r", 1000, "+CHTTPSCLSE:");
  } else if (m_type == CELL_SIM7670) {
    return sendCommand("AT+HTTPTERM\r");
  } else {
    // SIM7600: close raw SSL session
    return sendCommand("AT+CCHCLOSE=0\r", 1000, "+CCHCLOSE:");
  }
}

void CellHTTP::inbound()
{
  // Handle base-class URCs (incoming data, GPS position updates, etc.).
  CellSIMCOM::inbound();
  // Detect unsolicited close URCs: +CHTTPSCLSE/+CHTTPS_PEER_CLOSED (SIM5360
  // legacy HTTPS stack), +CCHCLOSE (SIM7600 session closed locally or via
  // AT+CCHCLOSE), or +CCH_PEER_CLOSED (SIM7600 server-initiated close).
  // +CCH_PEER_CLOSED is distinct from +CCHCLOSE: it fires when the remote peer
  // sends a TCP/TLS FIN (e.g. nabu.casa closes after sending the HTTP 200).
  // All must set m_state = HTTP_DISCONNECTED so that transmit()'s guard
  // triggers a proper reconnect (or a direct AT+CCHRECV read) before the
  // next send attempt.
  if (m_buffer && (strstr(m_buffer, "+CHTTPSCLSE") || strstr(m_buffer, "+CHTTPS_PEER_CLOSED") ||
                   strstr(m_buffer, "+CCHCLOSE:") || strstr(m_buffer, "+CCH_PEER_CLOSED:"))) {
    m_state = HTTP_DISCONNECTED;
  }
}

bool CellHTTP::send(HTTP_METHOD method, const char* host, uint16_t port, const char* path, const char* payload, int payloadSize)
{
  if (m_type == CELL_SIM7070) {
    if (method == METHOD_POST) {
      sprintf(m_buffer, "AT+SHBOD=%u,1000\r", payloadSize);
      if (sendCommand(m_buffer, 1000, "\r\n>")) {
        sendCommand(payload);
      }
    }
    snprintf(m_buffer, RECV_BUF_SIZE, "AT+SHREQ=\"%s\",%u\r", path, method == METHOD_GET ? 1 : 3);
    if (sendCommand(m_buffer, HTTP_CONN_TIMEOUT)) {
      char *p;
      int len = 0;
      if (strstr(m_buffer, "+SHREQ:") || sendCommand(0, HTTP_CONN_TIMEOUT, "+SHREQ:")) {
        if ((p = strstr(m_buffer, "+SHREQ:")) && (p = strchr(p, ','))) {
          m_code = atoi(++p);
          if ((p = strchr(p, ','))) len = atoi(++p);
        }
      }
      if (len > 0) {
        if (len > RECV_BUF_SIZE - 16) len = RECV_BUF_SIZE - 16;
        sprintf(m_buffer, "AT+SHREAD=0,%u\r", len);
        if (sendCommand(m_buffer)) {
          m_state = HTTP_SENT;
          return true;
        }
      }
    }
  } else if (m_type == CELL_SIM7670) {
    sprintf(m_buffer, "AT+HTTPPARA=\"URL\",\"https://%s:%u%s\"\r", host, port, path);
    if (sendCommand(m_buffer, 1000)) {
      if (payload) {
        sprintf(m_buffer, "AT+HTTPDATA=%u,1000\r", payloadSize);
        sendCommand(m_buffer, 1000, "DOWNLOAD\r");
        m_device->xbWrite(payload, payloadSize);
        sendCommand("AT+HTTPACTION=1\r");
      } else {
        sendCommand("AT+HTTPACTION=0\r");
      }
    }
    return true;
  } else if (m_type == CELL_SIM7600) {
    // Drain any pending URCs before sending — catches a +CCHCLOSE that
    // arrived in the UART buffer between open() and now.
    sendCommand(0, 50);
    if (m_state != HTTP_CONNECTED) {
      Serial.println("[CELL] Send aborted: connection closed");
      return false;
    }
    // SIM7600 raw SSL socket: send via AT+CCHSEND
    String header = genHeader(method, path, payload, payloadSize);
    // TX diagnostic: show the outgoing HTTP header up to (and including) the
    // blank-line separator (\r\n\r\n) so we can verify the request line, Host:,
    // and all other headers before the bytes reach the modem.  Fall back to the
    // first 512 chars if the separator is not found.
    if (cellNetDebug) {
      int headerEnd = header.indexOf("\r\n\r\n");
      const int previewLength = (headerEnd >= 0)
          ? min(headerEnd + 4, (int)header.length())
          : min(512, (int)header.length());
      Serial.print("[CELL] TX-Preview: ");
      Serial.write(header.c_str(), previewLength);
      Serial.println();
      Serial.print("[CELL] TX-First64(hex):");
      for (int i = 0; i < min(64, (int)header.length()); i++) {
        char hexBuf[4]; sprintf(hexBuf, " %02X", (unsigned char)header[i]); Serial.print(hexBuf);
      }
      Serial.println();
    }
    int len = header.length();
    sprintf(m_buffer, "AT+CCHSEND=0,%u\r", len + payloadSize);
    if (!sendCommand(m_buffer, 1000, ">")) {
      Serial.print("[CELL] Send failed:");
      Serial.println(m_buffer);
      m_state = HTTP_DISCONNECTED;
      return false;
    }
    // send HTTP header
    m_device->xbWrite(header.c_str());
    // send POST payload if any
    if (payload) m_device->xbWrite(payload, payloadSize);
    // Some SIM7600E-H firmware versions return only OK on a successful send
    // without generating a +CCHSEND: 0,0 completion URC.  Use the default
    // OK/ERROR termination and treat absence of a non-zero +CCHSEND: error
    // code as success.  +CCHSEND: 0,N with N > 0 always indicates failure.
    // If the remote peer closed the connection simultaneously (e.g. nabu.casa
    // sends HTTP 200 then TCP FIN), inbound() will have set m_state to
    // HTTP_DISCONNECTED; we preserve that so receive() can try a direct
    // AT+CCHRECV read instead of waiting for a +CCHRECV URC that won't come.
    if (sendCommand(0, HTTP_CONN_TIMEOUT)) {
      bool sendErr = false;
      char *cs = strstr(m_buffer, "+CCHSEND:");
      if (cs) {
        char *comma = strchr(cs, ',');
        sendErr = !comma || atoi(comma + 1) != 0;
      }
      if (!sendErr) {
        if (m_state != HTTP_DISCONNECTED) m_state = HTTP_SENT;
        return true;
      }
    }
  } else {
    // SIM5360 (legacy, no connection ID prefix)
    String header = genHeader(method, path, payload, payloadSize);
    int len = header.length();
    sprintf(m_buffer, "AT+CHTTPSSEND=%u\r", len + payloadSize);
    if (!sendCommand(m_buffer, 100, ">")) {
      m_state = HTTP_DISCONNECTED;
      return false;
    }
    // send HTTP header
    m_device->xbWrite(header.c_str());
    // send POST payload if any
    if (payload) m_device->xbWrite(payload, payloadSize);
    if (sendCommand(0, 200, "+CHTTPSSEND:")) {
      m_state = HTTP_SENT;
      return true;
    }
  }
  Serial.println(m_buffer);
  m_state = HTTP_ERROR;
  return false;
}

char* CellHTTP::receive(int* pbytes, unsigned int timeout)
{
  if (m_type == CELL_SIM7070) {
    if (!m_incoming && timeout) sendCommand(0, timeout, "+SHREAD:");
    if (!m_incoming) return 0;

    m_incoming = 0;
    m_state = HTTP_CONNECTED;

    char *p = strstr(m_buffer, "+SHREAD:");
    if (p) {
      int bytes = atoi(p += 9);
      if (pbytes) *pbytes = bytes;
      p = strchr(p, '\n');
      if (p++) {
        *(p + bytes) = 0;
        return p;
      }
    }
  } else if (m_type == CELL_SIM7670) {
    if (sendCommand("AT+HTTPHEAD\r", timeout, "+HTTPHEAD:")) {
      char *p = strstr(m_buffer, "HTTP/1.");
      if (p) m_code = atoi(p + 9);
    }
    sprintf(m_buffer, "AT+HTTPREAD=0,%u\r", RECV_BUF_SIZE - 32);
    sendCommand(m_buffer);
    char *p = strstr(m_buffer, "+HTTPREAD:");
    if (p) {
      m_state = HTTP_CONNECTED;
      int bytes = atoi(p + 11);
      if (pbytes) *pbytes = bytes;
      p = strchr(p, '\n');
      if (p) {
        p++;
        if (bytes < RECV_BUF_SIZE - 32) *(p + bytes) = 0;
        return p;
      }
    }
  } else if (m_type == CELL_SIM7600) {
    // SIM7600: use AT+CCH raw SSL socket receive
    int received = 0;
    char* payload = 0;
    bool keepalive;

    // In CCHRECVMODE=0 (the default when AT+CCHRECVMODE=1 is unsupported by the
    // modem firmware), the modem autonomously pushes received data to the UART
    // as "+CCHRECV: DATA,<session>,<len>\r\n<data>" without waiting for an
    // explicit AT+CCHRECV command.  This push may already have been captured
    // into m_buffer by send()'s AT+CCHSEND acknowledgement wait.  Check for it
    // here — before the URC wait below resets m_buffer — so the data is not
    // discarded.
    char *p = strstr(m_buffer, "+CCHRECV: DATA,");
    if (!p) p = strstr(m_buffer, "+CCHRECV:DATA,");

    if (!p) {
      // Data not yet in m_buffer; enter the URC / AT+CCHRECV read path.
      //
      // Wait for +CCHRECV: <session>,<len> URC (data available on session 0).
      // Skip the wait when the peer already closed the connection (m_state ==
      // HTTP_DISCONNECTED, set by inbound() on +CCH_PEER_CLOSED:): in that case
      // the server response is buffered in the modem and readable via a direct
      // AT+CCHRECV without waiting for a URC that will never arrive separately.
      //
      // Race-condition fix: +CCH_PEER_CLOSED: can arrive DURING the wait below,
      // causing inbound() to set m_state = HTTP_DISCONNECTED.  Without this fix
      // the old "if (!m_incoming) return 0" would return null even though data is
      // still buffered in the modem.  Re-checking m_state after the wait ensures
      // we fall through to AT+CCHRECV whenever the peer closed (with or without a
      // prior +CCHRECV: URC, i.e. regardless of AT+CCHRECVMODE setting).
      if (m_state != HTTP_DISCONNECTED) {
        if (!m_incoming && timeout) sendCommand(0, timeout, "+CCHRECV:");
        if (!m_incoming && m_state != HTTP_DISCONNECTED) return 0;
      }
      m_incoming = 0;

      // Re-check m_buffer after the URC wait: in CCHRECVMODE=0, the wait may
      // have read the autonomous data push from the UART (e.g. the modem sent
      // "+CCHRECV: DATA,0,N\r\n<data>\r\n+CCH_PEER_CLOSED: 0\r\n" in a single
      // UART read).  inbound() sets m_state=HTTP_DISCONNECTED from the peer-
      // closed URC but m_incoming stays 0 because "+CCHRECV: DATA,0," does not
      // match the "+CCHRECV: 0," pattern that inbound() checks.  Once pushed,
      // that data is gone from the modem — issuing AT+CCHRECV=0,N would return
      // 0 bytes — so parse m_buffer directly when the pattern is found here.
      p = strstr(m_buffer, "+CCHRECV: DATA,");
      if (!p) p = strstr(m_buffer, "+CCHRECV:DATA,");
      if (!p) {
        // Data still not in m_buffer; issue AT+CCHRECV to drain it from the
        // modem's internal buffer (normal path when CCHRECVMODE=1 is active:
        // +CCHRECV: 0,N URC set m_incoming; or when only +CCH_PEER_CLOSED:
        // arrived and response data is still in the modem's CCH session buffer).
        // Read the data: +CCHRECV: DATA,<session>,<len>\r\n<data>\r\n+CCHRECV: 0\r\nOK
        // Use default OK/ERROR termination to tolerate firmware variants
        // that may omit a space in the +CCHRECV: 0 end marker.
        sprintf(m_buffer, "AT+CCHRECV=0,%u\r", RECV_BUF_SIZE - 32);
        sendCommand(m_buffer, timeout);
        p = strstr(m_buffer, "\r\n+CCHRECV: DATA");
        if (!p) p = strstr(m_buffer, "\r\n+CCHRECV:DATA");  // no-space firmware variant
      }
    } else {
      m_incoming = 0;
    }
    if (p) {
      if ((p = strchr(p, ','))) {
        // Format is always "+CCHRECV: DATA,<session>,<len>"; skip session ID
        // and read length from the second comma only.
        char *eol = strchr(p, '\n');
        char *q = strchr(p + 1, ',');
        if (q && eol && q < eol) {
          received = atoi(q + 1);
          payload = eol + 1;
          if (m_buffer + RECV_BUF_SIZE - payload > received) {
            payload[received] = 0;
          }
        }
      }
    }
    if (received == 0) {
      m_state = HTTP_ERROR;
      return 0;
    }

    char *ps = strstr(payload, "/1.1 ");
    if (!ps) ps = strstr(payload, "/1.0 ");
    if (ps) m_code = atoi(ps + 5);
    keepalive = strstr(m_buffer, ": close\r\n") == 0;

    m_state = HTTP_CONNECTED;
    if (!keepalive) close();
    if (pbytes) *pbytes = received;
    return payload;
  } else {
    // SIM5360 legacy: use AT+CHTTPSRECV
    int received = 0;
    char* payload = 0;
    bool keepalive;

    if (!m_incoming && timeout) sendCommand(0, timeout, "RECV EVENT");
    if (!m_incoming) return 0;
    m_incoming = 0;

    // to be compatible with SIM5360
    bool legacy = false;
    char *p = strstr(m_buffer, "RECV EVENT");
    if (p && *(p - 1) == ' ') legacy = true;

    /*
      +CHTTPSRECV:XX\r\n
      [payload]\r\n
      +CHTTPSRECV:0\r\n
    */
    // TODO: implement for multiple chunks of data
    // only process first chunk now
    sprintf(m_buffer, "AT+CHTTPSRECV=%u\r", RECV_BUF_SIZE - 32);
    if (sendCommand(m_buffer, timeout, legacy ? "\r\n+CHTTPSRECV: 0" : "\r\n+CHTTPSRECV:0")) {
      char *p = strstr(m_buffer, "\r\n+CHTTPSRECV: DATA");
      if (p) {
        if ((p = strchr(p, ','))) {
          received = atoi(p + 1);
          char *eol = strchr(p, '\n');
          char *q = strchr(p + 1, ',');
          if (q && eol && q < eol) {
            received = atoi(q + 1);
          }
          payload = eol ? (eol + 1) : p;
          if (m_buffer + RECV_BUF_SIZE - payload > received) {
            payload[received] = 0;
          }
        }
      }
    }
    if (received == 0) {
      m_state = HTTP_ERROR;
      return 0;
    }

    p = strstr(payload, "/1.1 ");
    if (!p) p = strstr(payload, "/1.0 ");
    if (p) {
      m_code = atoi(p + 5);
    }
    keepalive = strstr(m_buffer, ": close\r\n") == 0;

    m_state = HTTP_CONNECTED;
    if (!keepalive) close();
    if (pbytes) *pbytes = received;
    return payload;
  }
  return 0;
}
