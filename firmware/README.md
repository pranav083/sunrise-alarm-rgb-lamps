# Sunlight Ctrl - ESP32 IR Firmware

Dev environment: macOS (Apple Silicon), `arduino-cli` (Homebrew), ESP32 core
`esp32:esp32` v3.3.12, library `IRremoteESP8266` v2.9.0.

## Sketches

- `ir_capture/ir_capture.ino` - Listens on `IR_RECV_PIN` (default GPIO 14),
  decodes IR remote signals with IRremoteESP8266, and prints protocol name,
  address, command, value (hex), bit count, and the raw timing array for
  every received code (via `resultToSourceCode()` plus an explicit raw dump),
  so unknown protocols can still be replayed with `IRsend` on `IR_SEND_PIN`
  (default GPIO 4). **Both pin numbers are defaults and must be verified
  against the actual ESP32E-N4 IR board wiring before use** - see the
  `#define` comments at the top of the file.
- `pin_probe/pin_probe.ino` - Polls a safe set of candidate GPIOs
  (`{2,4,5,12,13,14,15,16,17,18,19,21,22,23,25,26,27,32,33,34,35,36,39}`) as
  `INPUT` and reports any pin that toggles, to help discover which GPIO the
  onboard IR receiver is actually wired to (press and hold a remote button
  near the board while watching the serial output). Strapping/UART/flash
  pins (0, 1, 3, 6-11) are intentionally excluded as unsafe to probe.

## One-time environment setup (already done on this machine)

```bash
# Add the ESP32 boards index and install the core
arduino-cli config init --overwrite
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32

# Install the IR library (pin to 2.9.0+; older 2.8.x fails to build against
# esp32 core 3.x's new timer API - see Troubleshooting below)
arduino-cli lib install "IRremoteESP8266@2.9.0"

# Install esptool (used by arduino-cli under the hood for flashing, and
# useful standalone for chip info / manual flashing)
brew install esptool
# If Homebrew is unavailable, install for the current user only (no sudo):
#   pip install --user esptool
#   pipx install esptool

# Apple Silicon note: some builtin Arduino tools (e.g. ctags 5.8-arduino11)
# only ship an x86_64 macOS binary, so Rosetta 2 is required:
softwareupdate --install-rosetta --agree-to-license
```

## Detect the board's serial port

Plug in the ESP32 board via USB, then run:

```bash
ls /dev/cu.*
```

Look for something like `/dev/cu.usbserial-XXXXXXXX` (CP210x) or
`/dev/cu.wchusbserial-XXXXXXXX` / `/dev/cu.SLAB_USBtoUART` (CH340/CP210x
depending on the onboard USB-UART chip). Alternatively:

```bash
arduino-cli board list
```

## Compile

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 ir_capture
arduino-cli compile --fqbn esp32:esp32:esp32 pin_probe
```

Both compile cleanly as of this setup:

- `ir_capture`: 331028 bytes flash (25%), 22764 bytes RAM (6%)
- `pin_probe`: 272536 bytes flash (20%), 22204 bytes RAM (6%)

## Upload

Replace `<port>` with the value found above (e.g. `/dev/cu.usbserial-0001`):

```bash
arduino-cli upload -p <port> --fqbn esp32:esp32:esp32 ir_capture
arduino-cli upload -p <port> --fqbn esp32:esp32:esp32 pin_probe
```

## Monitor serial output

```bash
arduino-cli monitor -p <port> -c baudrate=115200
```

(Ctrl+C to exit.)

## Troubleshooting

- **Port does not appear in `/dev/cu.*`**: The board's USB-to-serial chip
  driver is likely missing.
  - **CP210x** (Silicon Labs) chips: install the
    [CP210x VCP driver](https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers)
    for macOS, then unplug/replug the board (may require a reboot on newer
    macOS due to kernel extension approval in System Settings > Privacy &
    Security).
  - **CH340/CH341** chips: install the
    [WCH CH34x macOS driver](https://github.com/WCHSoftGroup/ch34xser_macos)
    (or the widely used community build), then unplug/replug and approve
    the kernel extension if prompted.
  - After installing a driver, always fully unplug and replug the USB cable
    (a simple re-run of `ls /dev/cu.*` right after driver install is often
    not enough).
- **`ctags: bad CPU type in executable`** on Apple Silicon: the builtin
  `ctags` tool used by `arduino-cli` for library header parsing only ships
  as an x86_64 macOS binary. Install Rosetta 2 (`softwareupdate
  --install-rosetta --agree-to-license`) to resolve.
- **IRremoteESP8266 fails to compile** with errors like `'timerAlarmEnable'
  was not declared`: this means an old IRremoteESP8266 version (<=2.8.6) is
  installed against esp32 core 3.x, which changed the Arduino-ESP32 timer
  API. Upgrade the library: `arduino-cli lib install "IRremoteESP8266@2.9.0"`.
- Do **not** attempt `arduino-cli upload` until `arduino-cli board list` (or
  `ls /dev/cu.*`) actually shows the board's port - uploading blind will
  just fail or target the wrong port.

---

# ir_lab - ESP8266 OTA-only firmware (real IR lab board)

This is a **separate, different board** from the ESP32 sketches above: an
ESP8266 module with **no serial/USB-TTL access at all**. It came flashed
with stock firmware whose "info" page reports: ESP8266 core 3.0.2, CPU
80MHz, flash size 4194304 bytes (4MB), current sketch 410576 bytes, OTA
free space ~540KB. IR pins are taken from the Tasmota template for this
board: **IR send = GPIO4, IR recv = GPIO14**.

Because there is no serial access, **the only way to load or replace
firmware on this board is Over-The-Air (OTA), through a web page it
serves itself.** If a build fails to bring up Wi-Fi and that web update
page, the board is bricked until a USB-TTL adapter is bought and wired to
the bare pins. Every design decision in `ir_lab/ir_lab.ino` exists to make
that failure mode as unlikely as possible - see the safety comment block
at the top of the file.

## Environment (this machine)

```bash
arduino-cli config set board_manager.additional_urls \
  https://arduino.esp8266.com/stable/package_esp8266com_index.json
