# Rollback-Dokumentation: Änderungen seit v0.1.15

Diese Datei dokumentiert alle Änderungen, die seit dem Release **v0.1.15** im Repository vorgenommen wurden, bevor ein Rollback auf diesen Stand durchgeführt wurde.

---

## Übersicht

| Version | Datum | Schwerpunkt |
|---------|-------|-------------|
| v0.1.16 | 2026-03-14 | OTA NVS-Datenverlust-Fix |
| v0.1.17 | 2026-03-14 | OTA-Check-Timing-Fix |
| v0.1.18 | 2026-03-14 | Cellular OTA via hooks.nabu.casa |
| v0.1.19 | 2026-03-14 | OTA-Token-Provisionierung |
| v0.1.20 | 2026-03-14 | LED/Beep IST-Status-Persistenz |
| v0.1.21 | 2026-03-15 | Telemetrie-Cloud-Hook-Fixes |
| v0.1.22 | 2026-03-15 | CELL_DL_TEST, SHA256-Verifikation, IST-PIDs |
| v0.1.23 | 2026-03-15 | OTA-Token nach Serial-Flash, IST-PIDs cellular |
| v0.1.24 | 2026-03-15 | SIM7600E-H TLS-Fehler 15, staler OTA-Token |
| v0.1.25 | 2026-03-15 | Cellular OTA-Ausgabe, printOtaStatus(), HTTPD-Ausgabe |
| v0.1.26 | 2026-03-15 | OTA nur noch per WiFi (cellular OTA entfernt) |
| v0.1.27 | 2026-03-15 | Cellular OTA GET-Überreste entfernt |
| v0.1.28 | 2026-03-16 | (Keine eigenständigen Commits – Sync-Release) |
| v0.1.29 | 2026-03-16 | Cellular Telemetrie, CellDlTestButton entfernt |
| v0.1.30 | 2026-03-16 | OTA-Token Ausgabe, nvs_version-Fix, OTA-Confirm-Endpoint |
| v0.1.31 | 2026-03-16 | SSL-Heap-Erschöpfung in WifiHTTP::open() |
| v0.1.32 | 2026-03-16 | WiFi SSL-Heap: eager TLS-Teardown verhindert |
| v0.1.33 | 2026-03-16 | WiFi TLS-Heap-Fragmentierung (MBEDTLS_ERR_SSL_ALLOC_FAILED) |
| v0.1.34 | 2026-03-16 | OTA-Heap-Fragmentierung: TLS-Session vor OTA-Check schließen |
| v0.1.35 | 2026-03-16 | WiFi Low Heap: OTA-TLS früh schließen, TLS_MIN_FREE_HEAP=36KB |

---

## Detaillierte Änderungen pro Version

### v0.1.16 — OTA NVS-Datenverlust-Fix
**PR #121** | Commit `753343e`

**Geänderte Dateien:**
- `custom_components/freematics/views.py`
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: Datenverlust in `_applyNvsFromSD()` beim Schreiben von NVS-Daten aus SD-Karte
- OTA-Token Safety-Net: Token wird gesichert, bevor er überschrieben werden kann

---

### v0.1.17 — OTA-Check-Timing-Fix
**PR #122** | Commit `4b024d7`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: OTA-Check wird jetzt **vor** dem `continue` bei leerem Buffer ausgeführt, damit er auch bei inaktivem OBD2/GPS läuft

---

### v0.1.18 — Cellular OTA via hooks.nabu.casa
**PR #123** | Commit `2a36074`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: Cellular OTA Meta-Check wird jetzt über den `hooks.nabu.casa`-Webhook auf dem SIM7600E-H geleitet

---

### v0.1.19 — OTA-Token-Provisionierung
**PR #124** | Commit `2d0ba7a`

**Geänderte Dateien:**
- `custom_components/freematics/views.py`
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: `OTA_TOKEN`, `OTA_HOST` und `OTA_INTERVAL` werden jetzt korrekt an `handlerControl` und `SendConfigButton` übermittelt

