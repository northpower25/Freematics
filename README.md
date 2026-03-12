# Freematics ONE+ – Home Assistant Integration

A HACS-compatible Home Assistant integration for the **Freematics ONE+** OBD-II telematics device.  
The device pushes real-time vehicle telemetry (speed, RPM, GPS, engine sensors, battery voltage, …) directly to Home Assistant via a secure HTTPS webhook — no VPN, port forwarding, or public IP required.

📖 **[Full documentation (EN / DE)](docs/README.md)**

---

## Quick Start

1. Install via **HACS** → Custom Repositories → `https://github.com/northpower25/Freematics` (Category: Integration)
2. Restart Home Assistant
3. Add the **Freematics ONE+** integration under *Settings → Devices & Services*
4. Follow the 5-step wizard to configure connectivity and flash method
5. Flash the bundled firmware to your device (WiFi OTA or Serial USB)
6. Start driving — sensor entities are created automatically as data arrives

> `esptool` (needed for Serial USB flashing) is **automatically installed** with this integration. No manual setup required.

---

## Repository Structure

| Directory | Description |
|---|---|
| `custom_components/freematics/` | Home Assistant integration (HACS) |
| `firmware_v5/telelogger/` | Current Arduino/PlatformIO firmware source (ESP32) |
| `libraries/` | Arduino libraries for Freematics ONE+ and Esprit |
| `ESPRIT/` | Arduino library and examples for [Freematics Esprit](https://freematics.com/products/freematics-esprit) |
| `lovelace/` | Pre-built Lovelace dashboard YAML |
| `server/` | [Freematics Hub](https://freematics.com/hub/) server source |
| `docs/` | Full integration documentation |
| `old/` | Older firmware versions (v2 / v3 / v4) kept for reference |

---

## Features

- **Zero-config sensor creation** — entities appear automatically when the device sends its first payload
- **WiFi OTA flashing** — flash firmware directly from Home Assistant over WiFi (no USB required)
- **Serial USB flashing** — flash via USB; `esptool` bundled with integration
- **Live telemetry** — speed, RPM, throttle, engine load, coolant temp, GPS, accelerometer, battery voltage, signal strength
- **Custom Lovelace card** — colour-coded speed display, progress bars, GPS map link
- **Works with Nabu Casa** — no local network exposure required
- **WiFi + Cellular fallback** — seamless handover between WiFi and 4G/3G

---

## Supported Hardware

- [Freematics ONE+ Model A](https://freematics.com/products/freematics-one-plus/)
- [Freematics ONE+ Model B](https://freematics.com/products/freematics-one-plus-model-b/)
- [Freematics ONE+ Model H](https://freematics.com/products/freematics-one-plus-model-h/)

---

## License

BSD License — see [LICENSE](LICENSE).

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a full list of changes and release notes.

---

# Freematics ONE+ – Home Assistant Integration (Deutsch)

Eine HACS-kompatible Home Assistant Integration für das **Freematics ONE+** OBD-II Telematik-Gerät.  
Das Gerät sendet Echtzeit-Fahrzeugdaten direkt an Home Assistant über einen sicheren HTTPS-Webhook — ohne VPN, Port-Weiterleitung oder öffentliche IP.

📖 **[Vollständige Dokumentation (EN / DE)](docs/README.md)**

---

## Schnellstart

1. Installation über **HACS** → Benutzerdefinierte Repositories → `https://github.com/northpower25/Freematics` (Kategorie: Integration)
2. Home Assistant neu starten
3. Integration **Freematics ONE+** unter *Einstellungen → Geräte & Dienste* hinzufügen
4. Den 5-stufigen Assistenten für Verbindung und Flash-Methode durchlaufen
5. Firmware auf das Gerät flashen (WLAN OTA oder Seriell USB)
6. Losfahren – Sensor-Entitäten werden automatisch erstellt

> `esptool` (für Seriell-USB-Flashing) wird **automatisch mit dieser Integration installiert**. Keine manuelle Einrichtung erforderlich.

---

## Verzeichnisstruktur

| Verzeichnis | Beschreibung |
|---|---|
| `custom_components/freematics/` | Home Assistant Integration (HACS) |
| `firmware_v5/telelogger/` | Aktuelle Firmware-Quellen (Arduino/PlatformIO, ESP32) |
| `libraries/` | Arduino-Bibliotheken für Freematics ONE+ und Esprit |
| `ESPRIT/` | Arduino-Bibliothek und Beispiele für [Freematics Esprit](https://freematics.com/products/freematics-esprit) |
| `lovelace/` | Vorgefertigtes Lovelace-Dashboard (YAML) |
| `server/` | [Freematics Hub](https://freematics.com/hub/) Server-Quellcode |
| `docs/` | Vollständige Integrationsdokumentation |
| `old/` | Ältere Firmware-Versionen (v2 / v3 / v4) zur Referenz |

---

## Lizenz

BSD-Lizenz — siehe [LICENSE](LICENSE).

---

## Changelog

Alle Änderungen und Release Notes finden sich in [CHANGELOG.md](CHANGELOG.md).

