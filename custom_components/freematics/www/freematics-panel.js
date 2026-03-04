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

const PANEL_VERSION = "1.10.0";

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
  .ota-log {
    background: #1a1a2e;
    color: #c8d6e5;
    font-family: 'Roboto Mono', monospace;
    font-size: 0.80rem;
    padding: 10px 12px;
    border-radius: 6px;
    min-height: 60px;
    max-height: 180px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    margin-top: 8px;
  }
`;

// Module-level guard: tracks whether the esp-web-tools <script> tag has
// already been appended to the document.  Using customElements.get() alone
// is not sufficient because HA's scoped-custom-element-registry polyfill can
// make that call return undefined even when the element is already globally
// registered, which would cause the script to be loaded a second time and
// trigger a duplicate-definition error for Material Design sub-elements such
// as `md-focus-ring`.
let _espToolsLoaded = false;

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
    this._shadowDialogObserver = null;
    this._progressPollTimer = null;
    this._provisioningManifestUrl = null;
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    // Re-attach the body observer if the Flash tab was already rendered and
    // the observer was torn down by a previous disconnectedCallback (e.g.
    // HA sidebar navigation away and back).
    if (this._flashRendered) {
      this._watchInstallDialog();
    }
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
    if (this._shadowDialogObserver) {
      this._shadowDialogObserver.disconnect();
      this._shadowDialogObserver = null;
    }
    if (this._progressPollTimer) {
      clearInterval(this._progressPollTimer);
      this._progressPollTimer = null;
    }
    if (this._flashStallTimer) {
      clearTimeout(this._flashStallTimer);
      this._flashStallTimer = null;
    }
    if (this._dialogStallRef) {
      clearTimeout(this._dialogStallRef.timer);
      this._dialogStallRef = null;
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
    const cs = "background:var(--secondary-background-color);padding:1px 4px;border-radius:3px";

    el.innerHTML = `
      <div class="flash-wrap">

        <!-- ── Provisioning info banner ───────────────────────────── -->
        <div class="info-banner">
          &#128274; <strong>Auto-Provisioning</strong> – When you use the
          <em>Connect &amp; Flash Firmware</em> button below, the integration
          automatically embeds your WiFi credentials, cellular APN, and HA
          server address in the device settings (<em>NVS</em>) during the
          same flash operation — no manual configuration required after flashing.
        </div>

        <div id="no-serial-warn" class="warn-banner${hasSerial ? "" : " visible"}">
          &#9888; <strong>Web Serial API not available.</strong><br>
          Please open this page in <strong>Google Chrome</strong> or
          <strong>Microsoft Edge</strong> (version 89 or newer).<br>
          The Web Serial API also requires a <strong>secure HTTPS connection with a trusted
          certificate</strong>. When accessing Home Assistant via a local IP address, use
          <a href="https://www.nabucasa.com/" target="_blank" rel="noopener" style="color:#795548">Nabu Casa</a>
          (e.g. <code style="${cs}">*.ui.nabu.casa</code>)
          or use the <em>Manual Flash</em> section below.
        </div>

        <!-- ── Requirements ───────────────────────────────────────── -->
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

        <!-- ── Browser flasher (Web Serial) ──────────────────────── -->
        ${hasSerial ? `
        <div class="flash-card" id="flash-action">
          <h3>&#9889; Flash Firmware (USB / Web Serial)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 10px">
            Click the button below. A browser dialog will open so you can
            <strong>select the COM port</strong> of the Freematics ONE+.<br>
            Look for: <code style="${cs}">CP2102</code>,
            <code style="${cs}">CH340</code>, or a similar USB-Serial device.
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
            <li>Firmware + settings flash automatically (~45 s)</li>
            <li>Device restarts and connects to your WiFi / sends data to Home Assistant</li>
          </ol>
        </div>
        ` : `
        <div class="flash-card">
          <h3>&#9889; Browser / Web Serial not available</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color)">
            Use the standalone flasher page in Chrome / Edge or use one of the
            manual methods below.
          </p>
          <div class="flash-fallback">
            <a href="/api/freematics/flasher" target="_blank" rel="noopener">
              &#9889; Open Standalone Flasher Page
            </a>
          </div>
        </div>
        `}

        <!-- ── WiFi OTA (AP mode) ─────────────────────────────────── -->
        <div class="flash-card">
          <h3>&#128221; WiFi OTA (AP Mode)</h3>
          <ol style="font-size:.9rem;color:var(--secondary-text-color);margin:0">
            <li>Power on the Freematics ONE+ (factory or freshly flashed device)</li>
            <li>Connect your computer to WiFi <strong>TELELOGGER</strong> (password: <strong>PASSWORD</strong>)</li>
            <li>Set <code style="${cs}">192.168.4.1</code> as the Device IP in the integration settings</li>
            <li>Press <strong>Flash Firmware via WiFi OTA</strong> on the device page in HA</li>
          </ol>
        </div>

        <!-- ── WiFi OTA (Local network) ──────────────────────────── -->
        <div class="flash-card">
          <h3>&#128246; WiFi OTA (Local Network)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 10px">
            Flash when the Freematics ONE+ is already connected to your <strong>local WiFi
            network</strong> and reachable from the Home Assistant server.
          </p>
          <ol style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 12px">
            <li>Ensure the device is online and the HA server can reach its IP</li>
            <li>Enter the device's local IP address (and port if not 80)</li>
            <li>Click <em>Flash via WiFi OTA</em> — takes ~30 s</li>
          </ol>
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
            <input id="ota-ip-input" type="text" placeholder="192.168.x.x" style="
              flex:1;min-width:120px;padding:8px 10px;
              border:1px solid var(--divider-color);border-radius:6px;
              background:var(--primary-background-color);
              color:var(--primary-text-color);font-size:.9rem;font-family:inherit;
            ">
            <input id="ota-port-input" type="number" placeholder="80" value="80" min="1" max="65535" style="
              width:72px;padding:8px 10px;
              border:1px solid var(--divider-color);border-radius:6px;
              background:var(--primary-background-color);
              color:var(--primary-text-color);font-size:.9rem;font-family:inherit;
            ">
          </div>
          <button id="wifi-ota-btn" style="
            background:#2196f3;color:#fff;border:none;padding:10px 20px;
            font-size:.95rem;border-radius:6px;cursor:pointer;
            font-family:inherit;margin-bottom:8px;
          ">&#128246; Flash via WiFi OTA</button>
          <div id="wifi-ota-status" style="display:none;font-size:.88rem;margin-top:4px"></div>
          <div class="ota-log" id="ota-log" style="display:none"></div>
        </div>

        <!-- ── Manual flash (esptool / Freematics Builder) ─────────── -->
        <div class="flash-card">
          <h3>&#128187; Manual Flash (Windows, Linux, macOS)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            Use this method when Chrome / Edge is not available or you prefer an
            external tool.
          </p>

          <!-- Download box -->
          <div style="background:var(--secondary-background-color);border-radius:6px;padding:10px 14px;margin-bottom:12px">
            <div style="font-weight:600;font-size:.9rem;margin-bottom:6px">&#11015; Download files</div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
              <div>
                <a id="dl-flash-image" href="#" download="flash_image.bin"
                   style="color:#2196f3;font-size:.95rem;font-weight:600">
                  &#11015; flash_image.bin
                </a>
                <span style="color:var(--secondary-text-color);font-size:.82rem">
                  &nbsp;— Partition table&nbsp;+&nbsp;NVS&nbsp;+&nbsp;firmware, for <strong>esptool</strong> at offset <code style="${cs}">0x8000</code>
                </span>
                <div id="nvs-dl-status" style="font-size:.82rem;color:var(--secondary-text-color);margin-top:2px">
                  &#9203; Generating settings file…
                </div>
              </div>
              <div style="margin-top:4px">
                <a id="dl-firmware" href="/api/freematics/firmware.bin" download="telelogger.bin"
                   style="color:#2196f3;font-size:.85rem;font-weight:600">
                  &#11015; telelogger.bin
                </a>
                <span style="color:var(--secondary-text-color);font-size:.82rem">
                  &nbsp;— firmware only, for <strong>Freematics Builder</strong> at its default offset
                </span>
              </div>
            </div>

            <!-- flash_image.bin info box -->
            <div style="margin-top:8px;background:var(--primary-background-color);border-radius:4px;padding:8px 10px;font-size:.82rem;color:var(--secondary-text-color)">
              <strong style="color:var(--primary-text-color)">&#8505; What flash_image.bin contains (offset&nbsp;0x8000)</strong><br>
              <table style="margin-top:4px;border-collapse:collapse;width:100%">
                <tr>
                  <td style="padding:2px 8px 2px 0;white-space:nowrap">Offset <code style="${cs}">0x8000</code></td>
                  <td>Partition table (huge_app scheme, 4 KB) — ensures the correct partition layout</td>
                </tr>
                <tr>
                  <td style="padding:2px 8px 2px 0;white-space:nowrap">Offset <code style="${cs}">0x9000</code></td>
                  <td>NVS settings (20 KB) — your WiFi, server and webhook settings,
                      <em>generated fresh from the integration&rsquo;s current configuration</em></td>
                </tr>
                <tr>
                  <td style="padding:2px 8px 2px 0;white-space:nowrap">Offset <code style="${cs}">0xE000</code></td>
                  <td>OTA-data placeholder (8 KB, 0xFF — boots app at 0x10000)</td>
                </tr>
                <tr>
                  <td style="padding:2px 8px 2px 0;white-space:nowrap">Offset <code style="${cs}">0x10000</code></td>
                  <td>Application firmware (telelogger.bin, pre-compiled, flash mode DIO)</td>
                </tr>
              </table>
              <p style="margin:6px 0 0">
                The bootloader at <code style="${cs}">0x1000</code> is <strong>not overwritten</strong> —
                the factory-programmed one remains intact.
              </p>
              <p style="margin:4px 0 0;color:#e65100">
                &#9888; <strong>flash_image.bin cannot be used with the Freematics Builder.</strong>
                The Builder writes binaries at the app partition offset (0x10000), which would
                place partition-table data where firmware belongs and cause a restart loop.
                Use esptool (Option A) instead.
              </p>
            </div>

            <!-- Advanced: NVS only -->
            <details style="margin-top:8px">
              <summary style="cursor:pointer;font-size:.82rem;color:var(--secondary-text-color)">
                Advanced: download NVS settings file separately
              </summary>
              <div style="margin-top:6px">
                <a id="dl-nvs" href="#" download="config_nvs.bin"
                   style="color:#2196f3;font-size:.85rem">
                  &#11015; config_nvs.bin <small>(settings only, offset 0x9000)</small>
                </a>
              </div>
              <p style="font-size:.8rem;color:var(--secondary-text-color);margin:4px 0 0">
                &#9888; Flash <em>both</em> telelogger.bin and config_nvs.bin when using
                separate downloads — flashing only config_nvs.bin without updating the
                firmware may cause a boot loop on devices with older firmware.
              </p>
            </details>
          </div>

          <details style="margin-bottom:10px">
            <summary style="cursor:pointer;font-weight:600;font-size:.9rem;padding:4px 0">
              &#128187; Option A – esptool.py (Windows / Linux / macOS)
            </summary>
            <ol style="font-size:.88rem;color:var(--secondary-text-color);margin:8px 0 0 0">
              <li>Install Python and esptool:
                <pre style="background:var(--primary-background-color);padding:5px 8px;border-radius:4px;font-size:.82rem;margin:3px 0;overflow-x:auto">pip install esptool</pre>
              </li>
              <li>Connect the device via USB, find the COM port (Windows: Device Manager → Ports, e.g. <code style="${cs}">COM3</code>; Linux: <code style="${cs}">/dev/ttyUSB0</code>)</li>
              <li>Flash with a single command (esptool auto-detects the port; add <code style="${cs}">--port COM3</code> if it is not found):
                <pre style="background:var(--primary-background-color);padding:5px 8px;border-radius:4px;font-size:.82rem;margin:3px 0;overflow-x:auto">python -m esptool write-flash 0x8000 flash_image.bin</pre>
              </li>
            </ol>
          </details>

          <details style="margin-bottom:10px">
            <summary style="cursor:pointer;font-weight:600;font-size:.9rem;padding:4px 0">
              &#128268; Option B – Freematics Builder (Windows)
            </summary>
            <p style="font-size:.88rem;color:var(--secondary-text-color);margin:6px 0 4px">
              The Freematics Builder flashes <strong>firmware only</strong>.
              After flashing, use the <strong>browser-based flasher</strong> above to provision
              your WiFi and server settings.
            </p>
            <ol style="font-size:.88rem;color:var(--secondary-text-color);margin:4px 0 0 0">
              <li>Download <code style="${cs}">telelogger.bin</code> using the link above</li>
              <li>Download and open <a href="https://freematics.com/pages/products/freematics-one-plus-model-b/" target="_blank" rel="noopener" style="color:#2196f3">Freematics Builder</a></li>
              <li>Connect the Freematics ONE+ via USB</li>
              <li>In Freematics Builder select <strong>Custom Binary</strong> and choose the downloaded <code style="${cs}">telelogger.bin</code></li>
              <li>Click Flash — the device reboots with the new firmware</li>
              <li>Now use the <strong>&#9889; Browser Flash</strong> section above to provision your WiFi and server settings</li>
            </ol>
            <p style="font-size:.82rem;color:var(--secondary-text-color);margin:6px 0 0">
              &#8505; The Freematics Builder is available from the
              <a href="https://freematics.com/pages/products/freematics-one-plus-model-b/" target="_blank" rel="noopener" style="color:#2196f3">Freematics product page</a>.
            </p>
          </details>

          <details>
            <summary style="cursor:pointer;font-weight:600;font-size:.9rem;padding:4px 0">
              &#9889; Option C – Arduino IDE (Windows / Linux / macOS)
            </summary>
            <ol style="font-size:.88rem;color:var(--secondary-text-color);margin:8px 0 0 0">
              <li>Install <a href="https://www.arduino.cc/en/software" target="_blank" rel="noopener" style="color:#2196f3">Arduino IDE 2.x</a></li>
              <li>Add ESP32 board support: <em>File → Preferences → Board Manager URLs</em> → add <code style="${cs}">https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json</code>, then install <em>esp32 by Espressif</em></li>
              <li>Select board: <em>Tools → Board → ESP32 Arduino → ESP32 Dev Module</em></li>
              <li>Select port: <em>Tools → Port → COM3</em> (or your port)</li>
              <li>Flash <code style="${cs}">flash_image.bin</code> at offset <code style="${cs}">0x8000</code> using esptool (see Option A above)</li>
            </ol>
          </details>
        </div>

        <!-- ── Device ID explanation ──────────────────────────────── -->
        <div class="flash-card">
          <h3>&#128279; About the Device ID</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0">
            The <strong>Device ID</strong> shown in the serial log (e.g. <code style="${cs}">ZKUCQXJF</code>)
            is generated from the ESP32 chip's unique hardware MAC address.
            It is not configurable and will always be the same for a given device.
            This ID is only used for legacy Freematics Hub identification — it is
            <em>not</em> the Home Assistant webhook ID.
          </p>
        </div>

        <!-- ── Datalogger / HTTPD info ────────────────────────────── -->
        <div class="flash-card">
          <h3>&#128202; Built-in Data Viewer (Datalogger / HTTPD)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            The firmware includes a built-in HTTP data server
            (<code style="${cs}">ENABLE_HTTPD=1</code>) that lets you view live data
            directly on the device via a web browser. This is useful for
            diagnosing connection issues in the field.
          </p>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            <strong>Available endpoints when HTTPD is enabled:</strong>
          </p>
          <ul style="font-size:.88rem;color:var(--secondary-text-color);margin:0 0 8px">
            <li><code style="${cs}">/api/info</code> – device info (chip, firmware, uptime)</li>
            <li><code style="${cs}">/api/live</code> – live sensor data (OBD, GPS, MEMS)</li>
            <li><code style="${cs}">/api/control?cmd=…</code> – send control commands</li>
            <li><code style="${cs}">/api/list</code> – list log files on SD card</li>
            <li><code style="${cs}">/api/log/&lt;n&gt;</code> – download raw CSV log file</li>
          </ul>
          <p style="font-size:.88rem;color:#ff9800;margin:0">
            &#9888; The pre-compiled binary has HTTPD <strong>disabled</strong> by default.
            To enable it, compile from source with
            <code style="${cs}">ENABLE_HTTPD=1</code> in
            <code style="${cs}">firmware_v5/telelogger/config.h</code>
            and flash the resulting binary.
          </p>
        </div>

      </div>
    `;

    // Attach WiFi OTA button event listener
    const wifiOtaBtn = el.querySelector("#wifi-ota-btn");
    if (wifiOtaBtn) {
      wifiOtaBtn.addEventListener("click", async () => {
        const shadow = this.shadowRoot;
        const ipInput  = shadow.getElementById("ota-ip-input");
        const portInput = shadow.getElementById("ota-port-input");
        const statusDiv = shadow.getElementById("wifi-ota-status");
        const otaLog    = shadow.getElementById("ota-log");

        const ip   = (ipInput  ? ipInput.value  : "").trim();
        const port = portInput ? (parseInt(portInput.value) || 80) : 80;

        const showStatus = (color, html) => {
          if (!statusDiv) return;
          statusDiv.style.display = "block";
          statusDiv.innerHTML = `<span style="color:${color}">${html}</span>`;
        };

        const addLog = (cls, text) => this._appendOtaLog(cls, text);

        if (!ip) {
          showStatus("#ff9800", "&#9888; Please enter the device IP address.");
          return;
        }

        // Reset log panel and show it
        if (otaLog) { otaLog.innerHTML = ""; otaLog.style.display = "block"; }
        wifiOtaBtn.disabled = true;
        wifiOtaBtn.textContent = "⏳ Uploading…";
        showStatus("#2196f3", "&#9203; Uploading firmware… (may take ~30 s)");
        addLog("info", `Starting WiFi OTA flash to ${ip}:${port}…`);

        try {
          addLog("info", "Sending request to HA server…");
          const result = await this._hass.callApi("POST", "freematics/wifi_ota", {
            device_ip: ip,
            device_port: port,
          });

          // Render server-side log lines first
          if (result && Array.isArray(result.log)) {
            for (const line of result.log) {
              const cls = line.includes("[ERROR]") ? "err"
                        : line.includes("[OK]")    ? "ok"
                        : "info";
              addLog(cls, line);
            }
          }

          if (result && result.ok) {
            const msg = result.message || "Flash successful!";
            showStatus("#4caf50", `&#10003; ${msg}`);
            addLog("ok", "✓ OTA flash completed successfully.");
          } else {
            const msg = (result && result.message) ? result.message : "OTA flash failed.";
            showStatus("#f44336", `&#10007; OTA flash failed: ${msg}`);
            addLog("err", `✗ ${msg}`);
          }
        } catch (err) {
          const msg = (err && err.message) ? err.message : String(err);
          showStatus("#f44336", `&#10007; OTA flash failed: ${msg}`);
          addLog("err", `✗ ${msg}`);
        } finally {
          wifiOtaBtn.disabled = false;
          wifiOtaBtn.textContent = "📶 Flash via WiFi OTA";
        }
      });
    }

    // Fetch provisioning token and update NVS download link + esp-web-tools manifest
    this._fetchProvisioningToken(el);

    if (hasSerial) {
      this._loadEspWebTools();
    }
  }

  async _fetchProvisioningToken(el) {
    const nvsStatus      = el ? el.querySelector("#nvs-dl-status") : null;
    const flashImageLink = el ? el.querySelector("#dl-flash-image") : null;
    const nvsLink        = el ? el.querySelector("#dl-nvs") : null;

    try {
      const result = await this._hass.callApi("GET", "freematics/provisioning_token");
      if (result && result.token) {
        this._provisioningManifestUrl = result.manifest_url || "/api/freematics/manifest.json";

        // Combined single-file flash image (PT + NVS + firmware, offset 0x8000)
        const flashImageUrl = result.flash_image_url ||
          `/api/freematics/flash_image.bin?token=${result.token}`;
        if (flashImageLink) {
          flashImageLink.href = flashImageUrl;
        }

        // NVS-only download (for advanced use / browser flash)
        const nvsUrl = result.nvs_url ||
          `/api/freematics/config_nvs.bin?token=${result.token}`;
        if (nvsLink) {
          nvsLink.href = nvsUrl;
        }

        if (nvsStatus) {
            nvsStatus.innerHTML =
            "&#10003; File ready — download link active for 5 minutes. " +
            "<em>Generated fresh from your current settings.</em>";
          nvsStatus.style.color = "var(--success-color, #4caf50)";
        }
        // If esp-web-tools install button is already rendered, update its manifest attribute
        const installBtn = this.shadowRoot.querySelector("esp-web-install-button");
        if (installBtn) {
          installBtn.setAttribute("manifest", this._provisioningManifestUrl);
        }
      }
    } catch (e) {
      if (nvsStatus) {
        nvsStatus.textContent = "⚠ Could not generate settings file — no integration configured.";
        nvsStatus.style.color = "#ff9800";
      }
      if (flashImageLink) {
        flashImageLink.style.opacity = "0.4";
        flashImageLink.style.pointerEvents = "none";
      }
      if (nvsLink) {
        nvsLink.style.opacity = "0.4";
        nvsLink.style.pointerEvents = "none";
      }
    }
  }


  _loadEspWebTools() {
    const shadow = this.shadowRoot;
    const container = shadow.getElementById("esp-container");
    if (!container) return;

    // Load esp-web-tools and insert the install button.  Guard with both
    // customElements.get() and the module-level _espToolsLoaded flag to
    // handle cases where HA's scoped-custom-element-registry polyfill makes
    // customElements.get() return undefined even when the element has already
    // been registered globally (e.g. after visiting config/dashboard first).
    if (!_espToolsLoaded && !customElements.get("esp-web-install-button")) {
      _espToolsLoaded = true;
      const script = document.createElement("script");
      script.type = "module";
      script.src = "https://unpkg.com/esp-web-tools@10/dist/web/install-button.js?module";
      script.onload = () => this._insertInstallButton(container);
      script.onerror = () => {
        _espToolsLoaded = false; // allow retry on next panel load
        container.innerHTML = `
          <p style="color:#f44336;font-size:.9rem">
            &#9888; Failed to load the flash tool from the CDN.<br>
            Check your internet connection, or use the
            <a href="/api/freematics/flasher" target="_blank" rel="noopener" style="color:#2196f3">
              standalone flasher page
            </a> instead.
          </p>`;
      };
      document.head.appendChild(script);
    } else {
      this._insertInstallButton(container);
    }
  }

  _insertInstallButton(container) {
    // Use personalized manifest URL (with NVS settings) if available,
    // otherwise fall back to the basic manifest (firmware only).
    const manifestUrl = this._provisioningManifestUrl || "/api/freematics/manifest.json";
    container.innerHTML = `
      <esp-web-install-button manifest="${manifestUrl}">
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

    // Reveal the progress section immediately so it is always visible once
    // the flash button is ready.  This is the most reliable way to ensure
    // the section appears: it does not depend on click-event bubbling through
    // shadow-DOM slot boundaries or on MutationObserver timing.
    const shadow = this.shadowRoot;
    const progressSection = shadow.querySelector("#flash-progress");
    if (progressSection) {
      progressSection.style.display = "block";
      this._updateFlashUI(
        "Ready — connect the device and click the button above.",
        "",
        "#9e9e9e",
        0,
      );
      this._appendFlashLog("info", "Flash tool loaded. Connect the Freematics ONE+ and click the button above.");
    }

    // On every click: reset the log and re-show "Waiting for port selection"
    // so a second attempt always starts from a clean state.  Also re-arm the
    // body observer in case it was torn down (e.g. HA sidebar navigation).
    const activateBtn = container.querySelector('[slot="activate"]');
    if (activateBtn) {
      activateBtn.addEventListener("click", () => {
        const progress = this.shadowRoot.querySelector("#flash-progress");
        const log      = this.shadowRoot.querySelector("#flash-log");
        if (!progress) return;
        if (log) log.innerHTML = "";
        progress.style.display = "block";
        this._updateFlashUI("Waiting for port selection…", "", "#2196f3", 2);
        this._appendFlashLog("info", "Waiting for port selection…");
        // Re-arm the body observer so it is active when the dialog appears.
        this._watchInstallDialog();
        // If the install dialog never appears within 30 s (e.g. user dismissed
        // the port picker or the browser couldn't open the port), show a hint.
        if (this._flashStallTimer) clearTimeout(this._flashStallTimer);
        this._flashStallTimer = setTimeout(() => {
          this._flashStallTimer = null;
          // Only fire if we are still stuck at "waiting"
          const fill = this.shadowRoot.querySelector("#progress-bar-fill");
          if (fill && parseFloat(fill.style.width) <= 2) {
            this._appendFlashLog("err", "⏱ No install dialog appeared after 30 s. The port picker may have been dismissed, or the USB driver is not installed. See the Manual Flash Fallback section below.");
            this._updateFlashUI("⏱ No response — check USB connection and driver.", "err", "#f44336", 0);
          }
        }, 30000);
      });
    }

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
            if (this._shadowDialogObserver) {
              this._shadowDialogObserver.disconnect();
              this._shadowDialogObserver = null;
            }
            // Clear the stall-detection timeout (if still pending)
            if (this._flashStallTimer) {
              clearTimeout(this._flashStallTimer);
              this._flashStallTimer = null;
            }
            // Clear the dialog-level stall guard from _onInstallDialogAdded
            if (this._dialogStallRef) {
              clearTimeout(this._dialogStallRef.timer);
              this._dialogStallRef = null;
            }
            // Clear the poll timer and show an error if flash did not complete
            if (this._progressPollTimer) {
              clearInterval(this._progressPollTimer);
              this._progressPollTimer = null;
            }
          }
        }
      }
    });
    this._dialogBodyObserver.observe(document.body, { childList: true });
  }

  _onInstallDialogAdded(dialog) {
    const shadow = this.shadowRoot;
    const progressSection = shadow.querySelector("#flash-progress");
    const logEl = shadow.querySelector("#flash-log");
    if (!progressSection) return;

    // Cancel the "no dialog" stall timer started by the activate-button click
    if (this._flashStallTimer) {
      clearTimeout(this._flashStallTimer);
      this._flashStallTimer = null;
    }

    // Reset log and reveal the progress section (no-op if the click listener
    // already revealed it; setting display again is harmless).
    if (logEl) logEl.innerHTML = "";
    progressSection.style.display = "block";
    this._updateFlashUI("Connecting to device…", "", "#2196f3", 5);
    this._appendFlashLog("info", "Connecting to device…");
    this._appendFlashLog("info", "☝ A browser dialog appeared — select the COM port and follow its steps to install the firmware.");

    // Redirect the dialog's internal logger so real flash messages appear in
    // our log console (e.g. "Connecting", "Erasing", chunk-write confirmations).
    // Guard with a property-existence check in case the API changed.
    if ("logger" in dialog) {
      dialog.logger = {
        log:   (msg) => this._appendFlashLog("info", String(msg)),
        error: (msg) => this._appendFlashLog("err",  String(msg)),
        debug: (msg) => this._appendFlashLog("warn", `[dbg] ${String(msg)}`),
      };
    }

    // Helper: read the current dialog state from multiple possible sources and
    // normalise to uppercase so our MAP lookup works regardless of whether the
    // library uses "DASHBOARD" or "dashboard" as enum values.
    const readState = () => {
      const raw = dialog.getAttribute("state") || dialog._state || dialog.state;
      return raw ? String(raw).toUpperCase() : null;
    };

    // Shared state tracker – all three mechanisms (attribute observer, shadow-
    // root observer, and poll) update the same variable so we never emit a
    // duplicate log entry and always advance monotonically.
    if (this._progressPollTimer) clearInterval(this._progressPollTimer);
    let lastState = null;
    let lastPct   = null;
    const stallRef = { timer: null };  // wrapper object so handleState (declared first)
                                        // can cancel the timer (declared below)

    const handleState = (state) => {
      if (!state || state === lastState) return;
      lastState = state;
      clearTimeout(stallRef.timer);  // state changed — no longer stalled
      this._onDialogStateChanged(state);
    };

    // Primary: watch ALL attributes on the dialog element.  Removing the
    // attributeFilter catches cases where the library uses a different
    // attribute name or the attribute is added under an alias.
    const attrObserver = new MutationObserver(() => {
      handleState(readState());
    });
    attrObserver.observe(dialog, { attributes: true });
    this._currentAttrObserver = attrObserver;

    // Secondary: watch the dialog's shadow root for any Lit re-render.  Lit
    // re-renders whenever *any* @state property changes – including _client
    // being set when the device connects (which keeps _state at "DASHBOARD"
    // and so never triggers the attribute observer alone).
    // Use subtree:true to catch nested DOM updates, and retry if the shadow
    // root is not yet available (element may be upgraded asynchronously).
    const attachShadowObserver = () => {
      if (dialog.shadowRoot && !this._shadowDialogObserver) {
        const shadowObs = new MutationObserver(() => {
          handleState(readState());
        });
        shadowObs.observe(dialog.shadowRoot, { childList: true, subtree: true });
        this._shadowDialogObserver = shadowObs;
      }
    };
    attachShadowObserver();
    // Retry after short delays in case the element is upgraded after append.
    setTimeout(attachShadowObserver, 100);
    setTimeout(attachShadowObserver, 500);

    // Tertiary: poll every 300 ms as a belt-and-suspenders fallback, and
    // separately track write-progress percentage which isn't reflected in
    // the high-level state attribute.
    this._progressPollTimer = setInterval(() => {
      handleState(readState());

      // During the WRITING phase show real byte-level percentage
      const installState = dialog._installState;
      if (
        installState &&
        installState.state === "writing" &&
        installState.details
      ) {
        const pct = Math.round(installState.details.percentage);
        if (pct !== lastPct) {
          lastPct = pct;
          this._updateFlashUI(
            `Installing… ${pct}%`,
            "",
            "#2196f3",
            pct,
          );
        }
      }
    }, 300);

    // Read the initial state in case Lit has already rendered and set it
    // before our observers were registered.
    handleState(readState());

    // Stall guard: if no meaningful state change occurs within 60 s, show an
    // actionable error so the user knows something went wrong.  The timer is
    // cancelled as soon as the state advances.
    const STALL_MS = 60000;
    stallRef.timer = setTimeout(() => {
      this._dialogStallRef = null;
      if (!lastState || lastState === "CONNECTING") {
        this._appendFlashLog("err",
          "⏱ No response from device after 60 s. " +
          "The device did not respond to the programming handshake. " +
          "Check the USB cable, ensure the correct COM port was selected, " +
          "and that the USB-Serial driver is installed. " +
          "See the Manual Flash Fallback section below for alternative methods.");
        this._updateFlashUI("⏱ Timed out — check USB connection and COM port, then retry.", "err", "#f44336", 0);
      }
    }, STALL_MS);
    // Keep a reference on the instance so the body-observer removedNodes handler
    // can cancel this timer if the dialog is removed without firing "closed".
    this._dialogStallRef = stallRef;

    // Finalize when the dialog closes
    dialog.addEventListener("closed", () => {
      clearTimeout(stallRef.timer);
      stallRef.timer = null;
      this._dialogStallRef = null;
      attrObserver.disconnect();
      this._currentAttrObserver = null;
      if (this._shadowDialogObserver) {
        this._shadowDialogObserver.disconnect();
        this._shadowDialogObserver = null;
      }
      if (this._progressPollTimer) {
        clearInterval(this._progressPollTimer);
        this._progressPollTimer = null;
      }
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
    // State values are normalised to uppercase by readState() in
    // _onInstallDialogAdded, but keep the MAP in uppercase for clarity.
    const MAP = {
      DASHBOARD: { pct: 20,  label: "Connected — follow the dialog to install…", cls: "info", color: "#2196f3" },
      ASK_ERASE: { pct: 30,  label: "Awaiting erase confirmation in dialog…",    cls: "info", color: "#ff9800" },
      INSTALL:   { pct: 55,  label: "Installing firmware… (~30 s)",              cls: "info", color: "#2196f3" },
      PROVISION: { pct: 90,  label: "Configuring Wi-Fi…",                        cls: "info", color: "#2196f3" },
      LOGS:      { pct: 100, label: "✓ Installation complete.",                  cls: "ok",   color: "#4caf50" },
      ERROR:     { pct: 0,   label: "✗ Error — see dialog for details.",         cls: "err",  color: "#f44336" },
    };
    const info = MAP[state] || { pct: 10, label: `Status: ${state}`, cls: "info", color: "#2196f3" };
    this._updateFlashUI(info.label, info.cls !== "info" ? info.cls : "", info.color, info.pct);
    this._appendFlashLog(info.cls, info.label);
  }

  _updateFlashUI(label, cls, barColor, pct) {
    const shadow = this.shadowRoot;
    const statusText   = shadow.querySelector("#flash-status-text");
    const progressFill = shadow.querySelector("#progress-bar-fill");
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
    const logEl = shadow.querySelector("#flash-log");
    if (!logEl) return;
    const ts = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className   = `log-entry ${cls}`;
    entry.textContent = `[${ts}] ${text}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
  }

  _appendOtaLog(cls, text) {
    const shadow = this.shadowRoot;
    const logEl = shadow.querySelector("#ota-log");
    if (!logEl) return;
    const ts = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className   = `log-entry ${cls}`;
    // If the text already contains a server-side timestamp like [HH:MM:SS] skip
    // adding a second prefix; otherwise prepend the client-side time.
    entry.textContent = /^\[\d{1,2}:\d{2}:\d{2}\]/.test(text) ? text : `[${ts}] ${text}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
  }
}

// Guard against duplicate registration.  HA's scoped-custom-element-registry
// polyfill can cause this line to be reached more than once (e.g. on
// sidebar navigation away-and-back), which would throw an uncaught
// DOMException and leave the panel in a broken state.
if (!customElements.get("freematics-panel")) {
  customElements.define("freematics-panel", FreematicsPanel);
}

console.info(
  `%c FREEMATICS-PANEL %c v${PANEL_VERSION} `,
  "background:#2196f3;color:#fff;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px",
  "background:#1565c0;color:#fff;padding:2px 6px;border-radius:0 4px 4px 0"
);