arduino-cli core update-index
arduino-cli core install esp8266:esp8266   # installed: 3.1.2
```

`IRremoteESP8266@2.9.0` (already installed) is reused as-is.

## Build

```bash
cd firmware
arduino-cli compile \
  --fqbn "esp8266:esp8266:generic:eesz=4M2M,FlashMode=dout,xtal=80,baud=115200" \
  --export-binaries --output-dir ir_lab/build ir_lab
cp ir_lab/build/ir_lab.ino.bin ir_lab.bin
```

Board options used and why:

- `eesz=4M2M` - 4MB flash (matches the real chip), 2MB reserved for
  LittleFS, remainder split into two OTA-swappable app slots.
- `FlashMode=dout` - most compatible flash read mode; safest default when
  the exact flash chip on a random lab board isn't verified.
- `xtal=80` - 80MHz CPU, matching the stock firmware.
- `baud=115200` - only affects the (unused) serial bootloader link speed;
  harmless since there is no serial connection anyway.

Current build: **432784 bytes** (`ir_lab/ir_lab.ino`, esp8266 core 3.1.2),
comfortably under the ~480000-byte ceiling implied by the board's reported
OTA free space. Final artifact: `firmware/ir_lab.bin`.

## Flashing over OTA (no serial, no USB-TTL)

**First-time flash from the stock firmware:**

1. Connect a phone or laptop to the board's existing stock Wi-Fi /
   update page (whatever the stock firmware exposes) and use its own
   OTA/upload mechanism to upload `firmware/ir_lab.bin`. Wait for it to
   finish and let the board reboot - do not power-cycle mid-upload.

**After `ir_lab.ino` is running (first boot or any later boot):**

1. Join the Wi-Fi network **`SUNLIGHT_IR`** (open, no password) from a
   phone or laptop.
2. Browse to **`http://192.168.4.1`** (also reachable at
   `http://sunlight-ir.local` if your device supports mDNS). This page
   shows safe-mode status, uptime, free heap, Wi-Fi status, and the last
   30 IR captures.
3. Click **Firmware update**, or go directly to
   `http://192.168.4.1/update`, choose the new `.bin` file, and upload.
   Wait for the board to report success and reboot on its own. Do not
   power-cycle it during the upload.
4. To get the board on your home Wi-Fi (so you can reach it without
   staying on its AP), go to **`/wifi`**, enter your SSID/password, and
   submit. The board saves it to `/wifi.txt` on LittleFS and restarts;
   the `SUNLIGHT_IR` access point stays available regardless, so you
   always have a fallback way in even if the home Wi-Fi credentials are
   wrong.
5. All future firmware updates go through the same `/update` page - no
   serial connection is ever required again as long as each update keeps
   this same safety design.

## Web routes

- `/` - status + table of the last 30 IR captures (protocol, address,
  command, value, bit count), auto-refreshing every 2s.
- `/update` - firmware upload page (`ESP8266HTTPUpdateServer`), no
  password.
- `/wifi` - GET shows a form, POST saves SSID/password to `/wifi.txt`
  and restarts after ~1s.
- `/send?proto=NEC&value=0xF7C03F&bits=32` - transmits an IR code via
  `IRsend` on GPIO4. `/send` with no args shows a small form instead.
- `/json` - the same recent-captures list as machine-readable JSON, for
  scripting from a Mac on the same LAN.
- `/restart` - reboots the board.

## Safe mode (crash-loop protection)

A boot counter is kept in RTC user memory (survives reset/crash, not
power loss). Every boot increments it; if it reaches 3 without 30
uninterrupted seconds of uptime in between, the firmware enters
**safe mode**: Wi-Fi AP, web server, and `/update` still come up exactly
as normal, but IR init (`IRrecv`/`IRsend`) is skipped, in case the IR
peripherals or their libraries are ever implicated in a crash loop. The
counter resets to zero after 30s of stable uptime, and is also cleared
immediately on any *voluntary* restart (from `/wifi` or `/restart`) so
that intentionally reconfiguring the board a few times in a row never
falsely triggers safe mode. The `/` page shows in red when safe mode is
active.

## Concerns / notes for future maintainers

- No password on `/update`, `/wifi`, or `/send` - acceptable for a lab
  board on a private AP, but do not reuse this sketch on anything
  Internet-facing without adding auth.
- `WiFi.persistent(false)` is used so STA credentials are never written
  to SDK flash config (avoids a class of flash-corruption bricking);
  home Wi-Fi credentials are instead kept in a plain-text `/wifi.txt` on
  LittleFS, read back at each boot.
- If `/wifi.txt` is missing or LittleFS fails to mount, the firmware
  simply stays AP-only rather than blocking or attempting a destructive
  LittleFS format - always keeping `192.168.4.1` reachable.
- The recent-captures ring buffer is fixed-size, plain `char[600]`
  arrays (no dynamic `String` growth in the capture path), to keep heap
  usage predictable during real-time IR decoding.
