# Sunrise Alarm — Design

Date: 2026-09-28 · Status: draft for review

## Goal

Wake up to a simulated sunrise on two existing lamps, set from a phone, with no electrical modification
of the lamps. Either lamp can be used alone or both together.

## Hardware (all verified)

| Device | Role | Control path |
|---|---|---|
| Windows 11 PC (`my-windows-pc`, private VPN/mesh IP `<PC_VPN_IP>`, LAN `<PC_LAN_IP>`) | Always-on controller: web UI, scheduler, sunrise engine | — |
| ESP8266 IR board (`<IR_BOARD_IP>`, firmware ir_lab v3) | IR blaster for the Sunset lamp | HTTP `GET /send?proto=NEC&value=…&bits=32` |
| Sunset projection lamp | Lamp 1 | IR, NEC addr 0xEF00, 24 codes, 6 brightness levels |
| GCTECHING floor lamp (`MELK-OA10`, `<LAMP_BLE_MAC>`) | Lamp 2 | BLE from the PC: service FFF0, write FFF3 |

Reference data (codes, packets, calibration): `docs/HARDWARE-NOTES.md`.

Constraints discovered during bring-up:
- Both lamps respond to the **same 24 IR codes** with different meanings (Sunset "R" = floor "IC Set").
  The IR board **must be placed so only the Sunset lamp can see it.**
- PC Wi-Fi must stay on **5 GHz** (adapter "Preferred Band = Prefer 5GHz"); on 2.4 GHz the Intel combo
  radio starves BLE and the link drops every 5–15 s.
- Floor lamp green is ~3× strong, blue ~1.7× strong: colours are scaled G×0.3, B×0.6.

## Architecture

One Python process on the Windows PC (`%USERPROFILE%\sunlight\`, own venv), started at logon by Task
Scheduler, listening on port 8765 (reachable over a private VPN/mesh network, e.g. Tailscale/Headscale,
from the phone).

```
Phone ──VPN/mesh──► sunlight service (Windows PC)
                      ├── web UI + JSON API        (aiohttp)
                      ├── settings.json            (persisted config)
                      ├── scheduler                (asyncio loop, 30 s tick)
                      ├── sunrise engine           (progress p: 0→1, one master curve)
                      │     ├── FloorDriver  → BLE (bleak) → MELK-OA10
                      │     └── SunsetDriver → HTTP → ESP8266 → IR → Sunset lamp
                      └── sunlight.log             (runs, failures)
```

Units, each testable in isolation:

| Unit | Responsibility | Depends on |
|---|---|---|
| `curve.py` | `curve(p) -> (r, g, b, brightness)` from keyframes with smoothstep; pure | nothing |
| `floor.py` | `FloorDriver`: hold BLE link, `apply(r,g,b,brightness)`, reconnect, calibration + fine dimming | bleak |
| `sunset.py` | `SunsetDriver`: map p to the 11 IR stages, track level, send via HTTP | urllib |
| `engine.py` | Run a sunrise: clock, per-lamp drivers, demo vs alarm timing, stop | curve, drivers |
| `scheduler.py` | Decide when to start (wake time − length, enabled days), hold, auto-off | engine, settings |
| `settings.py` | Load/validate/save `settings.json` | nothing |
| `web.py` | UI page + API | engine, scheduler, settings |

## Settings (defaults)

| Setting | Default |
|---|---|
| Wake time | 06:30 |
| Days | Mon–Fri |
| Sunrise length | 30 min (range 10–60), ends at wake time |
| Hold after sunrise | 30 min at full, then off (or "stay on") |
| Lamps | Floor ✓, Sunset ✓ (each toggleable) |
| Alarm enabled | ✓ |

## Sunrise curve

Master progress `p` from 0 to 1 over the sunrise length. Keyframes (standard RGB, brightness 0–1),
interpolated with smoothstep between neighbours:

| p | R | G | B | Brightness |
|---|---|---|---|---|
| 0.00 | 80 | 0 | 0 | 0.005 |
| 0.10 | 140 | 5 | 0 | 0.015 |
| 0.20 | 200 | 15 | 0 | 0.04 |
| 0.35 | 255 | 45 | 0 | 0.09 |
| 0.50 | 255 | 95 | 5 | 0.18 |
| 0.62 | 255 | 135 | 30 | 0.30 |
| 0.72 | 255 | 160 | 60 | 0.44 |
| 0.82 | 255 | 185 | 95 | 0.60 |
| 0.91 | 255 | 205 | 125 | 0.78 |
| 1.00 | 255 | 220 | 150 | 1.00 |

**Floor lamp** (verified smooth in a 30 s demo): every 0.4 s compute the curve; brightness is sent as
`pct = ceil(brightness×100)` and the RGB is multiplied by `brightness×100/pct` (fine dimming — the lamp
only accepts whole percent). Apply G×0.3, B×0.6. Only changed packets are sent.

**Sunset lamp** (verified): setup ON, R, Bright− ×7 (level 0); then stages at
p = 0.00 R0, .18 R1, .32 OrangeRed1, .44 OrangeRed2, .54 Orange2, .63 Orange3, .71 LightOrange3,
.79 LightOrange4, .86 Yellow4, .93 Yellow5, 1.00 W5. Colour codes sent twice (idempotent); Bright+ once.

## Timing semantics

- **Alarm mode:** clock is wall time; sunrise ends exactly at wake time. If a link drops, the lamp holds
  its colour and resumes at the *current* p after reconnect (skips ahead).
- **Demo mode:** length chosen on the page (default 30 s); clock **pauses** while a link is down so
  nothing is skipped.
- The floor BLE link is opened **2 minutes before** sunrise start (first connect can take ~20 s) and held
  for the whole run.

## Web UI

Single page, phone-friendly: wake time, days, length, hold, per-lamp toggles, alarm on/off, **Save**,
**Demo** (with length), **Stop / I'm up**, and status: next alarm, running/idle, current p, per-lamp link
state, last run result. JSON API mirrors the page (`GET/PUT /api/settings`, `POST /api/demo`,
`POST /api/stop`, `GET /api/status`) for future automation.

## Error handling

| Failure | Behaviour |
|---|---|
| BLE link drops | Reconnect loop (connect by scanning, 20 s timeout), resume per timing mode; logged |
| BLE unavailable for whole run | Floor lamp skipped, Sunset continues; status shows "floor: unreachable" |
| IR board unreachable | Check `/version` before start and retry each command 2×; Sunset skipped if down; logged |
| PC Bluetooth radio off | Status shows "Bluetooth off"; alarm still runs Sunset lamp |
| Service crash | Task Scheduler restarts it; run state not resumed (acceptable for v1) |
| PC asleep | Service requests "system required" during runs and registers a wake timer 5 min before start |
| Stop pressed | Both lamps off immediately; run cancelled |

## Testing

- **Unit (pytest, no hardware):** `curve` keyframe values and monotonic brightness; fine-dimming maths;
  Sunset stage mapping; scheduler start-time/day logic incl. midnight wrap; settings validation.
- **Driver fakes:** engine tested with fake drivers recording commands (order, idempotent retries,
  pause vs skip semantics).
- **Hardware smoke (manual, scripted):** demo 30 s on each lamp alone and both together; confirm the
  floor lamp does **not** react to the Sunset IR once the board is placed.
- **Soak:** one real 30 min sunrise scheduled a few minutes ahead, then an actual morning.

## Out of scope (v1)

Floor-lamp effects/music modes, multiple alarms per day, phone-alarm integration, ESP32 bridge
(only if Windows BLE proves unreliable in the soak test), public GitHub release (planned after v1).
