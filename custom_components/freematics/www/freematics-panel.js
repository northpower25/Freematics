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
 *  3. Console    – Web Serial terminal at 115200 baud (like miniterm).
 */

const PANEL_VERSION = "1.16.1";

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
  /* --- serial console tab --- */
  .console-wrap { max-width: 900px; margin: 0 auto; }
  .console-toolbar {
    display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .console-terminal {
    background: #0d1117;
    color: #58d68d;
    font-family: 'Roboto Mono', 'Courier New', monospace;
    font-size: 0.82rem;
    padding: 12px 14px;
    border-radius: 8px;
    min-height: 320px;
    max-height: 520px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    box-shadow: inset 0 2px 8px rgba(0,0,0,.5);
    margin-bottom: 10px;
  }
  .console-input-row {
    display: flex; gap: 8px; align-items: center; margin-top: 8px;
  }
  .console-input {
    flex: 1;
    padding: 8px 10px;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: 'Roboto Mono', monospace;
    font-size: 0.88rem;
  }
  .console-btn {
    padding: 8px 14px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.88rem;
    font-family: inherit;
  }
  .console-btn-connect  { background: #4caf50; color: #fff; }
  .console-btn-connect:hover  { background: #388e3c; }
  .console-btn-disconnect { background: #f44336; color: #fff; }
  .console-btn-disconnect:hover { background: #c62828; }
  .console-btn-send     { background: #2196f3; color: #fff; }
  .console-btn-send:hover { background: #1976d2; }
  .console-btn-clear    { background: #757575; color: #fff; }
  .console-btn-clear:hover { background: #424242; }
  .console-btn-newtab   { background: #9c27b0; color: #fff; }
  .console-btn-newtab:hover { background: #6a1b9a; }
  .console-status {
    font-size: 0.82rem;
    padding: 4px 8px;
    border-radius: 4px;
    margin-left: 4px;
  }
  .console-status.connected { background: #e8f5e9; color: #2e7d32; }
  .console-status.disconnected { background: #ffebee; color: #c62828; }
  .baud-select {
    padding: 7px 10px;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-size: 0.88rem;
    font-family: inherit;
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
    this._consoleRendered = false;
    this._serialPort = null;
    this._serialReader = null;
    this._serialWriter = null;
    this._serialReadLoop = null;
    this._dialogBodyObserver = null;
    this._currentAttrObserver = null;
    this._shadowDialogObserver = null;
    this._progressPollTimer = null;
    this._showBtnFallbackTimer = null;
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
    if (this._showBtnFallbackTimer) {
      clearTimeout(this._showBtnFallbackTimer);
      this._showBtnFallbackTimer = null;
    }
    this._cleanupSerial();
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
   * Scan hass.states for sensor.freematics_*_speed entities and
   * return the list of unique entity prefixes, e.g.
   *   ["sensor.freematics_b1af617d"]
   *
   * The regex uses \w+ which includes underscores, so it correctly matches
   * ALL known entity-ID variants regardless of how many underscore-separated
   * segments appear between "freematics_" and "_speed":
   *   • Current installs: sensor.freematics_<id8>_speed
   *                   e.g. sensor.freematics_b1af617d_speed
   *   • PR-36 era:        sensor.freematics_one_<id8>_speed
   *   • Legacy installs:  sensor.freematics_one_unknown_speed
   *   • Minimal name:     sensor.freematics_one_speed
   * The non-greedy \w+? combined with the $ anchor ensures only the LAST
   * "_speed" is matched, giving the correct prefix for all variants.
   */
  _discoverDevices() {
    if (!this._hass) return [];
    const prefixes = new Set();
    for (const entityId of Object.keys(this._hass.states)) {
      const m = entityId.match(/^(sensor\.freematics_\w+?)_speed$/);
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
        <button class="tab" data-tab="console">&#128291; Serial Console</button>
      </div>
      <div class="content" id="content-dashboard"></div>
      <div class="content" id="content-flash" style="display:none"></div>
      <div class="content" id="content-console" style="display:none"></div>
    `;

    shadow.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => {
        shadow.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        btn.classList.add("active");
        this._activeTab = btn.dataset.tab;
        const dashEl    = shadow.getElementById("content-dashboard");
        const flashEl   = shadow.getElementById("content-flash");
        const consoleEl = shadow.getElementById("content-console");
        dashEl.style.display    = this._activeTab === "dashboard" ? "" : "none";
        flashEl.style.display   = this._activeTab === "flash"     ? "" : "none";
        consoleEl.style.display = this._activeTab === "console"   ? "" : "none";
        if (this._activeTab === "dashboard") {
          this._renderDashboard();
        } else if (this._activeTab === "flash") {
          this._renderFlash();
        } else {
          this._renderConsole();
        }
      });
    });

    this._renderContent();
  }

  _renderContent() {
    if (this._activeTab === "dashboard") {
      this._renderDashboard();
    } else if (this._activeTab === "flash") {
      this._renderFlash();
    } else {
      this._renderConsole();
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
    const isSecure = window.isSecureContext;
    const cs = "background:var(--secondary-background-color);padding:1px 4px;border-radius:3px";

    // Determine the reason Web Serial is unavailable (if it is)
    let serialWarnHtml = "";
    if (!hasSerial) {
      if (!isSecure) {
        // HTTP (non-secure) context — most common reason on local IP access
        serialWarnHtml = `
          &#9888; <strong>Web Serial API not available – HTTPS required.</strong><br>
          The Web Serial API requires a <strong>secure HTTPS connection</strong>. This is a
          browser security requirement that applies regardless of where the USB device is plugged in.
          <strong>Your USB device does not need to be on the same machine as the HA server</strong>
          — only the browser page must be loaded over HTTPS.<br><br>
          <strong>Options to enable browser flashing:</strong>
          <ul style="margin:6px 0 4px;padding-left:20px">
            <li>Access Home Assistant via
              <a href="https://www.nabucasa.com/" target="_blank" rel="noopener" style="color:#795548">Nabu Casa</a>
              (e.g. <code style="${cs}">https://xxx.ui.nabu.casa</code>)</li>
            <li>Access HA using <code style="${cs}">http://localhost:8123</code> instead of an IP address
              (<code>localhost</code> is treated as secure by browsers)</li>
            <li>Set up a trusted HTTPS certificate for your local HA instance</li>
          </ul>
          Or use the <em>Manual Flash</em> section below — it works without HTTPS.
        `;
      } else {
        // Secure context but no navigator.serial → unsupported browser
        serialWarnHtml = `
          &#9888; <strong>Web Serial API not available.</strong><br>
          Please open this page in <strong>Google Chrome</strong> or
          <strong>Microsoft Edge</strong> (version 89 or newer).<br>
          Other browsers (Firefox, Safari) do not support the Web Serial API.
        `;
      }
    }

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

        ${serialWarnHtml ? `<div class="warn-banner visible">${serialWarnHtml}</div>` : ""}

        <!-- ── Requirements ───────────────────────────────────────── -->
        <div class="flash-card">
          <h3>&#128268; Requirements</h3>
          <ul>
            <li>Google Chrome or Microsoft Edge (version 89+) — over HTTPS or <code style="${cs}">localhost</code></li>
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
            <div id="flash-manual-btn-wrap" style="display:none;margin-bottom:10px">
              <button id="flash-start-btn" style="
                background:#4caf50;color:#fff;border:none;padding:10px 22px;
                font-size:.9rem;border-radius:6px;cursor:pointer;width:100%;
                font-family:inherit;
              ">
                &#128640; Start Flashing
              </button>
            </div>
            <div class="flash-log" id="flash-log"></div>
          </div>
          <ol style="font-size:.9rem;color:var(--secondary-text-color)">
            <li>Click <em>Connect &amp; Flash Firmware</em></li>
            <li>Select the Freematics ONE+ COM port from the browser dialog</li>
            <li>Firmware + settings flash automatically (may take ~2 min)</li>
            <li>Device restarts and connects to your WiFi / sends data to Home Assistant</li>
          </ol>
        </div>
        ` : `
        <div class="flash-card">
          <h3>&#9889; Browser / Web Serial not available</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color)">
            Use the standalone flasher page in Chrome / Edge (over HTTPS or <code style="${cs}">localhost</code>),
            or use one of the manual methods below.
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
        showStatus("#2196f3", "&#9203; Uploading firmware… (may take ~2 min)");
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

    // Enable the built-in ESP Web Tools log/console so the raw flash output
    // is visible inside the dialog – useful for debugging failures.
    const installBtn = container.querySelector("esp-web-install-button");
    if (installBtn) {
      installBtn.showLog = true;
      installBtn.logConsole = true;
    }

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

    // Manual "Start Flashing" button — shown when device is connected (DASHBOARD
    // or ASK_ERASE state) as a fallback if auto-advance fails to click the
    // Install button inside the (potentially invisible) popup dialog.
    const startBtn = shadow.querySelector("#flash-start-btn");
    if (startBtn) {
      startBtn.addEventListener("click", () => {
        startBtn.disabled = true;
        startBtn.textContent = "Starting…";
        if (!this._currentDialog) {
          // Dialog reference is missing — guide the user to reconnect.
          startBtn.disabled = false;
          startBtn.textContent = "🚀 Start Flashing";
          this._appendFlashLog("warn",
            "⚠ No active install dialog found. " +
            "Please click Connect & Flash Firmware to reconnect the device.");
          return;
        }
        const advanced = this._tryAutoAdvanceDialog(this._currentDialog);
        if (!advanced) {
          // Could not find/click the Install button — re-enable and inform user.
          startBtn.disabled = false;
          startBtn.textContent = "🚀 Start Flashing";
          this._appendFlashLog("warn",
            "⚠ Could not auto-click the Install button. " +
            "The popup dialog may still be visible — please interact with it directly, " +
            "or try reconnecting the device and clicking Connect & Flash Firmware again.");
        }
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
            // Cancel the fallback button-reveal timer
            if (this._showBtnFallbackTimer) {
              clearTimeout(this._showBtnFallbackTimer);
              this._showBtnFallbackTimer = null;
            }
            // Clear dialog reference and hide the manual Start Flashing button
            this._currentDialog = null;
            const manualWrap = this.shadowRoot.querySelector("#flash-manual-btn-wrap");
            if (manualWrap) manualWrap.style.display = "none";
          }
        }
      }
    });
    this._dialogBodyObserver.observe(document.body, { childList: true });
  }

  _onInstallDialogAdded(dialog) {
    // Keep a reference so the manual Start Flashing button can call
    // _tryAutoAdvanceDialog even outside the handleState closure.
    this._currentDialog = dialog;
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

    // Fallback: reveal the "🚀 Start Flashing" button after a short delay if
    // auto-advance hasn't already triggered the install.  This handles the case
    // where readState() cannot detect the DASHBOARD/ASK_ERASE state (e.g. due
    // to an esp-web-tools internal API change) so the user always has a visible
    // manual trigger regardless of whether state detection is working.
    // Guard that ensures the Install / Skip-Erase button is only auto-clicked
    // once per dialog session even if the observers fire multiple times.
    let _autoAdvanced = false;
    if (this._showBtnFallbackTimer) {
      clearTimeout(this._showBtnFallbackTimer);
      this._showBtnFallbackTimer = null;
    }
    const SHOW_BTN_FALLBACK_MS = 5000;
    this._showBtnFallbackTimer = setTimeout(() => {
      this._showBtnFallbackTimer = null;
      if (_autoAdvanced || this._currentDialog !== dialog) return;
      const manualWrap = this.shadowRoot.querySelector("#flash-manual-btn-wrap");
      if (manualWrap && manualWrap.style.display !== "block") {
        manualWrap.style.display = "block";
        const btn = manualWrap.querySelector("#flash-start-btn");
        if (btn) {
          btn.disabled = false;
          btn.textContent = "🚀 Start Flashing";
        }
        this._appendFlashLog("info",
          "👆 If flashing has not started automatically, click the Start Flashing button below.");
      }
    }, SHOW_BTN_FALLBACK_MS);

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
    let lastState          = null;
    let lastPct            = null;
    // Track esp-web-tools v10 _installState messages for 1:1 log output.
    // In v10 the flash function communicates progress via state events stored
    // in dialog._installState rather than a logger interface, so we poll it.
    let lastInstallMessage = null;
    let lastInstallState   = null;
    const stallRef = { timer: null };  // wrapper object so handleState (declared first)
                                        // can cancel the timer (declared below)

    const handleState = (state) => {
      if (!state || state === lastState) return;
      lastState = state;
      clearTimeout(stallRef.timer);  // state changed — no longer stalled
      this._onDialogStateChanged(state);
      // Auto-advance past states that require interaction with the popup
      // dialog, which may be invisible inside the HA Dashboard.
      // A short delay lets the shadow DOM re-render and enable the button
      // before we try to click it.
      const DIALOG_AUTO_ADVANCE_DELAY_MS = 300;
      if ((state === "DASHBOARD" || state === "ASK_ERASE") && !_autoAdvanced) {
        setTimeout(() => {
          if (!_autoAdvanced) {
            _autoAdvanced = this._tryAutoAdvanceDialog(dialog);
            if (_autoAdvanced && this._showBtnFallbackTimer) {
              clearTimeout(this._showBtnFallbackTimer);
              this._showBtnFallbackTimer = null;
            }
          }
        }, DIALOG_AUTO_ADVANCE_DELAY_MS);
      }
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
    // Also: scan for Install / Skip-Erase buttons on every re-render so that
    // auto-advance works even when readState() cannot read the dialog state
    // (e.g. when esp-web-tools changes its internal property names).
    const attachShadowObserver = () => {
      if (dialog.shadowRoot && !this._shadowDialogObserver) {
        const shadowObs = new MutationObserver(() => {
          handleState(readState());
          if (!_autoAdvanced) {
            _autoAdvanced = this._tryAutoAdvanceDialog(dialog);
            if (_autoAdvanced && this._showBtnFallbackTimer) {
              clearTimeout(this._showBtnFallbackTimer);
              this._showBtnFallbackTimer = null;
            }
          }
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

      // Forward esp-web-tools v10 _installState messages to the log.
      // In v10 the flash() function communicates progress via state events
      // (stored in dialog._installState) rather than via a logger interface.
      // Each state transition carries a human-readable .message string such
      // as "Initializing...", "Initialized. Found ESP32", "Erasing device...",
      // "Writing complete", "All done!", or an error description.  We mirror
      // every *new* message to #flash-log so the user sees 1:1 raw output.
      // Exception: skip repetitive mid-stream "Writing progress: X%"
      // updates -- those are already visualised by the progress bar.
      const installState = dialog._installState;
      if (installState) {
        const iMsg   = installState.message;
        const iState = installState.state;

        if (iMsg && iMsg !== lastInstallMessage) {
          // Suppress repeated writing-progress lines; keep first entry and
          // the final "Writing complete" / any non-"Writing progress:" msg.
          const isRepeatWritingProgress =
            iState === "writing" &&
            lastInstallState === "writing" &&
            typeof iMsg === "string" &&
            iMsg.startsWith("Writing progress:");

          if (!isRepeatWritingProgress) {
            lastInstallMessage = iMsg;
            const cls = iState === "error" ? "err"
                      : iState === "finished" ? "ok"
                      : "info";
            this._appendFlashLog(cls, iMsg);
          }
        }
        lastInstallState = iState;

        // Any flash state change means the device is alive – cancel the stall
        // guard so it cannot fire a false "no response" error mid-flash.
        if (iState && iState !== "error" && stallRef.timer) {
          clearTimeout(stallRef.timer);
          stallRef.timer = null;
        }

        // During the WRITING phase show real byte-level percentage
        if (iState === "writing" && installState.details) {
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
      }
    }, 300);

    // Read the initial state in case Lit has already rendered and set it
    // before our observers were registered.
    handleState(readState());

    // Stall guard: if no meaningful state change occurs within STALL_MS, show
    // an actionable error so the user knows something went wrong.  The timer is
    // cancelled as soon as the state advances OR as soon as write progress is
    // detected (see the progress-poll interval above).
    // 3 min (180 s) gives enough headroom for the ~103 s flash write time at
    // 115 200 baud plus device reset and erase overhead.
    const STALL_MS = 180000;
    // Minimum write-progress percentage that indicates the flash is genuinely
    // under way.  5 % is well above the noise floor (0 % = no writes started)
    // but low enough that the guard trips before the firmware write completes.
    const STALL_MIN_PROGRESS_PCT = 5;
    const stallMinStr = `${Math.round(STALL_MS / 60000)} min`;
    stallRef.timer = setTimeout(() => {
      this._dialogStallRef = null;
      // Only fire if no state was detected AND no byte-level write progress
      // was observed AND no _installState messages were received.
      // This guards against readState() returning null throughout (API version
      // mismatch) while the flash is actually running and being tracked via
      // _installState (message forwarding or details.percentage).
      if ((!lastState || lastState === "CONNECTING") && (lastPct === null || lastPct < STALL_MIN_PROGRESS_PCT) && !lastInstallMessage) {
        this._appendFlashLog("err",
          `⏱ No response from device after ${stallMinStr}. ` +
          "The Web Serial API could not complete the programming handshake. " +
          "Check the USB cable and confirm the correct COM port was selected. " +
          "If the problem persists in the browser, use the esptool command-line method — " +
          "it handles device reset automatically via DTR/RTS: " +
          "python -m esptool write-flash 0x8000 flash_image.bin " +
          "(add --port COM3 if esptool does not detect the port automatically). " +
          "See the Manual Flash section below.");
        this._updateFlashUI("⏱ Timed out — check USB cable/driver, or use esptool from the command line.", "err", "#f44336", 0);
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
      if (this._showBtnFallbackTimer) {
        clearTimeout(this._showBtnFallbackTimer);
        this._showBtnFallbackTimer = null;
      }
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
      DASHBOARD: { pct: 20,  label: "Device connected — starting installation…", cls: "info", color: "#4caf50" },
      ASK_ERASE: { pct: 30,  label: "Checking flash state — skipping erase…",    cls: "info", color: "#2196f3" },
      INSTALL:   { pct: 55,  label: "Installing firmware… (may take ~2 min)",      cls: "info", color: "#2196f3" },
      PROVISION: { pct: 90,  label: "Configuring Wi-Fi…",                        cls: "info", color: "#2196f3" },
      LOGS:      { pct: 100, label: "✓ Installation complete.",                  cls: "ok",   color: "#4caf50" },
      ERROR:     { pct: 0,   label: "✗ Error — see dialog for details.",         cls: "err",  color: "#f44336" },
    };
    const info = MAP[state] || { pct: 10, label: `Status: ${state}`, cls: "info", color: "#2196f3" };
    this._updateFlashUI(info.label, info.cls !== "info" ? info.cls : "", info.color, info.pct);
    this._appendFlashLog(info.cls, info.label);

    // Show the manual Start Flashing button when device is connected (DASHBOARD
    // or ASK_ERASE) so the user has a visible fallback if auto-advance fails.
    // Hide it as soon as actual flashing begins or the session ends.
    const manualWrap = this.shadowRoot.querySelector("#flash-manual-btn-wrap");
    if (manualWrap) {
      const showBtn = state === "DASHBOARD" || state === "ASK_ERASE";
      manualWrap.style.display = showBtn ? "block" : "none";
      // Re-enable the button text in case it was disabled by a previous click.
      const btn = manualWrap.querySelector("#flash-start-btn");
      if (btn && showBtn) {
        btn.disabled = false;
        btn.textContent = "🚀 Start Flashing";
      }
    }
  }

  /**
   * Scan the esp-web-tools dialog's shadow root for Install / Skip-Erase
   * buttons and click the appropriate one automatically.  This handles the
   * case where the dialog popup is not visible or not interactable inside
   * the HA Dashboard (both the DASHBOARD and ASK_ERASE states require user
   * interaction with the popup).
   *
   * Returns true when a button was found and clicked, false otherwise.
   * The caller should set an "_autoAdvanced" guard so this is only invoked
   * once per dialog session.
   */
  _tryAutoAdvanceDialog(dialog) {
    const sr = dialog.shadowRoot;
    if (!sr) return false;

    // Helper: return the human-visible text of a button element.
    // mwc-button can store its label in a `label` attribute rather than as
    // text content, so we check both.
    const getBtnText = b =>
      (b.textContent || b.getAttribute("label") || "").trim();

    const allBtns = [...sr.querySelectorAll(
      "mwc-button, ewt-button, button, [role='button']",
    )];

    // --- ASK_ERASE state ---
    // Both an "Erase device" button AND a "Skip"/"Continue without erasing"
    // button are present.  We always skip erasing because the manifest already
    // writes a full image (partition table + NVS + firmware) at explicit offsets.
    // The skip/continue pattern is kept specific to erase-related phrasing to
    // avoid accidentally clicking unrelated "Continue" buttons.
    const eraseBtn = allBtns.find(b => /\berase\b/i.test(getBtnText(b)));
    const skipBtn  = allBtns.find(b => /\bskip\b|\bwithout eras/i.test(getBtnText(b)));
    if (eraseBtn && skipBtn) {
      this._appendFlashLog("info",
        "Skipping erase — the full partition image overwrites all sectors automatically.");
      this._updateFlashUI("Skipping erase — starting flash…", "", "#2196f3", 35);
      skipBtn.click();
      return true;
    }

    // --- DASHBOARD state ---
    // An Install button is present and not disabled — device is connected and
    // ready.  Click it to start the actual flash without requiring the user to
    // interact with the (potentially invisible) popup dialog.
    const installBtn = allBtns.find(b =>
      /\binstall\b/i.test(getBtnText(b)) && !b.disabled);
    if (installBtn) {
      this._appendFlashLog("info",
        "Device detected — triggering installation automatically (no popup interaction required).");
      this._updateFlashUI("Device connected — starting flash…", "", "#4caf50", 22);
      installBtn.click();
      return true;
    }

    return false;
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

  /* ── Serial Console tab ─────────────────────────────────────────── */

  async _cleanupSerial() {
    this._serialReadLoop = null;
    try { if (this._serialReader) { await this._serialReader.cancel(); } } catch (_) { /* ignore */ }
    try { if (this._serialWriter) { await this._serialWriter.close(); } } catch (_) { /* ignore */ }
    try { if (this._serialPort)   { await this._serialPort.close(); }  } catch (_) { /* ignore */ }
    this._serialReader = null;
    this._serialWriter = null;
    this._serialPort   = null;
  }

  _renderConsole() {
    const el = this.shadowRoot.getElementById("content-console");
    if (!el) return;

    if (this._consoleRendered) return;
    this._consoleRendered = true;

    const hasSerial = "serial" in navigator;
    const isSecure  = window.isSecureContext;

    let warnHtml = "";
    if (!hasSerial) {
      if (!isSecure) {
        warnHtml = `
          <div class="warn-banner visible" style="margin-bottom:14px">
            &#9888; <strong>Web Serial API not available – HTTPS required.</strong><br>
            Access Home Assistant via <strong>Nabu Casa</strong>, over HTTPS with a trusted
            certificate, or via <code>http://localhost:8123</code> to use the Serial Console.
            Alternatively, open the
            <a href="/api/freematics/console" target="_blank" rel="noopener" style="color:#795548">
              standalone console page
            </a> in Chrome/Edge on an HTTPS origin.
          </div>`;
      } else {
        warnHtml = `
          <div class="warn-banner visible" style="margin-bottom:14px">
            &#9888; <strong>Web Serial API not available.</strong><br>
            Please use <strong>Google Chrome</strong> or <strong>Microsoft Edge</strong>
            (version 89 or newer) to use the Serial Console.
          </div>`;
      }
    }

    el.innerHTML = `
      <div class="console-wrap">
        <h3 style="margin:0 0 12px;font-size:1.05rem;color:var(--primary-text-color)">
          &#128291; Serial Console
          <span style="font-size:.8rem;font-weight:400;color:var(--secondary-text-color);margin-left:8px">
            (like <code>python -m serial.tools.miniterm COM4 115200</code>)
          </span>
        </h3>

        ${warnHtml}

        <div class="info-banner" style="margin-bottom:14px">
          The Serial Console opens a direct connection to the Freematics ONE+
          USB serial port at 115200 baud. Use it to monitor the device log,
          check WiFi connection status, and observe OBD data in real time.
          <strong>Tip:</strong> You can also
          <a href="/api/freematics/console" target="_blank" rel="noopener" style="color:#1565c0">
            open the console in a separate browser tab ↗
          </a>
        </div>

        ${hasSerial ? `
        <div class="console-toolbar">
          <select id="console-baud" class="baud-select">
            <option value="9600">9600 baud</option>
            <option value="115200" selected>115200 baud</option>
            <option value="230400">230400 baud</option>
            <option value="460800">460800 baud</option>
            <option value="921600">921600 baud</option>
          </select>
          <select id="console-newline" class="baud-select">
            <option value="crlf">CR+LF (\\r\\n)</option>
            <option value="lf">LF only (\\n)</option>
            <option value="cr">CR only (\\r)</option>
          </select>
          <button id="console-connect-btn" class="console-btn console-btn-connect">
            &#128291; Connect
          </button>
          <button id="console-clear-btn" class="console-btn console-btn-clear">
            &#128465; Clear
          </button>
          <span id="console-status" class="console-status disconnected">● Disconnected</span>
        </div>
        <div id="console-terminal" class="console-terminal">
          <span style="color:#57606a">— Waiting for connection — click Connect to open a serial port —</span>
        </div>
        <div class="console-input-row">
          <input id="console-input" class="console-input" type="text"
                 placeholder="Type a command and press Enter or click Send…"
                 disabled>
          <button id="console-send-btn" class="console-btn console-btn-send" disabled>
            &#9654; Send
          </button>
        </div>
        <p style="font-size:.8rem;color:var(--secondary-text-color);margin:8px 0 0">
          &#8505; The console only works while this tab is open. Closing or navigating away
          will disconnect the port. Use the
          <a href="/api/freematics/console" target="_blank" rel="noopener" style="color:#2196f3">
            standalone console page
          </a>
          for a persistent dedicated window.
        </p>
        ` : `
        <div class="flash-card">
          <h3>&#128291; Serial Console not available in this browser</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color)">
            Use Chrome or Edge 89+ over HTTPS / <code>localhost</code>, or open the
            standalone console page:
          </p>
          <div class="flash-fallback">
            <a href="/api/freematics/console" target="_blank" rel="noopener">
              &#128291; Open Standalone Console Page
            </a>
          </div>
        </div>
        `}
      </div>
    `;

    if (!hasSerial) return;

    const shadow = this.shadowRoot;
    const connectBtn  = shadow.getElementById("console-connect-btn");
    const clearBtn    = shadow.getElementById("console-clear-btn");
    const sendBtn     = shadow.getElementById("console-send-btn");
    const inputEl     = shadow.getElementById("console-input");
    const terminalEl  = shadow.getElementById("console-terminal");
    const statusEl    = shadow.getElementById("console-status");
    const baudSel     = shadow.getElementById("console-baud");
    const newlineSel  = shadow.getElementById("console-newline");

    const appendTerminal = (text, color) => {
      // Replace first placeholder if present
      const placeholder = terminalEl.querySelector("span[style]");
      if (placeholder) terminalEl.innerHTML = "";
      const span = document.createElement("span");
      if (color) span.style.color = color;
      span.textContent = text;
      terminalEl.appendChild(span);
      terminalEl.scrollTop = terminalEl.scrollHeight;
    };

    const setConnected = (connected) => {
      if (connected) {
        connectBtn.textContent = "⏹ Disconnect";
        connectBtn.className = "console-btn console-btn-disconnect";
        statusEl.textContent = "● Connected";
        statusEl.className = "console-status connected";
        inputEl.disabled = false;
        sendBtn.disabled = false;
      } else {
        connectBtn.textContent = "🔌 Connect";
        connectBtn.className = "console-btn console-btn-connect";
        statusEl.textContent = "● Disconnected";
        statusEl.className = "console-status disconnected";
        inputEl.disabled = true;
        sendBtn.disabled = true;
      }
    };

    connectBtn.addEventListener("click", async () => {
      if (this._serialPort) {
        // Disconnect
        appendTerminal("\n[Disconnected]\n", "#57606a");
        await this._cleanupSerial();
        setConnected(false);
        return;
      }
      try {
        const port = await navigator.serial.requestPort();
        const baud = parseInt(baudSel.value) || 115200;
        await port.open({ baudRate: baud });
        this._serialPort = port;
        setConnected(true);
        appendTerminal(`\n[Connected at ${baud} baud]\n`, "#57606a");

        // Read loop
        const decoder = new TextDecoderStream();
        port.readable.pipeTo(decoder.writable).catch(() => {});
        const reader = decoder.readable.getReader();
        this._serialReader = reader;

        const readLoop = async () => {
          while (true) {
            let result;
            try { result = await reader.read(); } catch (_) { break; }
            if (result.done) break;
            appendTerminal(result.value);
            // Check if the loop was replaced (new connection)
            if (this._serialReadLoop !== readLoop) break;
          }
          if (this._serialPort) {
            appendTerminal("\n[Connection closed]\n", "#57606a");
            await this._cleanupSerial();
            setConnected(false);
          }
        };
        this._serialReadLoop = readLoop;

        // Writer stream
        const encoder = new TextEncoderStream();
        encoder.readable.pipeTo(port.writable).catch(() => {});
        this._serialWriter = encoder.writable.getWriter();

        readLoop();
      } catch (err) {
        if (err.name !== "NotFoundError") {
          appendTerminal(`\n[Error: ${err.message || err}]\n`, "#ff7675");
        }
      }
    });

    clearBtn.addEventListener("click", () => {
      terminalEl.innerHTML = "";
    });

    const sendCommand = async () => {
      if (!this._serialWriter || !inputEl.value) return;
      const nlMap = { crlf: "\r\n", lf: "\n", cr: "\r" };
      const nl = nlMap[newlineSel.value] || "\r\n";
      try {
        await this._serialWriter.write(inputEl.value + nl);
        inputEl.value = "";
      } catch (err) {
        appendTerminal(`\n[Send error: ${err.message || err}]\n`, "#ff7675");
      }
    };

    sendBtn.addEventListener("click", sendCommand);
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendCommand();
    });
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
