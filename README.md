# Sunlight Ctrl — a sunrise alarm from two unmodified cheap RGB lamps

Wakes you up with a simulated sunrise using **two ordinary, unmodified consumer RGB lamps** — no
soldering, no LED strip rewiring, no touching mains wiring. A small ESP8266 "smart IR" board and a
Python service drive the lamps through their own stock remote-control channels (infrared and
Bluetooth Low Energy) exactly as if a person were pressing buttons, just gradually and on a schedule.

If you searched for any of these and landed here, this project is probably relevant to you:

- `ESP8266/ESP32 Infrared Transmitting And Receiving NEC Command WIFI Transparent Transmission Module`
- Board silkscreen `ESP32_IR_TR_WIFI (303ESP32IR)` — **despite the "ESP32" printed on the board, the
  unit that actually shipped uses an ESP8266**, not an ESP32
- 24-key NEC infrared RGB remote, address `0xEF00`
- `MELK-OA10` Bluetooth LE floor lamp / "LotusLamp X" app / ELK-BLEDOM-style BLE protocol
- GCTECHING 120 cm RGB floor lamp bar
- 16-color sunset/sunset-projection lamp (NEC IR remote, same 24-key layout)

## What it is

- Two cheap lamps already sitting in a bedroom:
  1. A **16-color sunset projection lamp**, controlled only over infrared (NEC protocol).
  2. A **GCTECHING 120 cm RGB floor lamp**, which has both an IR remote and a Bluetooth LE
     interface — controlled here over BLE for smooth continuous color/brightness fades.
- A cheap **ESP8266-based "IR WiFi transparent transmission" board** acts as the IR blaster/receiver
  for the sunset lamp, reachable over HTTP on the LAN.
- A **Python service** (aiohttp) runs continuously, exposes a small phone-friendly web UI + JSON API,
  and on a schedule (or on demand, for a demo) drives both lamps along one shared sunrise color curve —
  red → orange → yellow → warm white — over a configurable duration, ending at wake time.
- Neither lamp is opened, modified, or rewired. Everything goes through the manufacturer's own
  IR/BLE control surface.

## Hardware list (exact, searchable names)

| Item | Product / identifier | Role |
|---|---|---|
| IR bridge board | "ESP8266/ESP32 Infrared Transmitting And Receiving NEC Command WIFI Transparent Transmission Module", silkscreen `ESP32_IR_TR_WIFI (303ESP32IR)` — **actual chip is an ESP8266**, not the ESP32 the silkscreen/listing implies | Sends/receives NEC IR to control the sunset lamp; reachable over Wi-Fi/HTTP |
| Remote 1 | 24-key NEC RGB remote, address `0xEF00` | Controls the sunset lamp (also reaches the floor lamp's IR receiver if it's in line of sight — see below) |
| Lamp 1 | 16-color sunset/sunset-projection lamp | Warm ambient IR-only lamp, 6 brightness levels, 16 fixed colors |
| Lamp 2 | GCTECHING 120 cm RGB floor lamp bar (remote manual: Clas Ohlson `SP-03LS3M-RGBPMD`) | Main light source; controlled via BLE for continuous RGB/brightness |
| BLE identity | Advertises as `MELK-OA10` (exact name has trailing spaces, e.g. `MELK-OA10   70`); paired app "LotusLamp X"; protocol family ELK-BLEDOM | GATT service `FFF0`, write characteristic `FFF3` (write-without-response), notify characteristic `FFF4` |

## Key discoveries (things that cost real debugging time)

- **No USB-serial on the IR board.** The board that actually shipped has no exposed
  USB-to-UART bridge at all — there is no way to flash it over a cable out of the box. The *only*
  way to load custom firmware onto it is **over the air, through the stock firmware's own web
  update page**, then via the custom firmware's own `/update` OTA page on every subsequent update.
  See `firmware/README.md` for the full ir_lab (ESP8266, OTA-only) firmware story, including the
  crash-loop "safe mode" designed specifically so a bad OTA build can never brick the board.
- **Both lamps understand the same 24 IR codes, but interpret them completely differently.**
  The sunset lamp and the floor lamp's IR receiver both use NEC address `0xEF00` with the identical
  24 command values from the same style of 24-key remote — but each lamp maps a given code to a
  *different* button/behavior (e.g. the sunset lamp's "R" button is the floor lamp's "IC Set").
  Practical consequence: **the IR emitter must be physically aimed/shielded so only the sunset lamp
  can see it**, or every "sunset lamp" command also hits the floor lamp in an unpredictable way.
- **2.4 GHz Wi-Fi/Bluetooth coexistence on Intel combo Wi-Fi/BT cards breaks BLE.** When the
  controlling PC's Wi-Fi adapter is on the 2.4 GHz band, the shared Intel radio starves the
  Bluetooth stack and the BLE link to the floor lamp drops every 5–15 seconds. Fix: force the PC's
  Wi-Fi adapter to prefer/only use **5 GHz**.
- **Color calibration for the floor lamp:** its green channel renders roughly 3× too strong and
  blue roughly 1.7× too strong compared to a standard sunrise RGB palette, so colors sent to it are
  scaled **green × 0.3, blue × 0.6** before being written over BLE.
