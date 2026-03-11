"""HTTP views for Freematics ONE+ integration.

Serves the following endpoints:
  GET  /api/freematics/flasher          – Browser-based serial flasher (HTML)
  GET  /api/freematics/manifest.json    – esp-web-tools firmware manifest
                                          Accepts optional ?token=<tok> to return a
                                          personalised manifest with NVS settings part.
  GET  /api/freematics/firmware.bin     – Bundled pre-compiled firmware binary
  GET  /api/freematics/bootloader.bin   – Second-stage bootloader binary (offset 0x1000)
  GET  /api/freematics/config_nvs.bin   – NVS partition image with device settings
                                          Requires ?token=<tok> issued by
                                          /api/freematics/provisioning_token.
  GET  /api/freematics/flash_image.bin  – Combined single-file flash image
                                          (bootloader + partition table + NVS + firmware,
                                          written at 0x1000).
                                          Requires ?token=<tok> issued by
                                          /api/freematics/provisioning_token.
  GET  /api/freematics/provisioning_token – (auth required) Issue a short-lived token
                                          that ties the NVS / manifest endpoints to
                                          the caller's config-entry settings.
  POST /api/freematics/wifi_ota         – Server-side WiFi OTA proxy (panel → HA → device)

The flasher page uses the Web Serial API (Chrome/Edge 89+) so the user can
flash the Freematics ONE+ that is connected to *their own computer's* USB port,
regardless of where Home Assistant is hosted.

NVS provisioning flow
─────────────────────
1. Panel JS calls GET /api/freematics/provisioning_token (HA auth required).
   Response: {"token": "…", "manifest_url": "…", "nvs_url": "…",
              "flash_image_url": "…"}
2. Panel passes manifest_url to <esp-web-install-button>.
   esp-web-tools fetches the manifest and discovers the NVS part URL.
3. During flash, esp-web-tools writes bootloader.bin at 0x1000, firmware.bin
   at 0x10000, and config_nvs.bin at 0x9000 in one pass.
4. Device reboots with WiFi SSID/password, APN, and server settings
   already stored in NVS — no post-flash manual configuration needed.

For manual flashing (esptool) the panel provides a single flash_image.bin
download that contains the bootloader, partition table, NVS partition and the
firmware merged into one file.  The user flashes it at offset 0x1000 and the
device boots with the correct settings without needing to handle multiple files.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import (
    CONF_CELL_APN,
    CONF_CELL_DEBUG,
    CONF_BEEP_EN,
    CONF_CLOUD_HOOK_URL,
    CONF_DATA_INTERVAL_MS,
    CONF_DEVICE_IP,
    CONF_DEVICE_PORT,
    CONF_ENABLE_BLE,
    CONF_ENABLE_HTTPD,
    CONF_LED_RED_EN,
    CONF_LED_WHITE_EN,
    CONF_OPERATING_MODE,
    CONF_SIM_PIN,
    CONF_SYNC_INTERVAL_S,
    CONF_WEBHOOK_ID,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    DEFAULT_DEVICE_PORT,
    DOMAIN,
    OPERATING_MODE_DATALOGGER,
)

_LOGGER = logging.getLogger(__name__)

# Token time-to-live in seconds (5 minutes).  After expiry the token is
# rejected so the window during which the unprotected NVS endpoint could
# serve WiFi credentials is minimised.
_TOKEN_TTL = 300

FIRMWARE_PATH = Path(__file__).parent / "firmware" / "telelogger.bin"
BOOTLOADER_PATH = Path(__file__).parent / "firmware" / "bootloader.bin"

# esp-web-tools manifest — describes the chip family and flash offsets.
# 0x1000 = 4096   – second-stage bootloader offset (always this on ESP32).
#                   Including the bootloader is critical: esp-web-tools performs
#                   a full chip erase on the first ("new install") flash, wiping
#                   the bootloader at 0x1000.  Without it the device loops with:
#                       flash read err, 1000  /  ets_main.c 371
# 0x8000 = 32768  – partition table offset (always this address on ESP32).
# 0x10000 = 65536 – application partition offset for ESP32.
# 0x9000  = 36864 – NVS partition offset (huge_app partition scheme).
# Including the partition table ensures the device always has the correct
# huge_app partition scheme, which is required for the NVS at 0x9000 to be
# found.  Without it, devices that had a different scheme would crash.
_MANIFEST_BASE = {
    "name": "Freematics ONE+ Telelogger",
    "version": "5.0",
    "new_install_prompt_erase": False,
    "builds": [
        {
            "chipFamily": "ESP32",
            "parts": [
                {"path": "bootloader.bin", "offset": 4096},
                {"path": "partition_table.bin", "offset": 32768},
                {"path": "firmware.bin", "offset": 65536},
            ],
        }
    ],
}

_FLASHER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freematics ONE+ Browser Flasher</title>
  <script
    type="module"
    src="https://unpkg.com/esp-web-tools@10/dist/web/install-button.js?module"
  ></script>
  <style>
    *   { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 640px; margin: 2rem auto; padding: 0 1.2rem; color: #333;
    }
    /* Compact style when embedded in a dashboard iframe */
    body.embedded {
      margin: 0.6rem;
      max-width: 100%;
    }
    body.embedded h1 { display: none; }
    body.embedded .card { margin: 0.5rem 0; padding: 0.7rem 0.9rem; }
    body.embedded .nav-links { display: none; }
    h1  { color: #03a9f4; font-size: 1.5rem; }
    .card {
      border-radius: 8px; padding: 1rem 1.2rem; margin: 1rem 0;
      background: #f5f5f5;
    }
    .info { background: #e3f2fd; border-left: 4px solid #03a9f4; }
    .warn { background: #fff8e1; border-left: 4px solid #ffc107; }
    .ok   { background: #e8f5e9; border-left: 4px solid #4caf50; }
    .err  { background: #ffebee; border-left: 4px solid #f44336; }
    ul, ol { margin: 0.4rem 0; padding-left: 1.4rem; }
    li     { margin: 0.3rem 0; }
    code   { background: #eee; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }
    a      { color: #03a9f4; }
    esp-web-install-button { display: block; margin: 1.4rem 0; }
    esp-web-install-button::part(button) {
      background: #03a9f4; color: #fff; border: none;
      padding: 0.75rem 2rem; font-size: 1.05rem;
      border-radius: 6px; cursor: pointer; width: 100%;
    }
    esp-web-install-button::part(button):hover { background: #0288d1; }
  </style>
</head>
<body>
  <h1>&#9889; Freematics ONE+ Browser Flasher</h1>

  <div class="card ok">
    This page flashes the firmware directly from <strong>your browser</strong>
    to the Freematics ONE+ connected to <strong>your computer's USB port</strong>
    &mdash; your computer does not need to be the Home Assistant server.
  </div>

  <div class="card info">
    <strong>Requirements:</strong>
    <ul>
      <li>Google Chrome or Microsoft Edge (version 89 or newer)</li>
      <li>Freematics ONE+ connected via USB to <em>this computer</em></li>
      <li>
        USB-Serial driver installed for your device's chip:<br>
        &bull; <a href="https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers"
                  target="_blank" rel="noopener">CP210x driver (Silicon Labs)</a><br>
        &bull; <a href="https://www.wch-ic.com/downloads/CH341SER_EXE.html"
                  target="_blank" rel="noopener">CH340 driver (WCH)</a>
      </li>
    </ul>
  </div>

  <div id="no-serial-warn" class="card warn" style="display:none">
    <span id="serial-warn-msg">
      &#9888; <strong>Web Serial API not available.</strong><br>
      Please open this page in <strong>Google Chrome</strong> or
      <strong>Microsoft Edge</strong> (version 89+).
    </span>
  </div>

  <div id="provisioned-note" class="card ok" style="display:none">
    &#128274; <strong>Auto-Provisioning active</strong> &mdash; your WiFi, APN, and HA
    server settings will be written to the device during this flash session.
  </div>

  <esp-web-install-button id="ewb" manifest="/api/freematics/manifest.json">
    <button slot="activate">&#9889; Connect &amp; Flash Firmware</button>
    <span slot="unsupported">
      <div class="card err">
        &#9888; Web Serial is not supported in this browser.
        Please use Chrome or Edge 89+.
      </div>
    </span>
  </esp-web-install-button>

  <div class="card">
    <strong>Steps:</strong>
    <ol>
      <li>Click <em>Connect &amp; Flash Firmware</em></li>
      <li>
        Select the serial port of the Freematics ONE+ from the browser dialog.<br>
        <small>Look for: <code>CP2102</code>, <code>CH340</code>, or a
        similar USB-Serial device name.</small>
      </li>
      <li>The firmware flashes automatically (may take up to 2 min)</li>
      <li>The device restarts and begins sending data to Home Assistant</li>
    </ol>
  </div>

  <div class="card warn">
    <strong>&#9888; If the flash stalls at &ldquo;Connecting&hellip;&rdquo;:</strong><br>
    The Web Serial API may not complete the automatic reset in some browsers. Use the
    <strong>esptool command line</strong> instead — it handles device reset automatically
    via DTR/RTS, just as it does when you run<br>
    <code>python -m esptool write-flash 0x1000 flash_image.bin</code><br>
    (add <code>--port COM3</code> if esptool does not detect the port automatically).
    Download <code>flash_image.bin</code> from the Home Assistant panel.
  </div>

  <p class="nav-links" style="margin-top:2rem">
    <a href="javascript:history.back()">&#8592; Back to Home Assistant</a>
    &nbsp;&nbsp;
    <a href="/api/freematics/console" target="_blank" rel="noopener">&#128291; Serial Console</a>
    &nbsp;&nbsp;
    <a href="https://github.com/northpower25/Freematics/blob/master/docs/README.md"
       target="_blank" rel="noopener">Documentation</a>
  </p>

  <script>
    // Apply a provisioned manifest URL when this page is opened from the HA
    // panel (either directly or via iframe).  The URL contains a short-lived
    // token so that WiFi, APN, and HA server settings are embedded in the
    // flash image automatically — no manual configuration after flashing.
    // Only accept paths that belong to the local HA API to prevent open-
    // redirect or manifest-injection attacks.
    (function () {
      const params = new URLSearchParams(window.location.search);
      const m = params.get('manifest');
      if (m && /^\\/api\\/freematics\\/manifest\\.json(\\?|$)/.test(m)) {
        document.getElementById('ewb').setAttribute('manifest', m);
        document.getElementById('provisioned-note').style.display = 'block';
      }
      // Apply embedded (iframe) mode: compact layout, hide navigation links.
      if (params.get('embedded') === '1') {
        document.body.classList.add('embedded');
      }
    })();

    // Accept manifest URL updates from the parent frame (dashboard panel).
    // The panel sends a postMessage when a fresh provisioning token is ready,
    // allowing the iframe to update without a full page reload.
    window.addEventListener('message', function (event) {
      // Only accept messages from the same origin for security.
      if (event.origin !== window.location.origin) return;
      if (event.data && event.data.type === 'freematics:updateManifest') {
        const m = event.data.manifest;
        if (m && /^\\/api\\/freematics\\/manifest\\.json(\\?|$)/.test(m)) {
          document.getElementById('ewb').setAttribute('manifest', m);
          document.getElementById('provisioned-note').style.display = 'block';
        }
      }
    });

    if (!('serial' in navigator)) {
      const warn = document.getElementById('no-serial-warn');
      warn.style.display = 'block';
      if (!window.isSecureContext) {
        document.getElementById('serial-warn-msg').innerHTML =
          '&#9888; <strong>Web Serial API not available &ndash; HTTPS required.</strong><br>' +
          'The Web Serial API requires a <strong>secure HTTPS connection</strong>. ' +
          'Open Home Assistant via <strong>Nabu Casa</strong> (*.ui.nabu.casa) or ' +
          'via <code>http://localhost:8123</code> to enable browser flashing. ' +
          'This is a browser security requirement and is unrelated to where your ' +
          'USB device is plugged in.';
      }
    }
  </script>
</body>
</html>
"""

_CONSOLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freematics ONE+ Serial Console</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 900px; margin: 1.5rem auto; padding: 0 1rem; color: #333;
      background: #fafafa;
    }
    h1 { color: #03a9f4; font-size: 1.4rem; margin-bottom: 0.4rem; }
    .subtitle { color: #666; font-size: 0.9rem; margin-bottom: 1rem; }
    .card {
      border-radius: 8px; padding: 0.8rem 1rem; margin: 0.8rem 0;
      background: #f5f5f5;
    }
    .info { background: #e3f2fd; border-left: 4px solid #03a9f4; }
    .warn { background: #fff8e1; border-left: 4px solid #ffc107; }
    code { background: #e0e0e0; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.88em; }
    a { color: #03a9f4; }
    .toolbar {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .terminal {
      background: #0d1117; color: #58d68d;
      font-family: "Courier New", Courier, monospace; font-size: 0.82rem;
      padding: 12px 14px; border-radius: 8px;
      min-height: 380px; max-height: 600px;
      overflow-y: auto; white-space: pre-wrap; word-break: break-all;
      box-shadow: inset 0 2px 8px rgba(0,0,0,.5);
      margin-bottom: 10px;
    }
    .input-row { display: flex; gap: 8px; align-items: center; }
    input[type=text] {
      flex: 1; padding: 8px 10px;
      border: 1px solid #ccc; border-radius: 6px;
      font-family: "Courier New", Courier, monospace; font-size: 0.88rem;
    }
    button {
      padding: 8px 14px; border: none; border-radius: 6px;
      cursor: pointer; font-size: 0.88rem;
    }
    #connect-btn  { background: #4caf50; color: #fff; }
    #connect-btn.disconnect { background: #f44336; }
    #send-btn     { background: #03a9f4; color: #fff; }
    #clear-btn    { background: #9e9e9e; color: #fff; }
    select {
      padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px;
      font-size: 0.88rem; background: #fff;
    }
    #status {
      font-size: 0.82rem; padding: 3px 8px; border-radius: 4px;
      background: #ffebee; color: #c62828;
    }
    #status.on { background: #e8f5e9; color: #2e7d32; }
    #no-serial-warn { display: none; }
  </style>
</head>
<body>
  <h1>&#128291; Freematics ONE+ Serial Console</h1>
  <p class="subtitle">
    Like <code>python -m serial.tools.miniterm COM4 115200</code> — in your browser.
  </p>

  <div id="no-serial-warn" class="card warn">
    &#9888; <strong>Web Serial API not available.</strong><br>
    <span id="serial-warn-reason">
      Please open this page in <strong>Google Chrome</strong> or
      <strong>Microsoft Edge</strong> (version 89 or newer) over a
      <strong>secure HTTPS connection</strong> or via
      <code>http://localhost:8123</code>.
    </span>
  </div>

  <div class="card info" style="font-size:0.88rem">
    &#8505; The Serial Console opens a direct Web Serial connection to the USB port at
    the selected baud rate. All output from the device is shown in the terminal below.
    Type commands in the input field and press Enter or click Send.
  </div>

  <div class="toolbar">
    <select id="baud-select">
      <option value="9600">9600 baud</option>
      <option value="115200" selected>115200 baud</option>
      <option value="230400">230400 baud</option>
      <option value="460800">460800 baud</option>
      <option value="921600">921600 baud</option>
    </select>
    <select id="newline-select">
      <option value="crlf">CR+LF (\\r\\n)</option>
      <option value="lf">LF only (\\n)</option>
      <option value="cr">CR only (\\r)</option>
    </select>
    <button id="connect-btn">&#128291; Connect</button>
    <button id="clear-btn">&#128465; Clear</button>
    <span id="status">&#9679; Disconnected</span>
  </div>

  <div id="terminal" class="terminal"><span style="color:#57606a">— Not connected —</span></div>

  <div class="input-row">
    <input id="cmd-input" type="text"
           placeholder="Type a command and press Enter or click Send…"
           disabled>
    <button id="send-btn" disabled>&#9654; Send</button>
  </div>

  <p style="margin-top:1.5rem">
    <a href="javascript:history.back()">&#8592; Back to Home Assistant</a>
    &nbsp;&nbsp;
    <a href="/api/freematics/flasher" target="_blank" rel="noopener">&#9889; Flasher Page</a>
  </p>

  <script>
    (function () {
      const connectBtn = document.getElementById('connect-btn');
      const clearBtn   = document.getElementById('clear-btn');
      const sendBtn    = document.getElementById('send-btn');
      const cmdInput   = document.getElementById('cmd-input');
      const terminal   = document.getElementById('terminal');
      const statusEl   = document.getElementById('status');
      const baudSel    = document.getElementById('baud-select');
      const nlSel      = document.getElementById('newline-select');

      let port = null;
      let reader = null;
      let writer = null;

      function appendTerminal(text, color) {
        const placeholder = terminal.querySelector('span[style]');
        if (placeholder) terminal.innerHTML = '';
        const span = document.createElement('span');
        if (color) span.style.color = color;
        span.textContent = text;
        terminal.appendChild(span);
        terminal.scrollTop = terminal.scrollHeight;
      }

      function setConnected(connected) {
        if (connected) {
          connectBtn.textContent = '\\u23F9 Disconnect';
          connectBtn.classList.add('disconnect');
          statusEl.textContent = '\\u25CF Connected';
          statusEl.classList.add('on');
          cmdInput.disabled = false;
          sendBtn.disabled = false;
        } else {
          connectBtn.textContent = '\\uD83D\\uDD0C Connect';
          connectBtn.classList.remove('disconnect');
          statusEl.textContent = '\\u25CF Disconnected';
          statusEl.classList.remove('on');
          cmdInput.disabled = true;
          sendBtn.disabled = true;
        }
      }

      async function cleanup() {
        try { if (reader) await reader.cancel(); } catch (_) {}
        try { if (writer) await writer.close(); }  catch (_) {}
        try { if (port)   await port.close(); }    catch (_) {}
        reader = null; writer = null; port = null;
      }

      connectBtn.addEventListener('click', async () => {
        if (port) {
          appendTerminal('\\n[Disconnected]\\n', '#57606a');
          await cleanup();
          setConnected(false);
          return;
        }
        try {
          const p = await navigator.serial.requestPort();
          const baud = parseInt(baudSel.value) || 115200;
          await p.open({ baudRate: baud });
          port = p;
          setConnected(true);
          appendTerminal('\\n[Connected at ' + baud + ' baud]\\n', '#57606a');

          const decoder = new TextDecoderStream();
          p.readable.pipeTo(decoder.writable).catch(() => {});
          reader = decoder.readable.getReader();

          const encoder = new TextEncoderStream();
          encoder.readable.pipeTo(p.writable).catch(() => {});
          writer = encoder.writable.getWriter();

          (async () => {
            while (true) {
              let result;
              try { result = await reader.read(); } catch (_) { break; }
              if (result.done) break;
              appendTerminal(result.value);
            }
            appendTerminal('\\n[Connection closed]\\n', '#57606a');
            await cleanup();
            setConnected(false);
          })();
        } catch (err) {
          if (err.name !== 'NotFoundError') {
            appendTerminal('\\n[Error: ' + (err.message || err) + ']\\n', '#ff7675');
          }
        }
      });

      clearBtn.addEventListener('click', () => { terminal.innerHTML = ''; });

      async function sendCommand() {
        if (!writer || !cmdInput.value) return;
        const nlMap = { crlf: '\\r\\n', lf: '\\n', cr: '\\r' };
        const nl = nlMap[nlSel.value] || '\\r\\n';
        try {
          await writer.write(cmdInput.value + nl);
          cmdInput.value = '';
        } catch (err) {
          appendTerminal('\\n[Send error: ' + (err.message || err) + ']\\n', '#ff7675');
        }
      }
      sendBtn.addEventListener('click', sendCommand);
      cmdInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendCommand(); });

      if (!('serial' in navigator)) {
        document.getElementById('no-serial-warn').style.display = 'block';
        if (!window.isSecureContext) {
          document.getElementById('serial-warn-reason').innerHTML =
            'This page is loaded over <strong>HTTP</strong> (not HTTPS). ' +
            'The Web Serial API requires a <strong>secure HTTPS connection</strong> ' +
            'or access via <code>http://localhost:8123</code>. ' +
            'This is a browser security requirement, not related to the USB port.';
        }
      }
    })();
  </script>
</body>
</html>
"""

_OTA_FLASHER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freematics ONE+ WiFi OTA Flash</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 640px; margin: 2rem auto; padding: 0 1.2rem; color: #333;
    }
    body.embedded { margin: 0.5rem; max-width: 100%; }
    body.embedded h1 { display: none; }
    body.embedded .card { margin: 0.4rem 0; padding: 0.6rem 0.9rem; }
    body.embedded .nav-links { display: none; }
    h1 { color: #03a9f4; font-size: 1.5rem; }
    .card {
      border-radius: 8px; padding: 1rem 1.2rem; margin: 1rem 0;
      background: #f5f5f5;
    }
    .info { background: #e3f2fd; border-left: 4px solid #03a9f4; }
    .warn { background: #fff8e1; border-left: 4px solid #ffc107; }
    .ok   { background: #e8f5e9; border-left: 4px solid #4caf50; }
    .err  { background: #ffebee; border-left: 4px solid #f44336; }
    code { background: #e0e0e0; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }
    a { color: #03a9f4; }
    .form-row {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      margin-bottom: 10px;
    }
    input[type=text], input[type=number] {
      padding: 8px 10px;
      border: 1px solid #ccc; border-radius: 6px;
      font-size: 0.9rem; font-family: inherit;
      background: #fff; color: #333;
    }
    #ip-input   { flex: 1; min-width: 130px; }
    #port-input { width: 72px; }
    #flash-btn {
      background: #2196f3; color: #fff; border: none;
      padding: 10px 18px; font-size: 0.95rem; border-radius: 6px;
      cursor: pointer; font-family: inherit; white-space: nowrap;
    }
    #flash-btn:disabled { opacity: 0.55; cursor: not-allowed; }
    #flash-btn:not(:disabled):hover { background: #1976d2; }
    #status { margin-top: 6px; font-size: 0.88rem; display: none; }
    .terminal {
      background: #0d1117; color: #c9d1d9;
      font-family: "Courier New", Courier, monospace; font-size: 0.82rem;
      padding: 10px 12px; border-radius: 8px;
      min-height: 60px; max-height: 220px;
      overflow-y: auto; white-space: pre-wrap; word-break: break-all;
      box-shadow: inset 0 2px 8px rgba(0,0,0,.5);
      margin-top: 10px; display: none;
    }
    .log-ok   { color: #58d68d; }
    .log-info { color: #c9d1d9; }
    .log-err  { color: #ff6b6b; }
  </style>
</head>
<body>
  <h1>&#128246; Freematics ONE+ WiFi OTA Flash</h1>

  <div class="card info">
    Flash firmware to the Freematics ONE+ over WiFi. The device must be
    reachable from the Home Assistant server and running firmware with
    <code>ENABLE_HTTPD=1</code>.
  </div>

  <div class="card">
    <div class="form-row">
      <input id="ip-input"   type="text"   placeholder="192.168.x.x" autocomplete="off">
      <input id="port-input" type="number" placeholder="80" value="80" min="1" max="65535">
      <button id="flash-btn">&#128246; Flash via WiFi OTA</button>
    </div>
    <div id="status"></div>
    <div id="terminal" class="terminal"></div>
  </div>

  <p class="nav-links" style="margin-top:1.5rem">
    <a href="javascript:history.back()">&#8592; Back to Home Assistant</a>
  </p>

  <script>
    (function () {
      const params    = new URLSearchParams(window.location.search);
      const ipInput   = document.getElementById('ip-input');
      const portInput = document.getElementById('port-input');
      const flashBtn  = document.getElementById('flash-btn');
      const terminal  = document.getElementById('terminal');
      const statusEl  = document.getElementById('status');

      // Pre-fill IP / port from URL params when opened from the panel.
      const initIp   = params.get('device_ip');
      const initPort = params.get('device_port');
      if (initIp)   ipInput.value   = initIp;
      if (initPort) portInput.value = initPort;

      // Compact layout when embedded in a dashboard iframe.
      if (params.get('embedded') === '1') {
        document.body.classList.add('embedded');
      }

      const token = params.get('token') || '';

      function appendLog(level, text) {
        terminal.style.display = 'block';
        const span = document.createElement('span');
        span.className = 'log-' + level;
        span.textContent = text + '\\n';
        terminal.appendChild(span);
        terminal.scrollTop = terminal.scrollHeight;
      }

      function setStatus(color, html) {
        statusEl.style.display = 'block';
        statusEl.style.color   = color;
        statusEl.innerHTML     = html;
      }

      flashBtn.addEventListener('click', () => {
        const ip   = ipInput.value.trim();
        const port = parseInt(portInput.value) || 80;

        if (!ip) {
          setStatus('#ff9800', '&#9888; Please enter the device IP address.');
          return;
        }
        if (!token) {
          setStatus('#f44336', '&#10007; No provisioning token &mdash; reload the page.');
          return;
        }

        // Reset UI
        terminal.innerHTML    = '';
        terminal.style.display = 'none';
        setStatus('#2196f3', '&#9203; Uploading firmware&hellip; (may take ~2 min)');
        flashBtn.disabled    = true;
        flashBtn.textContent = '\\u23F3 Uploading\\u2026';

        const url = '/api/freematics/wifi_ota_sse'
          + '?device_ip='   + encodeURIComponent(ip)
          + '&device_port=' + encodeURIComponent(port)
          + '&token='       + encodeURIComponent(token);

        const es = new EventSource(url);

        es.onmessage = function (ev) {
          let data;
          try { data = JSON.parse(ev.data); } catch (_) { return; }

          if (data.type === 'log') {
            const level = data.level === 'error' ? 'err'
                        : data.level === 'ok'    ? 'ok'
                        : 'info';
            const ts = data.ts || new Date().toLocaleTimeString();
            appendLog(level, '[' + ts + '] ' + data.message);

          } else if (data.type === 'done') {
            es.close();
            flashBtn.disabled    = false;
            flashBtn.textContent = '\\uD83D\\uDCF6 Flash via WiFi OTA';
            if (data.ok) {
              setStatus('#4caf50', '&#10003; Flash successful!');
              appendLog('ok', '\\u2713 OTA flash completed successfully.');
            } else {
              const msg = data.message || 'OTA flash failed.';
              setStatus('#f44336', '&#10007; Flash failed: ' + msg);
              appendLog('err', '\\u2717 ' + msg);
            }
          }
        };

        es.onerror = function () {
          es.close();
          setStatus('#f44336', '&#10007; Connection to Home Assistant lost.');
          appendLog('err', '\\u2717 SSE connection error \u2014 flash may still be running on the server.');
          flashBtn.disabled    = false;
          flashBtn.textContent = '\\uD83D\\uDCF6 Flash via WiFi OTA';
        };
      });
    })();
  </script>
</body>
</html>
"""


class FreematicsOtaFlasherView(HomeAssistantView):
    """Serve the WiFi OTA flasher HTML page.

    Accessible at /api/freematics/ota_flasher.

    The page is a self-contained UI for flashing firmware to the device over
    WiFi.  It uses the /api/freematics/wifi_ota_sse SSE endpoint to stream
    real-time progress, avoiding the HTTP timeout issue that occurs when the
    long-running POST to /api/freematics/wifi_ota blocks for ~2 minutes.

    requires_auth is False so the page can be loaded inside an iframe from the
    panel (which already has HA auth context).  The page authenticates the SSE
    request via the provisioning token embedded in the URL by the panel JS.
    """

    url = "/api/freematics/ota_flasher"
    name = "api:freematics:ota_flasher"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the WiFi OTA flasher HTML page."""
        return web.Response(
            body=_OTA_FLASHER_HTML.encode("utf-8"),
            content_type="text/html",
            charset="utf-8",
        )


class FreematicsWifiOtaSseView(HomeAssistantView):
    """Stream WiFi OTA flash progress as Server-Sent Events.

    Accessible at GET /api/freematics/wifi_ota_sse.

    Query parameters:
      device_ip   – IPv4 or IPv6 literal address of the target device.
      device_port – TCP port of the device HTTP server (default: 80).
      token       – Short-lived provisioning token issued by
                    /api/freematics/provisioning_token.

    The endpoint validates the token, then starts the WiFi OTA flash in a
    background asyncio task and streams progress events via SSE so the
    browser can display real-time feedback without hitting the ~60 s HTTP
    timeout that occurs with the synchronous POST endpoint.

    Event format (JSON):
      {"type": "log",  "level": "<info|ok|error>", "message": "…", "ts": "HH:MM:SS"}
      {"type": "done", "ok": true|false, "message": "…"}

    requires_auth is False – authentication is via the provisioning token.
    """

    url = "/api/freematics/wifi_ota_sse"
    name = "api:freematics:wifi_ota_sse"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response | web.StreamResponse:
        """Stream OTA flash progress events."""
        token       = request.rel_url.query.get("token",       "").strip()
        device_ip   = request.rel_url.query.get("device_ip",   "").strip()
        try:
            device_port = int(request.rel_url.query.get("device_port", "80"))
        except (TypeError, ValueError):
            device_port = 80

        hass = request.app["hass"]

        # Validate provisioning token (same store used by NVS / manifest views).
        token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
        entry_id, expiry = token_store.get(token, (None, 0))
        if not token or expiry <= time.monotonic() or entry_id is None:
            return web.Response(status=401, text="Invalid or expired token")

        if not device_ip:
            return web.Response(status=400, text="device_ip is required")

        try:
            ipaddress.ip_address(device_ip)
        except ValueError:
            return web.Response(
                status=400,
                text="device_ip must be a valid IPv4 or IPv6 address",
            )

        # Prepare SSE response.
        resp = web.StreamResponse(
            headers={
                "Content-Type":  "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )
        await resp.prepare(request)

        queue: asyncio.Queue = asyncio.Queue()

        from .flash_manager import async_flash_wifi  # noqa: PLC0415

        # Resolve LED/beep settings from the config entry identified by the
        # provisioning token so they are applied to NVS before flashing.
        _led_red_en: bool | None = None
        _led_white_en: bool | None = None
        _beep_en: bool | None = None
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None:
            cfg = {**entry.data, **entry.options}
            _led_red_en   = bool(cfg.get(CONF_LED_RED_EN,   True))
            _led_white_en = bool(cfg.get(CONF_LED_WHITE_EN, True))
            _beep_en      = bool(cfg.get(CONF_BEEP_EN,      True))

        # Start the flash in a background task so the SSE handler can still
        # send keep-alive pings and the flash continues even if the client
        # disconnects (preventing a half-flashed device).
        async def _run_flash() -> None:
            ok, msg, _ = await async_flash_wifi(
                device_ip,
                device_port,
                queue=queue,
                led_red_en=_led_red_en,
                led_white_en=_led_white_en,
                beep_en=_beep_en,
            )
            queue.put_nowait({"type": "done", "ok": ok, "message": msg})

        flash_task = asyncio.ensure_future(_run_flash())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Send a keep-alive comment to prevent proxy / browser
                    # from closing an idle SSE connection.
                    try:
                        await resp.write(b": keepalive\n\n")
                    except Exception:  # noqa: BLE001
                        break
                    continue

                try:
                    await resp.write(
                        ("data: " + json.dumps(event) + "\n\n").encode("utf-8")
                    )
                    await resp.drain()
                except Exception:  # noqa: BLE001
                    break

                if event.get("type") == "done":
                    break
        except Exception:  # noqa: BLE001
            pass
        finally:
            # Log if the flash task is still running after the SSE connection
            # closed (e.g. client navigated away).  We intentionally do NOT
            # cancel it: stopping a firmware upload mid-transfer would leave
            # the device in an indeterminate state.
            if not flash_task.done():
                _LOGGER.info(
                    "WiFi OTA SSE: client disconnected, flash to %s continues "
                    "in background",
                    device_ip,
                )

        return resp


class FreematicsFlasherView(HomeAssistantView):
    """Serve the browser-based serial flasher HTML page.

    Accessible at /api/freematics/flasher.

    requires_auth is False so users can open it directly from their browser
    without needing to pass a Bearer token (the page itself is just static HTML).
    The firmware this integration uses is open-source (BSD-licensed), so there
    are no proprietary concerns with serving it without authentication.
    """

    url = "/api/freematics/flasher"
    name = "api:freematics:flasher"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the flasher HTML page."""
        return web.Response(
            body=_FLASHER_HTML.encode("utf-8"),
            content_type="text/html",
            charset="utf-8",
        )


class FreematicsSerialConsoleView(HomeAssistantView):
    """Serve a standalone Web Serial terminal page.

    Accessible at /api/freematics/console.

    Opens in its own browser tab.  Provides a serial monitor at 115200 baud
    (configurable) so the user can watch the device log and send commands,
    equivalent to ``python -m serial.tools.miniterm <PORT> 115200``.

    requires_auth is False: the page is static HTML and contains no device
    credentials.  The user must explicitly select their own serial port through
    the browser's native port-picker dialog.
    """

    url = "/api/freematics/console"
    name = "api:freematics:console"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the standalone serial console HTML page."""
        return web.Response(
            body=_CONSOLE_HTML.encode("utf-8"),
            content_type="text/html",
            charset="utf-8",
        )


class FreematicsFirmwareView(HomeAssistantView):
    """Serve the bundled firmware binary.

    Accessible at /api/freematics/firmware.bin.
    Referenced by the manifest as a relative path.

    requires_auth is False because esp-web-tools (loaded from CDN) fetches this
    via the browser's native fetch() API and cannot inject a HA Bearer token.
    The firmware binary is open-source (BSD-licensed) and ships in the HACS
    download, so it is not sensitive data.

    These views are registered in async_setup() and persist for the lifetime of
    the HA process. There is no standard HA mechanism to unregister aiohttp
    routes; if the integration is removed and re-added, the routes are
    re-registered harmlessly (aiohttp deduplicates them).
    """

    url = "/api/freematics/firmware.bin"
    name = "api:freematics:firmware"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the firmware binary (read in a thread executor)."""
        if not FIRMWARE_PATH.exists():
            return web.Response(status=404, text="Firmware binary not found")
        try:
            hass = request.app["hass"]
            data: bytes = await hass.async_add_executor_job(FIRMWARE_PATH.read_bytes)
        except OSError as exc:
            return web.Response(status=500, text=f"Cannot read firmware: {exc}")
        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=telelogger.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )


class FreematicsBootloaderView(HomeAssistantView):
    """Serve the second-stage bootloader binary.

    Accessible at /api/freematics/bootloader.bin.
    Referenced by the esp-web-tools manifest so that the bootloader is always
    written at 0x1000 during a Web Serial flash.

    Including the bootloader is critical: esp-web-tools performs a full chip
    erase on the first ("new install") flash, wiping the existing bootloader at
    0x1000.  Without restoring it the ROM bootloader cannot hand off to the
    second-stage loader and the device loops endlessly with:
        flash read err, 1000  /  ets_main.c 371

    requires_auth is False: the bootloader binary is not device-specific and
    contains no sensitive data.
    """

    url = "/api/freematics/bootloader.bin"
    name = "api:freematics:bootloader"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the second-stage bootloader binary."""
        if not BOOTLOADER_PATH.exists():
            return web.Response(status=404, text="Bootloader binary not found")
        try:
            hass = request.app["hass"]
            data: bytes = await hass.async_add_executor_job(BOOTLOADER_PATH.read_bytes)
        except OSError as exc:
            return web.Response(status=500, text=f"Cannot read bootloader: {exc}")
        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=bootloader.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )


class FreematicsPartitionTableView(HomeAssistantView):
    """Serve the huge_app partition table binary.

    Accessible at /api/freematics/partition_table.bin.
    Referenced by the esp-web-tools manifest so that the correct partition
    scheme is always written at 0x8000 when flashing via Web Serial.

    Including the partition table ensures devices with a different scheme
    (e.g. default Arduino partitions) are migrated to huge_app automatically
    during the Web Serial flash, which is required for the NVS partition at
    0x9000 to be located correctly by the firmware.

    requires_auth is False: the partition table is the same for all devices
    (not device-specific) and contains no sensitive data.
    """

    url = "/api/freematics/partition_table.bin"
    name = "api:freematics:partition_table"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the huge_app partition table binary."""
        from .nvs_helper import generate_partition_table  # noqa: PLC0415

        hass = request.app["hass"]
        pt_data = await hass.async_add_executor_job(generate_partition_table)
        return web.Response(
            body=pt_data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=partition_table.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )


class FreematicsProxyOTAView(HomeAssistantView):
    """Proxy a WiFi OTA flash request from the panel browser to the device.

    Accessible at POST /api/freematics/wifi_ota.

    Accepts JSON body: {"device_ip": "192.168.x.x", "device_port": 80}

    The browser panel sends this request (with HA auth token).  This view
    then uses the HA server to push the bundled firmware binary to the device
    via HTTP multipart upload.  The device must be reachable from the HA
    server on the specified IP and port.

    requires_auth is True – only authenticated HA users may trigger a flash.
    """

    url = "/api/freematics/wifi_ota"
    name = "api:freematics:wifi_ota"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Trigger WiFi OTA flash from the HA server to the device."""
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "Invalid JSON body"}).encode(),
                content_type="application/json",
            )

        device_ip = str(data.get("device_ip", "")).strip()
        try:
            device_port = int(data.get("device_port", 80))
        except (TypeError, ValueError):
            device_port = 80

        if not device_ip:
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "device_ip is required"}).encode(),
                content_type="application/json",
            )

        # Validate that device_ip is a well-formed IP address (not a hostname or
        # URL) to mitigate SSRF: ipaddress.ip_address rejects anything that is
        # not a pure IPv4 or IPv6 literal.
        try:
            ipaddress.ip_address(device_ip)
        except ValueError:
            return web.Response(
                status=400,
                body=json.dumps({"ok": False, "message": "device_ip must be a valid IPv4 or IPv6 address"}).encode(),
                content_type="application/json",
            )

        from .flash_manager import async_flash_wifi  # noqa: PLC0415

        # Try to find LED/beep settings from a Freematics config entry.
        # This view lacks a per-device token so we use the first active entry.
        # If multiple entries exist, use the OTA flasher page instead.
        hass = request.app["hass"]
        _led_red_en: bool | None = None
        _led_white_en: bool | None = None
        _beep_en: bool | None = None
        entries = hass.config_entries.async_entries(DOMAIN)
        if entries:
            _cfg = {**entries[0].data, **entries[0].options}
            _led_red_en   = bool(_cfg.get(CONF_LED_RED_EN,   True))
            _led_white_en = bool(_cfg.get(CONF_LED_WHITE_EN, True))
            _beep_en      = bool(_cfg.get(CONF_BEEP_EN,      True))

        ok, msg, log_lines = await async_flash_wifi(
            device_ip,
            device_port,
            led_red_en=_led_red_en,
            led_white_en=_led_white_en,
            beep_en=_beep_en,
        )
        return web.Response(
            body=json.dumps({"ok": ok, "message": msg, "log": log_lines}).encode("utf-8"),
            content_type="application/json",
        )


# ---------------------------------------------------------------------------
# Provisioning token + NVS partition endpoints
# ---------------------------------------------------------------------------

class FreematicsProvisioningTokenView(HomeAssistantView):
    """Issue a short-lived provisioning token tied to the caller's config entry.

    Accessible at GET /api/freematics/provisioning_token.

    Requires HA authentication (requires_auth = True).  The returned token is
    embedded in the manifest URL and the NVS endpoint URL so that esp-web-tools
    (running in the browser without a Bearer token) can download the
    personalised NVS partition image.

    Response JSON:
      {
        "token": "<hex token>",
        "manifest_url": "/api/freematics/manifest.json?token=<token>",
        "nvs_url": "/api/freematics/config_nvs.bin?token=<token>",
        "flash_image_url": "/api/freematics/flash_image.bin?token=<token>",
        "nvs_offset": 36864,
        "expires_in": 300,
        "device_ip": "<configured device IP or empty string>",
        "device_port": 80
      }
    """

    url = "/api/freematics/provisioning_token"
    name = "api:freematics:provisioning_token"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Issue a provisioning token for the authenticated user's config entry."""
        hass = request.app["hass"]
        token = secrets.token_hex(32)
        expiry = time.monotonic() + _TOKEN_TTL

        entries = hass.config_entries.async_entries(DOMAIN)
        entry_id = entries[0].entry_id if entries else None
        entry = entries[0] if entries else None
        cfg = {**(entry.data if entry else {}), **(entry.options if entry else {})}

        token_store = hass.data.setdefault(DOMAIN, {}).setdefault("_tokens", {})
        token_store[token] = (entry_id, expiry)

        now = time.monotonic()
        expired = [t for t, (_, exp) in list(token_store.items()) if exp < now]
        for t in expired:
            token_store.pop(t, None)

        from .nvs_helper import NVS_PARTITION_OFFSET  # noqa: PLC0415

        return web.Response(
            body=json.dumps({
                "token": token,
                "manifest_url": f"/api/freematics/manifest.json?token={token}",
                "nvs_url": f"/api/freematics/config_nvs.bin?token={token}",
                "flash_image_url": f"/api/freematics/flash_image.bin?token={token}",
                "nvs_offset": NVS_PARTITION_OFFSET,
                "expires_in": _TOKEN_TTL,
                "device_ip": cfg.get(CONF_DEVICE_IP, ""),
                "device_port": cfg.get(CONF_DEVICE_PORT, DEFAULT_DEVICE_PORT),
            }).encode("utf-8"),
            content_type="application/json",
        )


class FreematicsPersonalisedManifestView(HomeAssistantView):
    """Serve the esp-web-tools manifest, optionally with a personalised NVS part.

    Accessible at GET /api/freematics/manifest.json?token=<token>.

    requires_auth is False because esp-web-tools fetches this via the browser
    native fetch() API without a HA Bearer token.

    Without a token the response is the standard manifest (firmware only).
    With a valid token a second part is appended pointing to the NVS partition
    image so the device boots with pre-configured settings.
    """

    url = "/api/freematics/manifest.json"
    name = "api:freematics:manifest"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the firmware manifest JSON."""
        import copy  # noqa: PLC0415

        token = request.rel_url.query.get("token", "")
        manifest = copy.deepcopy(_MANIFEST_BASE)

        if token:
            hass = request.app["hass"]
            token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
            entry_id, expiry = token_store.get(token, (None, 0))
            if expiry > time.monotonic() and entry_id is not None:
                from .nvs_helper import NVS_PARTITION_OFFSET  # noqa: PLC0415
                manifest["builds"][0]["parts"].append(
                    {
                        "path": f"config_nvs.bin?token={token}",
                        "offset": NVS_PARTITION_OFFSET,
                    }
                )

        return web.Response(
            body=json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
        )


async def _build_nvs_kwargs(hass, entry) -> dict:
    """Return keyword-argument dict for generate_nvs_partition() from a config entry.

    Extracts WiFi credentials, cellular APN, server host/port, and webhook path
    from the config entry, resolving the HA external URL for the server address.
    """
    cfg = {**entry.data, **entry.options}
    wifi_ssid = cfg.get(CONF_WIFI_SSID, "")
    wifi_password = cfg.get(CONF_WIFI_PASSWORD, "")
    cell_apn = cfg.get(CONF_CELL_APN, "")
    sim_pin = cfg.get(CONF_SIM_PIN, "")
    webhook_id = cfg.get(CONF_WEBHOOK_ID, "")
    enable_ble = bool(cfg.get(CONF_ENABLE_BLE, False))
    cell_debug = bool(cfg.get(CONF_CELL_DEBUG, False))
    led_red_en = bool(cfg.get(CONF_LED_RED_EN, True))
    led_white_en = bool(cfg.get(CONF_LED_WHITE_EN, True))
    beep_en = bool(cfg.get(CONF_BEEP_EN, True))
    data_interval_ms = int(cfg.get(CONF_DATA_INTERVAL_MS, 0))
    sync_interval_s = int(cfg.get(CONF_SYNC_INTERVAL_S, 0))

    # Determine the operating mode.  New entries use the operating_mode selector;
    # legacy pre-existing entries fall back to the old enable_httpd boolean.
    operating_mode = cfg.get(CONF_OPERATING_MODE)
    if operating_mode is not None:
        is_datalogger = (operating_mode == OPERATING_MODE_DATALOGGER)
    else:
        is_datalogger = bool(cfg.get(CONF_ENABLE_HTTPD, False))

    # HTTPD is always enabled in NVS so the device can receive OTA firmware
    # updates via WiFi regardless of operating mode.  The built-in HTTP server
    # (port 80) is required by the WiFi OTA flash mechanism.  In telelogger mode
    # BLE is already disabled to free memory for the TLS webhook client, so the
    # HTTP server and the TLS stack can coexist without memory pressure.
    enable_httpd = True

    # Webhook mode: the device sends telemetry to HA via HTTPS POST.  Only used
    # in telelogger (non-datalogger) mode and only when a webhook ID is present.
    is_webhook_mode = bool(webhook_id and not is_datalogger)

    server_host = ""
    server_port = 443
    webhook_path = ""
    # Cellular-specific server overrides.  When Nabu Casa cloud is active the
    # cloud webhook endpoint (hooks.nabu.casa) is stored here so that cellular
    # connections use it directly.  The SIM7600 modem cannot connect to the
    # Remote UI proxy (*.ui.nabu.casa) that get_url() may return; only
    # hooks.nabu.casa is reachable and reliable for IoT cellular devices.
    # WiFi connections use SERVER_HOST / WEBHOOK_PATH as before.
    cell_server_host = ""
    cell_server_port = 443
    cell_webhook_path = ""

    # Step 1 – try to obtain the Nabu Casa Cloud Webhook URL (hooks.nabu.casa).
    # This URL works from any network (WiFi or cellular) and is the only
    # option that SIM7600-based cellular devices can reach reliably.
    # The Remote UI URL (*.ui.nabu.casa) returned by get_url() is a browser-
    # only proxy; IoT devices (SIM7600, etc.) fail with TLS peer-close errors
    # because the Remote UI proxy does not accept direct machine-to-machine
    # HTTPS connections.
    _cloud_used = False
    if is_webhook_mode:
        # Try to obtain the Nabu Casa cloud webhook URL.  _candidate_url is
        # initialised here so the cached-URL fallback below can be reached even
        # when async_is_logged_in() returns False (e.g. cloud session expired
        # or cloud connection temporarily dropped since the config-flow ran).
        _candidate_url = None
        _cloud_logged_in = False
        try:
            from homeassistant.components import cloud as _ha_cloud  # noqa: PLC0415
            _cloud_logged_in = _ha_cloud.async_is_logged_in(hass)
            if _cloud_logged_in:
                # Try a fresh cloud hook URL.
                try:
                    _candidate_url = await _ha_cloud.async_create_cloudhook(hass, webhook_id)
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Freematics: could not reach Nabu Casa cloud for webhook %s "
                        "– will try cached URL.",
                        webhook_id,
                    )
        except Exception:  # noqa: BLE001
            pass  # Cloud component not available – fall through to cached URL / get_url()

        # Fall back to the cached cloud hook URL stored in entry.data.  This is
        # populated during config_flow setup or a previous successful provisioning
        # request.  Using the cached URL here ensures that re-provisioning works
        # even when Nabu Casa cloud is temporarily offline (async_is_logged_in()
        # returned False) or async_create_cloudhook() raised an exception – as
        # long as the URL was obtained during any prior session.
        if not _candidate_url:
            _cached = cfg.get(CONF_CLOUD_HOOK_URL, "")
            if _cached:
                _candidate_url = _cached
                _LOGGER.warning(
                    "Freematics: Nabu Casa cloud not available for webhook %s "
                    "– using cached hooks.nabu.casa URL from a previous session.",
                    webhook_id,
                )
            elif _cloud_logged_in:
                # Logged in but hook creation failed and no cached URL available.
                _LOGGER.warning(
                    "Freematics: could not create Nabu Casa cloud webhook "
                    "for %s – re-provision the device once Nabu Casa cloud "
                    "is connected to receive the correct hooks.nabu.casa URL.",
                    webhook_id,
                )

        if _candidate_url:
            try:
                _parsed = urlparse(_candidate_url)
                cell_server_host = _parsed.hostname or ""
                cell_server_port = (
                    _parsed.port or (443 if _parsed.scheme == "https" else 80)
                )
                cell_webhook_path = _parsed.path or ""
                # Only use the cloud hook URL when parsing produced a
                # non-empty hostname; an empty hostname would cause the
                # firmware to use the compile-time default server instead.
                if not cell_server_host:
                    raise ValueError("cloud hook URL has no hostname")
                # Also use the cloud hook URL for WiFi so that both
                # interfaces use the same publicly-reachable endpoint when
                # cloud is active.  The SERVER_HOST / WEBHOOK_PATH NVS
                # keys are shared between WiFi and cellular; CELL_HOST /
                # CELL_PATH provide an explicit cellular override so
                # devices re-provisioned while offline still get the right
                # URL for cellular after cloud reconnects.
                server_host = cell_server_host
                server_port = cell_server_port
                webhook_path = cell_webhook_path
                # Mark cloud as used when the URL was successfully obtained
                # (fresh or cached).  The hooks.nabu.casa path format requires
                # an opaque token returned by async_create_cloudhook – the raw
                # webhook_id is NOT a valid path on hooks.nabu.casa and will
                # cause Cloudflare to close the connection without sending any
                # HTTP response (firmware reports "[HTTP] No response").
                # Fall through to get_url() on failure so the device is at
                # least provisioned with a usable local URL.
                _cloud_used = True
                # Persist the URL in entry.data so that future provisioning
                # requests can use it even when cloud is temporarily offline.
                if _candidate_url != cfg.get(CONF_CLOUD_HOOK_URL, ""):
                    try:
                        hass.config_entries.async_update_entry(
                            entry,
                            data={**entry.data, CONF_CLOUD_HOOK_URL: _candidate_url},
                        )
                    except Exception as _exc:  # noqa: BLE001
                        _LOGGER.warning(
                            "Freematics: failed to persist cloud hook URL to "
                            "config entry: %s",
                            _exc,
                        )
            except Exception as _exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Freematics: failed to parse cloud hook URL %r: %s",
                    _candidate_url,
                    _exc,
                )

    # Step 2 – fall back to get_url() for the shared WiFi / general server
    # settings when the cloud hook was not available.
    if not _cloud_used:
        try:
            from homeassistant.helpers.network import get_url  # noqa: PLC0415
            base_url = get_url(hass, prefer_external=True)
            parsed = urlparse(base_url)
            server_host = parsed.hostname or ""
            if parsed.port:
                server_port = parsed.port
            elif parsed.scheme == "https":
                server_port = 443
            else:
                server_port = 80
        except Exception:  # noqa: BLE001
            # get_url() can raise NoURLAvailableError or other network-related
            # errors when no external URL is configured.  Cellular connections
            # require an externally reachable Home Assistant URL (Nabu Casa or
            # port-forward).  Log a warning so the user understands why the device
            # cannot reach Home Assistant.
            _LOGGER.warning(
                "Freematics: no external Home Assistant URL configured. "
                "Cellular (SIM) connections require Nabu Casa cloud access or a "
                "publicly reachable URL. The firmware will fall back to the "
                "compile-time default server (hub.freematics.com), which will NOT "
                "deliver webhooks to this Home Assistant instance."
            )
        # In datalogger mode the device serves a local HTTP API and must NOT
        # send webhooks to HA – leave webhook_path empty so the firmware falls
        # back to the legacy Freematics Hub path.  Webhooks are only used in
        # telelogger mode.
        if is_webhook_mode:
            webhook_path = f"/api/webhook/{webhook_id}"
        # Warn when the external URL is a Nabu Casa Remote UI address.  The
        # Remote UI proxy (*.ui.nabu.casa) works for WiFi (ESP32 MBEDTLS) but
        # SIM7600 cellular devices cannot complete TLS to it.  No CELL_HOST is
        # set in this branch because without the cloud hook token there is no
        # valid cellular endpoint to offer.
        if server_host and ".ui.nabu.casa" in server_host:
            _LOGGER.warning(
                "Freematics: the external HA URL (%s) is a Nabu Casa Remote UI "
                "address. WiFi provisioning will use this URL but cellular (SIM) "
                "connections will fail. Re-provision the device once Nabu Casa "
                "cloud is connected so that the correct hooks.nabu.casa URL can "
                "be stored for cellular use.",
                server_host,
            )

    return {
        "wifi_ssid": wifi_ssid,
        "wifi_password": wifi_password,
        "cell_apn": cell_apn,
        "sim_pin": sim_pin,
        "server_host": server_host,
        "server_port": server_port,
        "webhook_path": webhook_path,
        "cell_server_host": cell_server_host,
        "cell_server_port": cell_server_port,
        "cell_webhook_path": cell_webhook_path,
        "enable_httpd": enable_httpd,
        "enable_ble": enable_ble,
        "cell_debug": cell_debug,
        "led_red_en": led_red_en,
        "led_white_en": led_white_en,
        "beep_en": beep_en,
        "data_interval_ms": data_interval_ms,
        "sync_interval_s": sync_interval_s,
    }


class FreematicsConfigNvsView(HomeAssistantView):
    """Serve a personalised NVS partition image for initial device provisioning.

    Accessible at GET /api/freematics/config_nvs.bin?token=<token>.

    requires_auth is False because esp-web-tools fetches this directly from
    the browser using the URL embedded in the manifest (no Bearer token).
    A valid provisioning token is required; tokens are issued by
    /api/freematics/provisioning_token (auth required) and expire after
    _TOKEN_TTL seconds.

    The NVS image encodes:
      - WiFi SSID / password (so the device connects on first boot)
      - Cellular APN (cellular fallback)
      - Server host / port / webhook path (firmware v5.1+ with NVS server settings)
    """

    url = "/api/freematics/config_nvs.bin"
    name = "api:freematics:config_nvs"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the NVS partition binary for the token's config entry."""
        token = request.rel_url.query.get("token", "")
        if not token:
            return web.Response(status=400, text="token parameter required")

        hass = request.app["hass"]
        token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
        entry_id, expiry = token_store.get(token, (None, 0))
        if expiry <= time.monotonic() or entry_id is None:
            return web.Response(status=403, text="Invalid or expired token")

        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return web.Response(status=404, text="Config entry not found")

        kwargs = await _build_nvs_kwargs(hass, entry)

        from .nvs_helper import generate_nvs_partition  # noqa: PLC0415

        nvs_data = await hass.async_add_executor_job(
            generate_nvs_partition,
            kwargs["wifi_ssid"],
            kwargs["wifi_password"],
            kwargs["cell_apn"],
            kwargs["server_host"],
            kwargs["server_port"],
            kwargs["webhook_path"],
            kwargs["enable_httpd"],
            kwargs["enable_ble"],
            kwargs["data_interval_ms"],
            kwargs["sync_interval_s"],
            kwargs["sim_pin"],
            kwargs["cell_server_host"],
            kwargs["cell_server_port"],
            kwargs["cell_webhook_path"],
            kwargs["cell_debug"],
        )

        if nvs_data is None:
            return web.Response(
                status=503,
                text=(
                    "NVS partition generation failed. "
                    "Install esp-idf-nvs-partition-gen: pip install esp-idf-nvs-partition-gen"
                ),
            )

        return web.Response(
            body=nvs_data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=config_nvs.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )


class FreematicsFlashImageView(HomeAssistantView):
    """Serve a combined single-file flash image (partition table + NVS + firmware).

    Accessible at GET /api/freematics/flash_image.bin?token=<token>.

    The returned binary merges:
      - The second-stage bootloader (0x1000, ~19 KB)
      - The huge_app partition table (0x8000, 4 KB)
      - The personalised NVS partition (0x9000, 20 KB) with device settings
      - 0xFF padding covering the otadata region (0xE000–0xFFFF)
      - The pre-compiled application firmware (telelogger.bin, from 0x10000)

    The whole file is written at flash offset 0x1000 in a single operation:
      python -m esptool write-flash 0x1000 flash_image.bin

    Including the bootloader is critical: esp-web-tools performs a full chip
    erase on the first ("new install") flash, wiping the bootloader at 0x1000.
    Without restoring it the ROM bootloader cannot hand off and the device loops
    endlessly with "flash read err, 1000 / ets_main.c 371".  Including the
    partition table ensures the correct huge_app partition scheme is always
    programmed.

    Do NOT use the Freematics Builder with this file – the Builder writes at
    0x10000 which would corrupt the partition layout and cause a restart loop.

    requires_auth is False; a valid provisioning token authorises access
    (same pattern as config_nvs.bin).
    """

    url = "/api/freematics/flash_image.bin"
    name = "api:freematics:flash_image"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the combined bootloader + NVS + firmware flash image."""
        token = request.rel_url.query.get("token", "")
        if not token:
            return web.Response(status=400, text="token parameter required")

        hass = request.app["hass"]
        token_store = hass.data.get(DOMAIN, {}).get("_tokens", {})
        entry_id, expiry = token_store.get(token, (None, 0))
        if expiry <= time.monotonic() or entry_id is None:
            return web.Response(status=403, text="Invalid or expired token")

        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return web.Response(status=404, text="Config entry not found")

        if not FIRMWARE_PATH.exists():
            return web.Response(status=404, text="Firmware binary not found")

        kwargs = await _build_nvs_kwargs(hass, entry)

        from .nvs_helper import generate_flash_image, generate_nvs_partition  # noqa: PLC0415

        nvs_data = await hass.async_add_executor_job(
            generate_nvs_partition,
            kwargs["wifi_ssid"],
            kwargs["wifi_password"],
            kwargs["cell_apn"],
            kwargs["server_host"],
            kwargs["server_port"],
            kwargs["webhook_path"],
            kwargs["enable_httpd"],
            kwargs["enable_ble"],
            kwargs["data_interval_ms"],
            kwargs["sync_interval_s"],
            kwargs["sim_pin"],
            kwargs["cell_server_host"],
            kwargs["cell_server_port"],
            kwargs["cell_webhook_path"],
            kwargs["cell_debug"],
        )

        if nvs_data is None:
            return web.Response(
                status=503,
                text=(
                    "NVS partition generation failed. "
                    "Install esp-idf-nvs-partition-gen: pip install esp-idf-nvs-partition-gen"
                ),
            )

        bootloader_path = BOOTLOADER_PATH if BOOTLOADER_PATH.exists() else None
        image_data = await hass.async_add_executor_job(
            generate_flash_image, nvs_data, FIRMWARE_PATH, bootloader_path
        )

        if image_data is None:
            return web.Response(status=503, text="Failed to build flash image")

        return web.Response(
            body=image_data,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=flash_image.bin",
                "Access-Control-Allow-Origin": "*",
            },
        )