---

### v0.1.20 — LED/Beep IST-Status-Persistenz & OTA NVS-Retry
**PR #125** | Commit `45452af`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/views.py`

**Inhalt:**
- Fix: LED/Beep IST-Status-Persistenz über Verbindungsunterbrechungen hinweg
- Fix: OTA NVS-Retry-Mechanismus verbessert

---

### v0.1.21 — Telemetrie-Cloud-Hook-Fixes
**PR #126** | Commit `bff28eb`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/__init__.py`
- `custom_components/freematics/const.py`

**Inhalt:**
- Fix: LED/Beep IST-Status-Verfolgung in Cloud-Hook-Telemetrie
- Fix: SD-Karten-Status (`PID_SD_TOTAL_MB=0x86`, `PID_SD_FREE_MB=0x87`) in Telemetrie
- Fix: Cellular OTA Download über Cloud-Hook

---

### v0.1.22 — CELL_DL_TEST, SHA256-Verifikation, IST-PIDs
**PR #127** | Commits `ef7a087`, `49d6717`, `c357709`, `6c6776e`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `firmware_v5/telelogger/dataserver.cpp`
- `custom_components/freematics/__init__.py`
- `custom_components/freematics/button.py`
- `libraries/FreematicsPlus/FreematicsBase.h`

**Inhalt:**
- Neu: `CELL_DL_TEST`-Kommando — Download-Test für cellular Binary via `hooks.nabu.casa`
- Neu: Streaming-SHA256-Verifikation für OTA-Firmware-Downloads (WiFi + Cellular)
- Fix: Cellular Telemetrie IST-Attribute, LTE-Verfolgung (`PID_CONN_TYPE=0x88`)
- Fix: OTA-Pause nach SD-Staging (`s_ota_pending=true`)
- Fix: Linker-Fehler durch `static` bei `s_cell_dl_test_request` entfernt
- Neu: PIDs `PID_SD_TOTAL_MB=0x86`, `PID_SD_FREE_MB=0x87` in `FreematicsBase.h`
- Neu: `PID_CONN_TYPE=0x88` (1=WiFi, 2=Cellular) in `FreematicsBase.h`

---

### v0.1.23 — OTA-Token nach Serial-Flash, IST-PIDs cellular
**PR #129** | Commits `d1dfb6e`, `a5eeeee`, `648d049`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/views.py`

**Inhalt:**
- Fix: OTA-Token wird nach Serial-Flash korrekt gesetzt
- Fix: Cell-DL-Test wird nach Serial-Flash automatisch ausgelöst
- Fix: Serial-Flash wird abgebrochen, wenn OTA aktiv ist und NVS-Generierung fehlschlägt
- Fix: IST-Status-PIDs (`0x84`–`0x88`) werden garantiert im ersten cellular Paket gesendet (`s_send_state_pids`-Flag)

---

### v0.1.24 — SIM7600E-H TLS-Fehler 15
**PR #130** | Commits `c97f40d`, `0666e55`

**Geänderte Dateien:**
- `libraries/FreematicsPlus/FreematicsNetwork.cpp`
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/__init__.py`

**Inhalt:**
- Fix: TLS-Fehler 15 auf SIM7600E-H mit `*.ui.nabu.casa` (Cloudflare) durch Einschränkung auf ECDHE-RSA-Cipher (`C02FC030`)
- Fix: Staler OTA-Token im Webhook-Closure durch `_live_ota_token()`-Helper
- Fix: Cellular OTA nutzt jetzt POST via `hooks.nabu.casa`

---

### v0.1.25 — Cellular OTA-Ausgabe, printOtaStatus(), HTTPD-Ausgabe
**PR #131** | Commits `05c60f7`, `dc5ae37`, `fd9c674`, `5e69bbe`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: Cellular OTA TLS-Fehler 15 — `hooks.nabu.casa` Webhook bevorzugt gegenüber direktem `*.ui.nabu.casa`
- Neu: `printOtaStatus()`-Hilfsfunktion — gibt ersten 8 Hex-Zeichen des Tokens + `...` aus
- Fix: OTA-Status bei `interval=0` zeigt `(checks disabled)`-Suffix
- Fix: HTTPD-IP wird auf derselben Zeile wie das Label ausgegeben

---

### v0.1.26 — OTA nur noch per WiFi (cellular OTA entfernt)
**PR #133** | Commits `e090f97`, `06e97f4`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/views.py`
- `custom_components/freematics/firmware/README.md` (neu)

