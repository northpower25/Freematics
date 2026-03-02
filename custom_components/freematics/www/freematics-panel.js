/**
 * Freematics ONE+ Sidebar Panel
 *
 * Custom panel element that is registered as a Home Assistant sidebar entry
 * automatically when the Freematics ONE+ integration is installed.
 *
 * Tabs:
 *  1. Dashboard  – live vehicle telemetry, auto-discovers all Freematics devices.
 *  2. Flash      – browser-based firmware flasher using the Web Serial API
 *                  (Chrome / Edge 89+).  The user picks the COM port from the
 *                  native browser dialog; no manual port entry is needed.
 */

const PANEL_VERSION = "1.0.0";

/* -------------------------------------------------------------------------
 * Styles
 * ---------------------------------------------------------------------- */
const STYLES = `
  :host {
    display: block;
    height: 100%;
    overflow: auto;
    font-family: var(--primary-font-family, Roboto, sans-serif);
    background: var(--primary-background-color);
  }
  .panel-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px 0;
  }
  .panel-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--primary-text-color);
  }
  .panel-icon {
    color: #2196f3;
    font-size: 2rem;
  }
  .tabs {
    display: flex;
    gap: 4px;
    padding: 12px 20px 0;
    border-bottom: 1px solid var(--divider-color);
  }
  .tab {
    padding: 8px 16px;
    cursor: pointer;
    border-radius: 6px 6px 0 0;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--secondary-text-color);
    border: none;
    background: none;
    transition: color 0.2s, background 0.2s;
  }
  .tab:hover { background: var(--secondary-background-color); }
  .tab.active {
    color: #2196f3;
    border-bottom: 2px solid #2196f3;
  }
  .content { padding: 20px; }
  /* --- dashboard --- */
  .device-section { margin-bottom: 28px; }
  .device-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--primary-text-color);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .card {
    background: var(--card-background-color, #fff);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.08));
  }
  .card-title {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--secondary-text-color);
    margin-bottom: 8px;
  }
  .speed-display {
    font-size: 3rem;
    font-weight: 700;
    line-height: 1;
    color: var(--primary-text-color);
  }
  .speed-unit {
    font-size: 1rem;
    color: var(--secondary-text-color);
    margin-left: 4px;
  }
  .row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--divider-color); }
  .row:last-child { border-bottom: none; }
  .row-label { flex: 1; color: var(--secondary-text-color); font-size: 0.88rem; }
  .row-value { font-weight: 600; color: var(--primary-text-color); font-size: 0.9rem; }
  .bar-wrap { height: 5px; background: var(--divider-color); border-radius: 3px; flex: 1; overflow: hidden; margin: 0 8px; }
  .bar { height: 100%; border-radius: 3px; transition: width 0.4s; }
  .no-device {
    text-align: center;
    padding: 40px 20px;
    color: var(--secondary-text-color);
    font-size: 1rem;
  }
  .no-device ha-icon { font-size: 3rem; display: block; margin-bottom: 12px; }
  /* --- flash tab --- */
  .flash-wrap { max-width: 640px; margin: 0 auto; }
  .flash-card {
    background: var(--card-background-color, #fff);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.08));
  }
  .flash-card h3 { margin: 0 0 10px; font-size: 1rem; color: var(--primary-text-color); }
  .flash-card ul, .flash-card ol { margin: 6px 0; padding-left: 20px; }
  .flash-card li { margin: 4px 0; font-size: 0.9rem; color: var(--secondary-text-color); }
  .flash-card a { color: #2196f3; }
  .info-banner {
    background: #e3f2fd;
    border-left: 4px solid #2196f3;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 0.9rem;
    color: #1565c0;
    margin-bottom: 16px;
  }
  .warn-banner {
    background: #fff8e1;
    border-left: 4px solid #ffc107;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 0.9rem;
    color: #795548;
    margin-bottom: 16px;
    display: none;
  }
  .warn-banner.visible { display: block; }
  esp-web-install-button { display: block; margin: 14px 0; }
  esp-web-install-button::part(button) {
    background: #2196f3;
    color: #fff;
    border: none;
    padding: 12px 24px;
    font-size: 1rem;
    border-radius: 6px;
    cursor: pointer;
    width: 100%;
  }
  esp-web-install-button::part(button):hover { background: #1976d2; }
  .flash-fallback {
    text-align: center;
    padding: 16px;
  }
  .flash-fallback a {
    display: inline-block;
    padding: 12px 24px;
    background: #2196f3;
    color: #fff;
    text-decoration: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 500;
  }
  .flash-fallback a:hover { background: #1976d2; }
  /* --- flash progress --- */
  .progress-section { margin-top: 16px; }
  .flash-status-text {
    font-size: 0.88rem;
    color: var(--secondary-text-color);
    min-height: 20px;
    margin-bottom: 6px;
  }
  .flash-status-text.ok  { color: #4caf50; font-weight: 600; }
  .flash-status-text.err { color: #f44336; font-weight: 600; }
  .progress-bar-wrap {
    height: 10px;
    background: var(--divider-color);
    border-radius: 5px;
    overflow: hidden;
    margin-bottom: 10px;
  }
  .progress-bar-fill {
    height: 100%;
    background: #2196f3;
    border-radius: 5px;
    width: 0%;
    transition: width 0.35s ease;
  }
  .flash-log {
    background: #1a1a2e;
    color: #c8d6e5;
    font-family: 'Roboto Mono', monospace;
    font-size: 0.80rem;
    padding: 10px 12px;
    border-radius: 6px;
    min-height: 72px;
    max-height: 210px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .log-entry        { margin: 2px 0; }
  .log-entry.info   { color: #c8d6e5; }
  .log-entry.ok     { color: #55efc4; }
  .log-entry.err    { color: #ff7675; }
  .log-entry.warn   { color: #fdcb6e; }
`;

