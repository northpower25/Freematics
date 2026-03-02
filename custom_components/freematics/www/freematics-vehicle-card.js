/**
 * Freematics Vehicle Card
 * A custom Lovelace card for the Freematics ONE+ Home Assistant integration.
 * Displays vehicle telemetry data in a compact dashboard card.
 *
 * Usage in Lovelace:
 *   type: custom:freematics-vehicle-card
 *   title: My Car
 *   webhook_id: <your-webhook-id>
 *   entity_prefix: sensor.freematics_one_<webhook_id_short>
 */

const VERSION = "1.1.0";

class FreematicsVehicleCard extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
  }

  getCardSize() {
    return 4;
  }

  _getEntity(suffix) {
    if (!this._hass) return null;
    const id = this._config.entity_prefix
      ? `${this._config.entity_prefix}_${suffix}`
      : `sensor.freematics_one_${suffix}`;
    return this._hass.states[id] || null;
  }

  _stateVal(suffix, unit) {
    const e = this._getEntity(suffix);
    if (!e) return "—";
    const v = parseFloat(e.state);
    if (isNaN(v)) return e.state;
    return unit ? `${v.toFixed(1)} ${unit}` : v.toFixed(1);
  }

  _stateRaw(suffix) {
    const e = this._getEntity(suffix);
    if (!e) return null;
    return parseFloat(e.state);
  }

  _batteryIcon(v) {
    if (v === null) return "mdi:battery-unknown";
    if (v >= 13.0) return "mdi:battery";
    if (v >= 12.4) return "mdi:battery-80";
    if (v >= 12.0) return "mdi:battery-60";
    if (v >= 11.5) return "mdi:battery-40";
    return "mdi:battery-alert";
  }

  _batteryColor(v) {
    if (v === null) return "#9e9e9e";
    if (v >= 13.0) return "#4caf50";
    if (v >= 12.0) return "#ff9800";
    return "#f44336";
  }

  _speedColor(v) {
    if (v === null) return "#9e9e9e";
    if (v === 0) return "#4caf50";
    if (v < 80) return "#2196f3";
    if (v < 120) return "#ff9800";
    return "#f44336";
  }

  _render() {
    if (!this._hass || !this._config) return;

    const title = this._config.title || "Freematics ONE+";
    const speed = this._stateRaw("speed");
    const rpm = this._stateRaw("rpm");
    const battery = this._stateRaw("battery");
    const signal = this._stateRaw("signal");
    const lat = this._stateRaw("lat");
    const lng = this._stateRaw("lng");
    const coolant = this._stateRaw("coolant_temp");
    const engineLoad = this._stateRaw("engine_load");
    const throttle = this._stateRaw("throttle");
    const fuelPressure = this._stateRaw("fuel_pressure");
    const satellites = this._stateRaw("satellites");
    const accX = this._stateRaw("acc_x");
    const accY = this._stateRaw("acc_y");
    const accZ = this._stateRaw("acc_z");

    const speedColor = this._speedColor(speed);
    const battColor = this._batteryColor(battery);

    const hasGps = lat !== null && lng !== null;
    const mapsUrl = hasGps
      ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}&zoom=15`
      : null;

    const rpmPercent = rpm !== null ? Math.min((rpm / 7000) * 100, 100) : 0;
    const loadPercent = engineLoad !== null ? Math.min(engineLoad, 100) : 0;
    const throttlePercent = throttle !== null ? Math.min(throttle, 100) : 0;

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--primary-font-family, Roboto, sans-serif);
        }
        ha-card {
          padding: 16px;
          background: var(--card-background-color);
          border-radius: var(--ha-card-border-radius, 12px);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
        }
        .title {
          font-size: 1.2em;
          font-weight: 600;
          color: var(--primary-text-color);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .title ha-icon {
          color: #2196f3;
        }
        .signal {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .speed-container {
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 8px 0 16px;
        }
        .speed-value {
          font-size: 3.5em;
          font-weight: 700;
          color: ${speedColor};
          line-height: 1;
        }
        .speed-unit {
          font-size: 1.1em;
          color: var(--secondary-text-color);
          margin-left: 6px;
          margin-top: 18px;
        }
        .gauges {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          margin-bottom: 14px;
        }
        .gauge {
          background: var(--secondary-background-color);
          border-radius: 8px;
          padding: 10px 12px;
        }
        .gauge-label {
          font-size: 0.75em;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .gauge-value {
          font-size: 1.2em;
          font-weight: 600;
          color: var(--primary-text-color);
        }
        .bar-container {
          height: 6px;
          background: var(--divider-color);
          border-radius: 3px;
          margin-top: 6px;
          overflow: hidden;
        }
        .bar-fill {
          height: 100%;
          border-radius: 3px;
          transition: width 0.4s ease;
        }
        .info-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 12px;
        }
        .info-item {
          background: var(--secondary-background-color);
          border-radius: 8px;
          padding: 8px 10px;
          text-align: center;
        }
        .info-label {
          font-size: 0.7em;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .info-value {
          font-size: 1em;
          font-weight: 600;
          color: var(--primary-text-color);
          margin-top: 2px;
        }
        .battery-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          background: var(--secondary-background-color);
          border-radius: 8px;
          margin-bottom: 10px;
        }
        .battery-icon {
          color: ${battColor};
          font-size: 1.4em;
        }
        .battery-value {
          font-weight: 600;
          color: ${battColor};
        }
        .battery-label {
          color: var(--secondary-text-color);
          font-size: 0.85em;
        }
        .gps-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          background: var(--secondary-background-color);
          border-radius: 8px;
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .gps-row a {
          color: #2196f3;
          text-decoration: none;
          font-weight: 500;
        }
        .gps-row a:hover { text-decoration: underline; }
        .no-data {
          text-align: center;
          color: var(--secondary-text-color);
          padding: 20px;
        }
      </style>
      <ha-card>
        <div class="header">
          <div class="title">
            <ha-icon icon="mdi:car-connected"></ha-icon>
            ${title}
          </div>
          <div class="signal">
            <ha-icon icon="mdi:signal"></ha-icon>
            ${signal !== null ? `${signal} dBm` : "—"}
          </div>
        </div>

        <div class="speed-container">
          <div class="speed-value">${speed !== null ? Math.round(speed) : "—"}</div>
          <div class="speed-unit">km/h</div>
        </div>

        <div class="gauges">
          <div class="gauge">
            <div class="gauge-label">RPM</div>
            <div class="gauge-value">${rpm !== null ? Math.round(rpm) : "—"}</div>
            <div class="bar-container">
              <div class="bar-fill" style="width:${rpmPercent}%;background:#2196f3;"></div>
            </div>
          </div>
          <div class="gauge">
            <div class="gauge-label">Engine Load</div>
            <div class="gauge-value">${engineLoad !== null ? engineLoad.toFixed(1) + " %" : "—"}</div>
            <div class="bar-container">
              <div class="bar-fill" style="width:${loadPercent}%;background:${loadPercent > 80 ? "#f44336" : "#ff9800"};"></div>
            </div>
          </div>
          <div class="gauge">
            <div class="gauge-label">Throttle</div>
            <div class="gauge-value">${throttle !== null ? throttle.toFixed(1) + " %" : "—"}</div>
            <div class="bar-container">
              <div class="bar-fill" style="width:${throttlePercent}%;background:#9c27b0;"></div>
            </div>
          </div>
          <div class="gauge">
            <div class="gauge-label">Coolant Temp</div>
            <div class="gauge-value">${coolant !== null ? coolant.toFixed(1) + " °C" : "—"}</div>
            <div class="bar-container">
              <div class="bar-fill" style="width:${coolant !== null ? Math.min((coolant / 120) * 100, 100) : 0}%;background:${coolant !== null && coolant > 100 ? "#f44336" : "#4caf50"};"></div>
            </div>
          </div>
        </div>

        <div class="info-row">
          <div class="info-item">
            <div class="info-label">Fuel Press.</div>
            <div class="info-value">${fuelPressure !== null ? fuelPressure.toFixed(0) + " kPa" : "—"}</div>
          </div>
          <div class="info-item">
            <div class="info-label">GPS Sats</div>
            <div class="info-value">${satellites !== null ? Math.round(satellites) : "—"}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Acc X/Y/Z</div>
            <div class="info-value" style="font-size:0.8em;">
              ${accX !== null ? accX.toFixed(2) : "—"} /
              ${accY !== null ? accY.toFixed(2) : "—"} /
              ${accZ !== null ? accZ.toFixed(2) : "—"}
            </div>
          </div>
        </div>

        <div class="battery-row">
          <ha-icon class="battery-icon" icon="${this._batteryIcon(battery)}"></ha-icon>
          <span class="battery-value">${battery !== null ? battery.toFixed(2) + " V" : "—"}</span>
          <span class="battery-label">Battery Voltage</span>
        </div>

        ${hasGps ? `
        <div class="gps-row">
          <ha-icon icon="mdi:map-marker"></ha-icon>
          Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}
          &nbsp;|&nbsp;
          <a href="${mapsUrl}" target="_blank" rel="noopener">Open Map ↗</a>
        </div>
        ` : `
        <div class="gps-row">
          <ha-icon icon="mdi:map-marker-off"></ha-icon>
          GPS not available
        </div>
        `}
      </ha-card>
    `;
  }
}

customElements.define("freematics-vehicle-card", FreematicsVehicleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "freematics-vehicle-card",
  name: "Freematics Vehicle Card",
  description: "A card displaying live vehicle telemetry from the Freematics ONE+ device.",
  preview: false,
  documentationURL: "https://github.com/northpower25/Freematics",
});

console.info(
  `%c FREEMATICS-VEHICLE-CARD %c v${VERSION} `,
  "background:#2196f3;color:#fff;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px",
  "background:#1565c0;color:#fff;padding:2px 6px;border-radius:0 4px 4px 0"
);