**Inhalt:**
- Feature: OTA-Funktionalität in cellular-Modus entfernt — OTA nur noch über WiFi
- Dokumentation: WiFi-only OTA README erstellt
- Fix: Fehlender `_ota_meta_url`-Parameter in `views.py`
- Fix: `last_packet_time` wird im Fehlerpfad aktualisiert

---

### v0.1.27 — Cellular OTA GET-Überreste entfernt
**PR #134** | Commit `3bf3807`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: Verbleibende cellular OTA GET-Remnants entfernt
- Fix: Veraltete Kommentare für WiFi-only OTA aktualisiert

---

### v0.1.28 — (Sync-Release, keine eigenständigen Commits)
Reine Versionsbump-Veröffentlichung ohne neue Commits.

---

### v0.1.29 — Cellular Telemetrie, CellDlTestButton entfernt
**PR #135 / #136** | Commits `dbb3dc5`, `b4811bf`, `05f3351`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/button.py`
- `custom_components/freematics/views.py`

**Inhalt:**
- Fix: Cellular Telemetrie-Übertragung repariert
- Fix: `CellDlTestButton`-Komponente entfernt
- Fix: OTA Firmware-Download HTTP 500 (NameError) in `views.py` behoben
- Sync: Branch mit master synchronisiert

---

### v0.1.30 — OTA-Token Ausgabe, nvs_version-Fix, OTA-Confirm-Endpoint
**PR #137** | Commits `351d1c3`, `9211bda`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `custom_components/freematics/views.py`

**Inhalt:**
- Fix: OTA-Token in serieller Ausgabe wird gekürzt dargestellt (erste 8 Hex-Zeichen + `...`)
- Fix: Vorzeitiges Schreiben von `nvs_version` in `nvs.bin` verhindert
- Neu: OTA-Confirm-Endpoint (`GET /api/freematics/ota_pull/{token}/ota_confirm`) — Status wird erst nach SHA256-Verifikation durch das Gerät gesetzt
- Einschränkung: OTA nur noch über WiFi

---

### v0.1.31 — SSL-Heap-Erschöpfung in WifiHTTP::open()
**PR #138** | Commit `2ad24de`

**Geänderte Dateien:**
- `libraries/FreematicsPlus/FreematicsNetwork.cpp`
- `libraries/FreematicsPlus/FreematicsNetwork.h`
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: SSL-Heap-Erschöpfung in `WifiHTTP::open()` durch mehrschichtige Heap-Fragmentierungs-Verteidigung
- Fix: NVS-Version wird korrekt in serieller Ausgabe protokolliert
- Neue Konstante: `TLS_MIN_FREE_HEAP` in `FreematicsNetwork.h`

---

### v0.1.32 — WiFi SSL-Heap: eager TLS-Teardown verhindert
**PR #139** | Commit `106e399`

**Geänderte Dateien:**
- `libraries/FreematicsPlus/FreematicsNetwork.cpp`
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: `WifiHTTP::receive()` ruft bei `Connection: close` nicht mehr `close()`/`client.stop()` auf
- Stattdessen: `m_state=HTTP_DISCONNECTED` — defer to `open()` für atomisches `stop()+connect()`
- Verhindert Heap-Fragmentierung durch eager TLS-Teardown

---