- **Fine dimming trick:** the floor lamp's BLE brightness command only accepts whole percentage
  points (0–100), which is too coarse near the very dark start of a sunrise. The workaround sends
  brightness as `ceil(brightness × 100)` and then compensates by scaling the RGB values by
  `brightness×100/pct`, so the *perceived* brightness stays smooth even though the lamp's own
  brightness field only moves in whole-percent steps.

## Architecture

```
Phone / browser
      │  HTTP (web UI + JSON API)
      ▼
Python service (aiohttp), one process, always-on
      ├── settings.json            persisted schedule/config
      ├── scheduler                decides when to start a sunrise
      ├── sunrise engine           one master curve, progress p: 0 → 1
      │     ├── FloorDriver  ──BLE──► GCTECHING / MELK-OA10 floor lamp
      │     └── SunsetDriver ─HTTP──► ESP8266 IR board ─IR──► sunset lamp
      └── log                      run history, failures
```

Both drivers consume the same normalized sunrise curve (`curve.py`): a set of RGB + brightness
keyframes from deep red at `p=0` to warm white at `p=1`, interpolated with smoothstep. The floor
lamp gets near-continuous updates over BLE; the IR-only sunset lamp is mapped to the closest of its
fixed colors/brightness steps and only re-sent when the target actually changes.

## Remote access (optional)

The service only needs to be reachable on your home LAN, but if you want to reach it from your phone
off-network, a private VPN/mesh overlay (e.g. Tailscale/Headscale) plus a local reverse proxy works
well. A minimal Caddy example, terminating TLS for your own domain and forwarding to the service:

```
example.com:8444 {
    reverse_proxy 127.0.0.1:8765
}
```

If you use split-horizon DNS for your own domain over Tailscale/Headscale, point it at your VPN/mesh
IP rather than relying on public DNS — this avoids campus/hotel Wi-Fi resolvers caching an `NXDOMAIN`
for a name that only resolves privately.

## Quick start

1. Flash the IR bridge board with the OTA-only firmware in `firmware/ir_lab/ir_lab.ino` (first flash
   goes through the *stock* firmware's own upload page; see `firmware/README.md` for the full
   OTA flow and the `SUNLIGHT_IR` fallback access point).
2. Confirm the sunset lamp's IR codes and the floor lamp's BLE protocol against `firmware/ir_codes.md`
   (NEC address `0xEF00`, 24 codes; BLE service `FFF0` / write char `FFF3`).
3. Set up the Python service in `service/` (see `service/requirements.txt`), and configure it with
   the IR board's address and the floor lamp's BLE address via the `SUNLIGHT_IR_HOST` and
   `SUNLIGHT_FLOOR_ADDRESS` environment variables (see `docs/HARDWARE-NOTES.md` for how to find
   the BLE address — scan for a device name starting with `MELK`).
4. Run the service, open its web UI on your phone, set a wake time, and try **Demo** before trusting
   it for a real morning.
5. Aim/position the IR emitter so only the sunset lamp can see it, since both lamps decode the same
   IR codes differently.

## Controls: web page, API and iPhone Shortcuts

The phone web page has **Demo**, **🌅 Sunrise now**, **☀ I'm up** (jump to full brightness and stay
lit, then the usual hold / auto-off) and **■ Lights off** (cancel and turn both lamps off — always
wins over "I'm up"). The same actions are plain HTTP endpoints:

| Endpoint | Method | Does |
|---|---|---|
| `/api/sunrise-now` | POST `{"minutes": 20}` | start a real sunrise now |
| `/api/wake` | POST | I'm up |
| `/api/stop` | POST | Lights off |
| `/api/settings` | GET / PUT | read / change wake time, days, length, lamps, alarm on/off |
| `/api/status` | GET | state, progress, lamp links, next sunrise |

**Remote page (`/remote`):** on-screen copies of both 24-key remotes (each button sends its real NEC code through the ESP8266 board — `POST /api/ir {"code": "F720DF"}`) plus a Bluetooth card for the floor lamp: on/off, colour picker (calibrated), 1–100% brightness and presets — `POST /api/floor` with `{"power": "on"}`, `{"rgb": [255,100,0]}` or `{"brightness": 30}`. Both lamps obey the same IR codes, so aim the IR board at one lamp.

[docs/SHORTCUTS.md](docs/SHORTCUTS.md) shows how to wire these to Apple Shortcuts: "I'm up" when your
iPhone alarm is stopped, "Hey Siri, lights off", a one-tap "Set sunrise", and "Hey Siri, sunrise now".

## Photos

- `docs/photos/remote-floor-lamp.jpg` — the GCTECHING floor lamp's remote (`SP-03LS3M-RGBPMD`).
- `docs/photos/remote-sunset-lamp.jpg` — the 24-key NEC remote used with the sunset/projection lamp.
- `docs/photos/stock-firmware-wifimanager.png` — the IR board's stock firmware Wi-Fi setup page.
- `docs/photos/ir-lab-firmware-page.png` — the custom `ir_lab` firmware's own web UI/OTA page.

## Status

Working design for a single-household sunrise alarm; see `docs/DESIGN.md` for the full design record.
