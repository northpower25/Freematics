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

const PANEL_VERSION = "1.18.0";

/* -------------------------------------------------------------------------
 * Shadow-DOM helper
 * ---------------------------------------------------------------------- */

/**
 * Recursively query a CSS selector across shadow DOM boundaries.
 *
 * `querySelectorAll` does NOT pierce shadow roots, so elements nested inside
 * custom-element shadow roots (e.g. ewt-page-dashboard inside
 * ewt-install-dialog) are invisible to a plain `sr.querySelectorAll(sel)`.
 * This helper walks every shadow root reachable from `root` and collects all
 * matching elements.
 *
 * @param {ShadowRoot|Element} root - Starting DOM root to search from.
 * @param {string} selector         - CSS selector to match.
 * @returns {Element[]}
 */
function _queryAllShadow(root, selector) {
  const found = [...root.querySelectorAll(selector)];
  for (const el of root.querySelectorAll("*")) {
    if (el.shadowRoot) {
      found.push(..._queryAllShadow(el.shadowRoot, selector));
    }
  }
  return found;
}

/** Default (unauthenticated) esp-web-tools manifest served by this integration. */
const DEFAULT_MANIFEST_URL = "/api/freematics/manifest.json";

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
    this._flashRendering = false;
    this._consoleRendered = false;
    this._serialPort = null;
    this._serialReader = null;
    this._serialWriter = null;
    this._serialReadLoop = null;
    this._provisioningManifestUrl = null;
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    // Nothing to re-attach for the iframe-based flash tab.
  }

  disconnectedCallback() {
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
  async _renderFlash() {
    const el = this.shadowRoot.getElementById("content-flash");
    if (!el) return;

    // Render only once: preserves the iframe so an in-progress flash is not
    // interrupted when the user switches tabs and returns.
    if (this._flashRendered || this._flashRendering) return;
    this._flashRendering = true;

    const cs = "background:var(--secondary-background-color);padding:1px 4px;border-radius:3px";

    // Fetch provisioning token first so the iframe starts with the personalised
    // manifest URL (includes WiFi, APN, and HA server settings).
    let manifestUrl = DEFAULT_MANIFEST_URL;
    let flashImageUrl = null;
    let nvsUrl = null;
    try {
      const result = await Promise.race([
        this._hass.callApi("GET", "freematics/provisioning_token"),
        new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 4000)),
      ]);
      if (result && result.manifest_url) {
        manifestUrl = result.manifest_url;
        this._provisioningManifestUrl = manifestUrl;
        flashImageUrl = result.flash_image_url || null;
        nvsUrl        = result.nvs_url || null;
      }
    } catch (_) {
      // Non-fatal: fall back to default manifest (firmware without NVS settings).
    }

    const flasherUrl = `/api/freematics/flasher?manifest=${encodeURIComponent(manifestUrl)}&embedded=1`;

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

        <!-- ── Browser flasher via iframe (Web Serial) ───────────── -->
        <div class="flash-card" id="flash-action">
          <h3>&#9889; Flash Firmware (USB / Web Serial)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            Connect the Freematics ONE+ via USB to <em>this computer</em>, then click
            <strong>Connect &amp; Flash Firmware</strong> below.
            A browser dialog will open to select the COM port.<br>
            Look for: <code style="${cs}">CP2102</code>,
            <code style="${cs}">CH340</code>, or a similar USB-Serial device.
          </p>
          <p style="font-size:.82rem;color:var(--secondary-text-color);margin:0 0 6px">
            &#128268; Requires
            <strong>Google Chrome or Microsoft Edge 89+</strong>
            over HTTPS or <code style="${cs}">localhost</code>.
          </p>
          <iframe
            id="flash-iframe"
            src="${flasherUrl}"
            allow="serial"
            style="width:100%;height:520px;border:1px solid var(--divider-color);border-radius:6px;"
            title="Freematics ONE+ Browser Flasher"
          ></iframe>
          <p style="font-size:.82rem;color:var(--secondary-text-color);margin:4px 0 0;text-align:center">
            Iframe not working? &nbsp;
            <a id="flash-newtab-link" href="${flasherUrl.replace('&embedded=1','')}"
               target="_blank" rel="noopener"
               style="color:#2196f3;white-space:nowrap"
               aria-label="Open flasher in a new browser tab">
              Open flasher in a new browser tab ↗
            </a>
          </p>
        </div>

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
            The device firmware is compiled with the built-in HTTP server enabled
            (<code style="${cs}">ENABLE_HTTPD=1</code>) so no extra configuration is needed.
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
                  &nbsp;— Bootloader&nbsp;+&nbsp;Partition table&nbsp;+&nbsp;NVS&nbsp;+&nbsp;firmware, for <strong>esptool</strong> at offset <code style="${cs}">0x1000</code>
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
              <strong style="color:var(--primary-text-color)">&#8505; What flash_image.bin contains (offset&nbsp;0x1000)</strong><br>
              <table style="margin-top:4px;border-collapse:collapse;width:100%">
                <tr>
                  <td style="padding:2px 8px 2px 0;white-space:nowrap">Offset <code style="${cs}">0x1000</code></td>
                  <td>Second-stage bootloader (∼19 KB) — <strong>critical:</strong> restores the bootloader erased by esp-web-tools on first install</td>
                </tr>
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
                <pre style="background:var(--primary-background-color);padding:5px 8px;border-radius:4px;font-size:.82rem;margin:3px 0;overflow-x:auto">python -m esptool write-flash 0x1000 flash_image.bin</pre>
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
              <li>Flash <code style="${cs}">flash_image.bin</code> at offset <code style="${cs}">0x1000</code> using esptool (see Option A above)</li>
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
          <h3>&#128202; Built-in Data Viewer &amp; OTA Update Server (HTTPD)</h3>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            The pre-compiled firmware has the built-in HTTP server
            (<code style="${cs}">ENABLE_HTTPD=1</code>) <strong>enabled by default</strong>.
            This allows WiFi OTA firmware updates and lets you view live data
            directly on the device via a web browser.
          </p>
          <p style="font-size:.9rem;color:var(--secondary-text-color);margin:0 0 8px">
            <strong>Available endpoints when the device is reachable on the network:</strong>
          </p>
          <ul style="font-size:.88rem;color:var(--secondary-text-color);margin:0 0 8px">
            <li><code style="${cs}">/api/info</code> – device info (chip, firmware, uptime)</li>
            <li><code style="${cs}">/api/live</code> – live sensor data (OBD, GPS, MEMS)</li>
            <li><code style="${cs}">/api/control?cmd=…</code> – send control commands</li>
            <li><code style="${cs}">/api/list</code> – list log files on SD card</li>
            <li><code style="${cs}">/api/log/&lt;n&gt;</code> – download raw CSV log file</li>
            <li><code style="${cs}">/update</code> – OTA firmware upload endpoint (used by WiFi OTA above)</li>
          </ul>
        </div>

      </div>
    `;

    // Mark as rendered (guards against tab-switch re-renders).
    this._flashRendered = true;
    this._flashRendering = false;

    // Update download links with provisioned URLs (if token was obtained above).
    const flashImageLink = el.querySelector("#dl-flash-image");
    const nvsLink        = el.querySelector("#dl-nvs");
    const nvsStatus      = el.querySelector("#nvs-dl-status");
    if (flashImageUrl && flashImageLink) {
      flashImageLink.href = flashImageUrl;
    }
    if (nvsUrl && nvsLink) {
      nvsLink.href = nvsUrl;
    }
    if (nvsStatus) {
      if (flashImageUrl) {
        nvsStatus.innerHTML =
          "&#10003; File ready — download link active for 5 minutes. " +
          "<em>Generated fresh from your current settings.</em>";
        nvsStatus.style.color = "var(--success-color, #4caf50)";
      } else {
        nvsStatus.textContent = "⚠ Could not generate settings file — no integration configured.";
        nvsStatus.style.color = "#ff9800";
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