### v0.1.33 — WiFi TLS-Heap-Fragmentierung (MBEDTLS_ERR_SSL_ALLOC_FAILED)
**PR #140** | Commit `99a84e8`

**Geänderte Dateien:**
- `libraries/FreematicsPlus/FreematicsNetwork.cpp`
- `libraries/FreematicsPlus/FreematicsNetwork.h`
- `firmware_v5/telelogger/telelogger.ino`

**Inhalt:**
- Fix: `MBEDTLS_ERR_SSL_ALLOC_FAILED (-32512)` durch WiFi TLS-Heap-Fragmentierung
- Dreischichtige Verteidigung in `WifiHTTP::open()`:
  1. Socket-Wiederverwendung bei `HTTP_DISCONNECTED` + gleichem Host
  2. Guard 1: Heap-Check vor `stop()` bei Hostwechsel
  3. Guard 2: Heap-Check nach `stop()` vor `connect()`
- `TLS_MIN_FREE_HEAP` auf 40 KB gesetzt
- Sofortiges `wifi.end()+reconnect` bei Heap-Fragmentierungsfehler in Telemetrie

---

### v0.1.34 — OTA-Heap-Fragmentierung: TLS-Session vor OTA-Check schließen
**PR #141** | Commit `0314500`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `libraries/FreematicsPlus/FreematicsNetwork.h`

**Inhalt:**
- Fix: OTA-Heap-Fragmentierung durch Schließen der Telemetrie-TLS-Session vor OTA-Check
- `TLS_MIN_FREE_HEAP` auf 38 KB gesenkt

---

### v0.1.35 — WiFi Low Heap: OTA-TLS früh schließen, TLS_MIN_FREE_HEAP=36KB
**PR #142** | Commit `23b0412`

**Geänderte Dateien:**
- `firmware_v5/telelogger/telelogger.ino`
- `libraries/FreematicsPlus/FreematicsNetwork.h`

**Inhalt:**
- Fix: OTA-TLS-Session in `performPullOtaCheck()` wird direkt nach Empfang von `meta.json` geschlossen
- `TLS_MIN_FREE_HEAP` auf 36 KB gesenkt (2 KB über dem ~34 KB TLS-Minimum)

---

## Betroffene Dateien (Gesamtübersicht)

| Datei | Art der Änderung |
|-------|-----------------|
| `firmware_v5/telelogger/telelogger.ino` | Umfangreiche Änderungen (+1056/-677 Zeilen) |
| `custom_components/freematics/views.py` | Umfangreiche Änderungen (+733/-Zeilen) |
| `libraries/FreematicsPlus/FreematicsNetwork.cpp` | Erweitert (+119 Zeilen) |
| `libraries/FreematicsPlus/FreematicsNetwork.h` | Erweitert (+37 Zeilen) |
| `libraries/FreematicsPlus/FreematicsBase.h` | Erweitert (+10 Zeilen) |
| `custom_components/freematics/__init__.py` | Erweitert (+70 Zeilen) |
| `custom_components/freematics/button.py` | Neu/Erweitert (+55 Zeilen) |
| `custom_components/freematics/const.py` | Erweitert (+12 Zeilen) |
| `custom_components/freematics/manifest.json` | Version: 0.1.15 → 0.1.35 |
| `custom_components/freematics/nvs_helper.py` | Erweitert (+19 Zeilen) |
| `custom_components/freematics/firmware/README.md` | Neu (+13 Zeilen) |
| `custom_components/freematics/firmware/telelogger.bin` | Binary aktualisiert |
| `firmware_v5/telelogger/telelogger.bin` | Binary aktualisiert |
| `firmware_v5/telelogger/dataserver.cpp` | Erweitert (+46 Zeilen) |
| `firmware_v5/telelogger/README.md` | Erweitert (+15 Zeilen) |

---

## Rollback-Ziel

**Rollback auf: `v0.1.15`** (Commit `be11f16d277c2c759d16c8d7bee2deea8462faad`)

Datum des Rollbacks: 2026-03-17
