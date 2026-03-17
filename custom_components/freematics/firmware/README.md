# Freematics ONE+ Firmware

This directory contains the pre-compiled firmware binary for the Freematics ONE+.

## Files

- `telelogger.bin` – compiled firmware binary (ESP32, flash at offset `0x10000`)
- `bootloader.bin` – second-stage bootloader binary (ESP32, flash at offset `0x1000`, DIO/40 MHz)

## Firmware Configuration

The bundled firmware is compiled with these settings (see `firmware_v5/telelogger/platformio.ini`):

- **`ENABLE_WIFI=1`** – WiFi + cellular co-operation enabled; WiFi SSID and password
  are loaded at boot from the NVS partition provisioned by the HA integration.
- **`SERVER_PROTOCOL=3`** – HTTPS POST (compatible with the HA webhook integration).
  Server host, port, and webhook path are loaded at boot from NVS.

On first boot the device reads its configuration from NVS (written by the HA
integration's `config_nvs.bin` / `flash_image.bin`):

| NVS key       | Description                                     |
|---------------|-------------------------------------------------|
| `WIFI_SSID`   | WiFi network SSID                               |
| `WIFI_PWD`    | WiFi network password                           |
| `CELL_APN`    | Cellular APN (empty = auto-detect)              |
| `SERVER_HOST` | Home Assistant hostname / Nabu Casa domain      |
| `SERVER_PORT` | HTTPS port (usually 443)                        |
| `WEBHOOK_PATH`| Full path: `/api/webhook/<webhook_id>`          |
| `ENABLE_HTTPD`| 1 = start built-in HTTP server for WiFi OTA     |

## Building from Source

The firmware is automatically rebuilt by the `Build Firmware` GitHub Actions
workflow whenever source files in `firmware_v5/telelogger/` or `libraries/`
change.  The updated binaries (`telelogger.bin` and `bootloader.bin`) are
committed back automatically.

To compile the firmware manually:

1. Install [PlatformIO](https://platformio.org/)
2. Open `firmware_v5/telelogger/` in PlatformIO
3. Run: `pio run --environment esp32dev`
4. Find the compiled binaries at:
   - `.pio/build/esp32dev/firmware.bin` → replace `telelogger.bin`
   - `.pio/build/esp32dev/bootloader.bin` → replace `bootloader.bin`

## Flash Offsets (ESP32)

| Component              | Offset    |
|------------------------|-----------|
| Bootloader             | `0x1000`  |
| Partition table        | `0x8000`  |
| NVS partition          | `0x9000`  |
| Application            | `0x10000` |

The integration's **Web Serial / esp-web-tools flash** writes:
- `bootloader.bin` at `0x1000` (**critical** — esp-web-tools erases the chip on first install, wiping the factory bootloader)
- `partition_table.bin` (generated) at `0x8000`
- `telelogger.bin` at `0x10000`
- `config_nvs.bin` (NVS with WiFi/server settings) at `0x9000`

The **combined `flash_image.bin`** (downloaded from the integration panel)
includes the bootloader, partition table, NVS, and firmware merged into one
file that is written at `0x1000` using:
```
python -m esptool write-flash 0x1000 flash_image.bin
```

> **Why 0x1000?** The second-stage bootloader lives at 0x1000. esp-web-tools
> performs a full chip erase on the first installation, which wipes it. Without
> restoring the bootloader the device loops with `flash read err, 1000 /
> ets_main.c 371`. The combined image starts at 0x1000 so a single esptool
> command restores everything, including the bootloader.