/* -------------------------------------------------------------------------
 * Panel element
 * ---------------------------------------------------------------------- */
class FreematicsPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._panel = null;
    this._activeTab = "dashboard";
    this._initialized = false;
    this._flashRendered = false;
    this._dialogBodyObserver = null;
    this._currentAttrObserver = null;
    this.attachShadow({ mode: "open" });
  }

  disconnectedCallback() {
    if (this._dialogBodyObserver) {
      this._dialogBodyObserver.disconnect();
      this._dialogBodyObserver = null;
    }
    if (this._currentAttrObserver) {
      this._currentAttrObserver.disconnect();
      this._currentAttrObserver = null;
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
    } else {
      this._updateDashboard();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  /* ── entity discovery ───────────────────────────────────────────── */

  /**
   * Scan hass.states for sensor.freematics_one_*_speed entities and
   * return the list of unique entity prefixes, e.g.
   *   ["sensor.freematics_one_a1b2c3d4"]
   */
  _discoverDevices() {
    if (!this._hass) return [];
    const prefixes = new Set();
    for (const entityId of Object.keys(this._hass.states)) {
      const m = entityId.match(/^(sensor\.freematics_one_\w+?)_speed$/);
      if (m) prefixes.add(m[1]);
    }
    return [...prefixes];
  }

  _val(prefix, suffix, decimals = 1) {
    const state = this._hass && this._hass.states[`${prefix}_${suffix}`];
    if (!state) return "—";
    const v = parseFloat(state.state);
    if (isNaN(v)) return state.state;
    return decimals === 0 ? Math.round(v).toString() : v.toFixed(decimals);
  }

  _raw(prefix, suffix) {
    const state = this._hass && this._hass.states[`${prefix}_${suffix}`];
    if (!state) return null;
    const v = parseFloat(state.state);
    return isNaN(v) ? null : v;
  }

  /* ── full render (first time) ───────────────────────────────────── */
  _render() {
    const shadow = this.shadowRoot;
    shadow.innerHTML = `
      <style>${STYLES}</style>
      <div class="panel-header">
        <ha-icon class="panel-icon" icon="mdi:car-connected"></ha-icon>
        <div class="panel-title">Freematics ONE+</div>
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="dashboard">&#128250; Dashboard</button>
        <button class="tab" data-tab="flash">&#9889; Flash Firmware</button>
      </div>
      <div class="content" id="content-dashboard"></div>
      <div class="content" id="content-flash" style="display:none"></div>
    `;

    shadow.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => {
        shadow.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        btn.classList.add("active");
        this._activeTab = btn.dataset.tab;
        const dashEl  = shadow.getElementById("content-dashboard");
        const flashEl = shadow.getElementById("content-flash");
        if (this._activeTab === "dashboard") {
          dashEl.style.display  = "";
          flashEl.style.display = "none";
          this._renderDashboard();
        } else {
          dashEl.style.display  = "none";
          flashEl.style.display = "";
          this._renderFlash();
        }
      });
    });

    this._renderContent();
  }

  _renderContent() {
    if (this._activeTab === "dashboard") {
      this._renderDashboard();
    } else {
      this._renderFlash();
    }
  }

  /* ── Dashboard tab ─────────────────────────────────────────────── */
  _renderDashboard() {
    const el = this.shadowRoot.getElementById("content-dashboard");
    if (!el) return;

    const devices = this._discoverDevices();

    if (devices.length === 0) {
      el.innerHTML = `
        <div class="no-device">
          <ha-icon icon="mdi:car-off"></ha-icon>
          <strong>No Freematics device detected yet.</strong><br><br>
          Waiting for telemetry data from the device.<br>
          Make sure the firmware is configured with the correct webhook URL and the device is powered on.
        </div>
      `;
      return;
    }

    el.innerHTML = devices.map(prefix => this._deviceHTML(prefix)).join("");
  }

  _updateDashboard() {
    if (this._activeTab !== "dashboard") return;
    const el = this.shadowRoot.getElementById("content-dashboard");
    if (!el) return;
    this._renderDashboard();
  }

  _speedColor(speed) {
    if (speed === null) return "#9e9e9e";
    if (speed === 0) return "#4caf50";
    if (speed < 80) return "#2196f3";
    if (speed < 120) return "#ff9800";
    return "#f44336";
  }

  _batteryColor(battery) {
    if (battery === null) return "#9e9e9e";
    if (battery >= 13) return "#4caf50";
    if (battery >= 12) return "#ff9800";
    return "#f44336";
  }

  _deviceHTML(prefix) {
    const speed    = this._raw(prefix, "speed");
    const rpm      = this._raw(prefix, "rpm");
    const battery  = this._raw(prefix, "battery");
    const signal   = this._raw(prefix, "signal");
    const coolant  = this._raw(prefix, "coolant_temp");
    const load     = this._raw(prefix, "engine_load");
    const throttle = this._raw(prefix, "throttle");
    const lat      = this._raw(prefix, "lat");
    const lng      = this._raw(prefix, "lng");
    const alt      = this._raw(prefix, "alt");
    const gpsSpd   = this._raw(prefix, "gps_speed");
    const sats     = this._raw(prefix, "satellites");
    const accX     = this._raw(prefix, "acc_x");
    const accY     = this._raw(prefix, "acc_y");
    const accZ     = this._raw(prefix, "acc_z");
    const intakeT  = this._raw(prefix, "intake_temp");
    const fuelP    = this._raw(prefix, "fuel_pressure");
    const heading  = this._raw(prefix, "heading");

    const deviceLabel = prefix.replace("sensor.", "").replace(/_/g, " ");
    const speedColor = this._speedColor(speed);
    const battColor  = this._batteryColor(battery);

    const rpmPct   = rpm   !== null ? Math.min((rpm / 7000) * 100, 100) : 0;
    const loadPct  = load  !== null ? Math.min(load, 100) : 0;
    const thrPct   = throttle !== null ? Math.min(throttle, 100) : 0;

    const mapsUrl  = lat !== null && lng !== null
      ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}&zoom=15`
      : null;

    return `
      <div class="device-section">
        <div class="device-title">
          <ha-icon icon="mdi:car-connected" style="color:#2196f3"></ha-icon>
          ${deviceLabel}
          ${signal !== null ? `<span style="font-size:.8rem;color:var(--secondary-text-color);margin-left:auto;"><ha-icon icon="mdi:signal"></ha-icon> ${signal.toFixed(0)} dBm</span>` : ""}
        </div>

        <div class="grid-2">
          <!-- Speed card -->
          <div class="card">
            <div class="card-title">Speed</div>
            <div style="display:flex;align-items:baseline">
              <div class="speed-display" style="color:${speedColor}">${speed !== null ? Math.round(speed) : "—"}</div>
              <div class="speed-unit">km/h</div>
            </div>
            ${gpsSpd !== null ? `<div style="font-size:.82rem;color:var(--secondary-text-color);margin-top:4px">GPS: ${gpsSpd.toFixed(1)} km/h</div>` : ""}
          </div>

          <!-- Battery card -->
          <div class="card">
            <div class="card-title">Battery</div>
            <div style="font-size:2rem;font-weight:700;color:${battColor}">${battery !== null ? battery.toFixed(2) + " V" : "—"}</div>
            <div style="font-size:.82rem;color:var(--secondary-text-color);margin-top:4px">
              ${battery !== null ? (battery >= 13 ? "✓ Good" : battery >= 12 ? "⚠ Low" : "✗ Critical") : ""}
            </div>
          </div>

          <!-- Engine card -->
          <div class="card">
            <div class="card-title">Engine</div>
            <div class="row">
              <span class="row-label">RPM</span>
              <div class="bar-wrap"><div class="bar" style="width:${rpmPct}%;background:#2196f3"></div></div>
              <span class="row-value">${rpm !== null ? Math.round(rpm) : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Load</span>
              <div class="bar-wrap"><div class="bar" style="width:${loadPct}%;background:${loadPct > 80 ? "#f44336" : "#ff9800"}"></div></div>
              <span class="row-value">${load !== null ? load.toFixed(1) + " %" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Throttle</span>
              <div class="bar-wrap"><div class="bar" style="width:${thrPct}%;background:#9c27b0"></div></div>
              <span class="row-value">${throttle !== null ? throttle.toFixed(1) + " %" : "—"}</span>
            </div>
          </div>

          <!-- Temps / Pressure card -->
          <div class="card">
            <div class="card-title">Temperature &amp; Pressure</div>
            <div class="row">
              <span class="row-label">Coolant</span>
              <span class="row-value">${coolant !== null ? coolant.toFixed(1) + " °C" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Intake</span>
              <span class="row-value">${intakeT !== null ? intakeT.toFixed(1) + " °C" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Fuel Pressure</span>
              <span class="row-value">${fuelP !== null ? fuelP.toFixed(0) + " kPa" : "—"}</span>
            </div>
          </div>

          <!-- GPS card -->
          <div class="card">
            <div class="card-title">GPS</div>
            <div class="row">
              <span class="row-label">Latitude</span>
              <span class="row-value">${lat !== null ? lat.toFixed(5) : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Longitude</span>
              <span class="row-value">${lng !== null ? lng.toFixed(5) : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Altitude</span>
              <span class="row-value">${alt !== null ? alt.toFixed(0) + " m" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Heading</span>
              <span class="row-value">${heading !== null ? heading.toFixed(0) + " °" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Satellites</span>
              <span class="row-value">${sats !== null ? Math.round(sats) : "—"}</span>
            </div>
            ${mapsUrl ? `<div style="margin-top:8px"><a href="${mapsUrl}" target="_blank" rel="noopener" style="color:#2196f3;font-size:.85rem">&#128204; Open in map ↗</a></div>` : ""}
          </div>

          <!-- Accelerometer card -->
          <div class="card">
            <div class="card-title">Accelerometer</div>
            <div class="row">
              <span class="row-label">X</span>
              <span class="row-value">${accX !== null ? accX.toFixed(2) + " m/s²" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Y</span>
              <span class="row-value">${accY !== null ? accY.toFixed(2) + " m/s²" : "—"}</span>
            </div>
            <div class="row">
              <span class="row-label">Z</span>
              <span class="row-value">${accZ !== null ? accZ.toFixed(2) + " m/s²" : "—"}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /* ── Flash Firmware tab ─────────────────────────────────────────── */
  _renderFlash() {
    const el = this.shadowRoot.getElementById("content-flash");
    if (!el) return;

    // Render only once: preserves the esp-web-install-button DOM node so
    // the underlying Web Serial port is never orphaned between tab switches,
    // which prevents the "The port is already open" error on re-click.
    if (this._flashRendered) return;
    this._flashRendered = true;

    const hasSerial = "serial" in navigator;

    el.innerHTML = `
      <div class="flash-wrap">
        <div class="info-banner">
          &#9889; <strong>Browser Flasher</strong> – Flash firmware directly from your browser
          to the Freematics ONE+ connected to <strong>your computer's USB port</strong>.
          Your computer does not need to be the Home Assistant server.
        </div>

        <div id="no-serial-warn" class="warn-banner${hasSerial ? "" : " visible"}">
          &#9888; <strong>Web Serial API not available.</strong><br>
          Please open this page in <strong>Google Chrome</strong> or
          <strong>Microsoft Edge</strong> (version 89 or newer).<br>
          Alternatively, use the <em>Flash Firmware via WiFi OTA</em> button in
          Home Assistant's device page.
        </div>

        <div class="flash-card">
          <h3>&#128268; Requirements</h3>
          <ul>
            <li>Google Chrome or Microsoft Edge (version 89+)</li>
            <li>Freematics ONE+ connected via USB to <em>this computer</em></li>
            <li>USB–Serial driver installed:
              <ul>
                <li><a href="https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers" target="_blank" rel="noopener">CP210x driver (Silicon Labs)</a></li>
                <li><a href="https://www.wch-ic.com/downloads/CH341SER_EXE.html" target="_blank" rel="noopener">CH340 driver (WCH)</a></li>
              </ul>
            </li>
          </ul>
        </div>

        ${hasSerial ? `
        <div class="flash-card" id="flash-action">
          <h3>&#9889; Flash Firmware</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 10px">
            Click the button below. A browser dialog will open so you can
            <strong>select the COM port</strong> of the Freematics ONE+.<br>
            Look for: <code style="background:var(--secondary-background-color);padding:1px 4px;border-radius:3px">CP2102</code>,
            <code style="background:var(--secondary-background-color);padding:1px 4px;border-radius:3px">CH340</code>,
            or a similar USB-Serial device.
          </p>
          <div id="esp-container">
            <p style="color:var(--secondary-text-color);font-size:.9rem">Loading flash tool…</p>
          </div>
          <div class="progress-section" id="flash-progress" style="display:none">
            <div class="flash-status-text" id="flash-status-text"></div>
            <div class="progress-bar-wrap">
              <div class="progress-bar-fill" id="progress-bar-fill"></div>
            </div>
            <div class="flash-log" id="flash-log"></div>
          </div>
          <ol style="font-size:.9rem;color:var(--secondary-text-color)">
            <li>Click <em>Connect &amp; Flash Firmware</em></li>
            <li>Select the Freematics ONE+ COM port from the browser dialog</li>
            <li>Firmware flashes automatically (~30 s)</li>
            <li>Device restarts and begins sending data to Home Assistant</li>
          </ol>
        </div>
        ` : `
        <div class="flash-card">
          <h3>WiFi OTA / Server-side Flash</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color)">
            Use the <strong>Flash Firmware via WiFi OTA</strong> or
            <strong>Flash Firmware via Serial</strong> buttons on the
            Freematics ONE+ device page in Home Assistant, or open the
            standalone flasher page in Chrome / Edge:
          </p>
          <div class="flash-fallback">
            <a href="/api/freematics/flasher" target="_blank" rel="noopener">
              &#9889; Open Standalone Flasher Page
            </a>
          </div>
        </div>
        `}

        <div class="flash-card">
          <h3>&#128221; WiFi OTA (AP Mode)</h3>
          <ol>
            <li>Power on the Freematics ONE+ (factory or freshly flashed device)</li>
            <li>Connect your device to WiFi network <strong>TELELOGGER</strong> (password: <strong>PASSWORD</strong>)</li>
            <li>Set <code style="background:var(--secondary-background-color);padding:1px 4px;border-radius:3px">192.168.4.1</code> as the Device IP in the integration settings</li>
            <li>Press <strong>Flash Firmware via WiFi OTA</strong> in the device page</li>
          </ol>
        </div>
      </div>
    `;

    if (hasSerial) {
      this._loadEspWebTools();
    }
  }

  _loadEspWebTools() {
    const shadow = this.shadowRoot;
    const container = shadow.getElementById("esp-container");
    if (!container) return;

    // Load esp-web-tools and insert the install button
    if (!customElements.get("esp-web-install-button")) {
      const script = document.createElement("script");
      script.type = "module";
      script.src = "https://unpkg.com/esp-web-tools@10/dist/web/install-button.js?module";
      script.onload = () => this._insertInstallButton(container);
      document.head.appendChild(script);
    } else {
      this._insertInstallButton(container);
    }
  }

  _insertInstallButton(container) {
    container.innerHTML = `
      <esp-web-install-button manifest="/api/freematics/manifest.json">
        <button slot="activate" style="
          background:#2196f3;color:#fff;border:none;padding:12px 24px;
          font-size:1rem;border-radius:6px;cursor:pointer;width:100%;
          font-family:inherit;margin-bottom:10px;
        ">
          &#9889; Connect &amp; Flash Firmware
        </button>
        <span slot="unsupported" style="color:#f44336;font-size:.9rem">
          &#9888; Web Serial is not supported in this browser. Please use Chrome or Edge 89+.
        </span>
      </esp-web-install-button>
    `;
    this._watchInstallDialog();
  }

  /* ── Install-dialog observer (progress bar + log) ────────────────── */

  /**
   * esp-web-tools v10 does NOT fire state-changed on <esp-web-install-button>.
   * The actual flash work happens inside <ewt-install-dialog> which is
   * appended to document.body.  We watch for it with a MutationObserver and
   * track its 'state' attribute to update our progress UI.
   */
  _watchInstallDialog() {
    if (this._dialogBodyObserver) return;
    this._dialogBodyObserver = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === 1 && node.localName === "ewt-install-dialog") {
            this._onInstallDialogAdded(node);
          }
        }
        for (const node of mutation.removedNodes) {
          if (node.nodeType === 1 && node.localName === "ewt-install-dialog") {
            if (this._currentAttrObserver) {
              this._currentAttrObserver.disconnect();
              this._currentAttrObserver = null;
            }
          }
        }
      }
    });
    this._dialogBodyObserver.observe(document.body, { childList: true });
  }

  _onInstallDialogAdded(dialog) {
    const shadow = this.shadowRoot;
    const progressSection = shadow.getElementById("flash-progress");
    const logEl = shadow.getElementById("flash-log");
    if (!progressSection) return;

    // Reset log and reveal the progress section
    if (logEl) logEl.innerHTML = "";
    progressSection.style.display = "block";
    this._updateFlashUI("Connecting to device…", "", "#2196f3", 5);
    this._appendFlashLog("info", "Connecting to device…");

    // Watch for dialog state attribute changes
    const attrObserver = new MutationObserver(() => {
      const state = dialog.getAttribute("state");
      if (state) this._onDialogStateChanged(state);
    });
    attrObserver.observe(dialog, { attributes: true, attributeFilter: ["state"] });
    this._currentAttrObserver = attrObserver;

    // Read the initial state if Lit has already set it
    const initState = dialog.getAttribute("state");
    if (initState) this._onDialogStateChanged(initState);

    // Finalize when the dialog closes
    dialog.addEventListener("closed", () => {
      attrObserver.disconnect();
      this._currentAttrObserver = null;
      const lastState = dialog.getAttribute("state");
      if (lastState === "ERROR") {
        this._updateFlashUI("✗ Error — see the dialog for details.", "err", "#f44336", 0);
        this._appendFlashLog("err", "Operation ended with an error.");
      } else {
        this._updateFlashUI("Flash session ended.", "ok", "#4caf50", 100);
        this._appendFlashLog("ok", "Dialog closed.");
      }
    }, { once: true });
  }

  _onDialogStateChanged(state) {
    const MAP = {
      DASHBOARD: { pct: 20,  label: "Connected — follow the dialog to install…", cls: "info", color: "#2196f3" },
      ASK_ERASE: { pct: 30,  label: "Awaiting erase confirmation in dialog…",    cls: "info", color: "#ff9800" },
      INSTALL:   { pct: 55,  label: "Installing firmware… (~30 s)",              cls: "info", color: "#2196f3" },
      PROVISION: { pct: 90,  label: "Configuring Wi-Fi…",                        cls: "info", color: "#2196f3" },
      LOGS:      { pct: 100, label: "✓ Installation complete.",                  cls: "ok",   color: "#4caf50" },
      ERROR:     { pct: 0,   label: "✗ Error — see dialog for details.",         cls: "err",  color: "#f44336" },
    };
    const info = MAP[state] || { pct: 0, label: state, cls: "info", color: "#2196f3" };
    this._updateFlashUI(info.label, info.cls !== "info" ? info.cls : "", info.color, info.pct);
    this._appendFlashLog(info.cls, info.label);
  }

  _updateFlashUI(label, cls, barColor, pct) {
    const shadow = this.shadowRoot;
    const statusText   = shadow.getElementById("flash-status-text");
    const progressFill = shadow.getElementById("progress-bar-fill");
    if (statusText) {
      statusText.textContent = label;
      statusText.className   = `flash-status-text${cls ? " " + cls : ""}`;
    }
    if (progressFill) {
      progressFill.style.width      = `${pct}%`;
      progressFill.style.background = barColor;
    }
  }

  _appendFlashLog(cls, text) {
    const shadow = this.shadowRoot;
    const logEl = shadow.getElementById("flash-log");
    if (!logEl) return;
    const ts = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className   = `log-entry ${cls}`;
    entry.textContent = `[${ts}] ${text}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
  }
}

customElements.define("freematics-panel", FreematicsPanel);

console.info(
  `%c FREEMATICS-PANEL %c v${PANEL_VERSION} `,
  "background:#2196f3;color:#fff;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px",
  "background:#1565c0;color:#fff;padding:2px 6px;border-radius:0 4px 4px 0"
);
