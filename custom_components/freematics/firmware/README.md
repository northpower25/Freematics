# Freematics ONE+ Firmware

This directory contains the pre-compiled firmware binary for the Freematics ONE+.

## File

- `telelogger.bin` – compiled firmware binary (ESP32, flash at offset `0x10000`)

## Firmware Version

Version: 5.x (from `firmware_v5/telelogger`)
Protocol: includes `PROTOCOL_HA_WEBHOOK` (value 4) for direct Home Assistant integration

## Building from Source

To compile the firmware yourself:

1. Install [PlatformIO](https://platformio.org/)
2. Open `firmware_v5/telelogger/` in PlatformIO
3. Configure `config.h` or `Kconfig.projbuild` with your settings
4. Run: `pio run`
5. Find the compiled binary at `.pio/build/esp32dev/firmware.bin`
6. Replace `telelogger.bin` in this directory with the new binary

## Flash Offsets (ESP32)

| Component | Offset |
|---|---|
| Bootloader | `0x1000` |
| Partition table | `0x8000` |
| Application | `0x10000` |

The integration only flashes the application at `0x10000`. Bootloader and
partition table are already programmed from the factory.
