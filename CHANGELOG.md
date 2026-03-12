# Changelog – Freematics ONE+ Home Assistant Integration

All notable changes to this project are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.1.00] – 2025-03-12

### Summary

This release completes the firmware TLS reliability overhaul, adds runtime LED/buzzer
control, introduces a structured GitHub issue form, and ships a fully revised bilingual
(EN/DE) documentation with a new HowTo/FAQ section.

### ✨ New Features

#### Integration (Home Assistant)
- **LED & Buzzer control** — new options in the config/options flow to enable or disable the
  red power LED (`LED_RED_EN`), white network LED (`LED_WHITE_EN`), and in-cabin buzzer
  (`BEEP_EN`) independently. Settings are written to device NVS on the next flash.
- **Cellular debug logging flag** (`CELL_DEBUG`) — enable verbose AT-command logging at
  runtime from the HA options flow without recompiling the firmware.
- **Model H support** — Freematics ONE+ Model H can now be selected in the config flow.
- **Improved flash reliability** — `async_flash_serial()` now writes the partition table
  (`0x8000`), optional NVS (`0x9000`), and firmware (`0x10000`) in a single `esptool`
  invocation, eliminating race conditions between separate write operations.
- **Combined `flash_image.bin` starts at `0x1000`** — the downloadable image now includes
  the bootloader, partition table, NVS, and firmware merged into one file written at offset
  `0x1000`. This prevents the "flash read err, 1000" boot-loop that occurred when
  esp-web-tools erased the chip and wiped the factory bootloader.
- **GitHub issue templates** — structured bug report, flash issue, and feature request
  forms added to `.github/ISSUE_TEMPLATE/` for easier bug reporting.

#### Firmware (ESP32 / telelogger)
- **Dual-OTA partition layout** — `partitions_ota.csv` updated to support OTA partition
  slots `app0`/`app1` (each 1.94 MB) alongside NVS, otadata, and room for future
  expansion on 4 MB and 16 MB flash variants.
- **TLS detection threshold raised to 300 ms** (`MIN_TLS_HANDSHAKE_MS`) — responses to
  `AT+CCHOPEN` faster than 300 ms are now hard-rejected as plain TCP connections,
  preventing silent HTTP→HTTPS downgrade on affected SIM7600 firmware revisions.
- **`CCHOPEN` ssl_ctx_id fallback** — `CellHTTP::open()` tries `ssl_ctx_id=0` then
  `ssl_ctx_id=1` before giving up; the ambiguous 4-parameter form that caused silent
  plain-TCP fallback on some SIM7600E-H builds has been removed.
- **`CCHSTART` fatal on failure** — `CellHTTP::init()` now returns `HTTP_ERROR` immediately
  if `AT+CCHSTART` fails instead of continuing with a broken state.
- **4xx backoff** — `TeleClientHTTP::transmit()` implements exponential back-off for HTTP
  4xx responses (initial 2 s, doubling up to 64 s) to avoid hammering the server on
  misconfiguration. HTTP 400 (plain-HTTP-to-HTTPS-port) uses a fixed 2 s delay.
- **`Connection: close` header** — `HTTPClient::genHeader()` sends `Connection: close`
  (instead of `keep-alive`) and defensively strips scheme/host prefix from path arguments.
- **Token masking in serial log** — `printMaskedPath()` truncates cloud-hook paths to
  20 characters + `…` to prevent the ~170-character webhook token from appearing in full
  in serial monitor output.
- **`serverProcess(0)` in idle loop** — `/api/control?cmd=OFF` (and other HTTP commands)
  are now serviced every 100 ms during active telemetry, not only during
  `standby()`/`waitMotion()`.

### 🐛 Bug Fixes

- **Red LED stays on after serial flash** — the red LED now turns off correctly after a
  successful serial flash completes. Previously the LED remained lit because the
  post-flash GPIO reset was missing.
- **Partition table missing on fresh installs** — a generated partition table is now
  always included in the esptool invocation so first-time flashes on blank devices
  succeed without manual intervention.
- **`ets_main.c 371` boot-loop on esp-web-tools first install** — fixed by including the
  bootloader in `flash_image.bin` starting at offset `0x1000` so the bootloader is
  always restored after a chip-erase.

### 📖 Documentation

- Full bilingual (EN/DE) documentation rewrite — both sections now cover the same 7-step
  config flow, including the new **Operating Mode** and **Flash Method** steps that were
  previously missing from the German section.
- New **HowTo / FAQ** section (EN + DE) — covers the 10 most common issues with
  step-by-step solutions: TLS memory errors, no sensor data, WiFi OTA failures,
  Browser Serial issues, serial flash failures, cellular connectivity problems,
  LED/buzzer troubleshooting, CELL_DEBUG, updating firmware, and resetting to defaults.
- Corrected `flash_image.bin` offset references (`0x9000` → `0x1000`) throughout
  the German documentation section.
- Added LED/BEEP/CELL_DEBUG settings to the entity reference and config flow description.
- Added Freematics ONE+ Model H to the supported hardware list.

### 🔧 Technical / Internal

- `nvs_helper.py` generates the dual-OTA partition table used by both serial and
  Web Serial (esp-web-tools) flash paths.
- `flash_manager.py` passes the generated partition table bytes to esptool alongside
  NVS and firmware in one atomic operation.
- `views.py` provisioning token endpoint updated to include the partition table part
  in the esp-web-tools manifest for browser-based flashing.

---

## [0.0.95] and earlier

For history prior to 0.0.96, see the
[commit log](https://github.com/northpower25/Freematics/commits/master).

---

*Integration maintained by [@northpower25](https://github.com/northpower25).  
Firmware based on the [Freematics ONE+](https://freematics.com/products/freematics-one-plus/) platform by Stanley Huang.*
