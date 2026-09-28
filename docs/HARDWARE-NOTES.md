# IR codes

Board: ESP8266 IR board at `<IR_BOARD_IP>` (its own mDNS name, e.g. sunlight-ir.local), firmware v3. Receive GPIO14, send GPIO4 — both confirmed (2026-09-28).

## Remote 1 — Sunset projection lamp (16-color) — 24-key RGB remote

Protocol NEC, 32 bits, address 0xEF00. Held buttons emit NEC repeat frames (value 0xFFFF…, bits=0) — ignore.
All 24 codes captured from the remote and verified by sending from the board to the lamp (2026-09-28).

| Button | Cmd | Value | Notes |
|---|---|---|---|
| Brightness up | 0x00 | 0xF700FF | |
| Brightness down | 0x01 | 0xF7807F | |
| OFF | 0x02 | 0xF740BF | |
| ON | 0x03 | 0xF7C03F | |
| R | 0x04 | 0xF720DF | sunrise step 1 |
| G | 0x05 | 0xF7A05F | |
| B | 0x06 | 0xF7609F | |
| W | 0x07 | 0xF7E01F | sunrise final |
| Orange-red (row 3 col 1) | 0x08 | 0xF710EF | sunrise step 2 |
| Light green (row 3 col 2) | 0x09 | 0xF7906F | |
| Light blue (row 3 col 3) | 0x0A | 0xF750AF | lamp renders it purple-ish |
| FLASH | 0x0B | 0xF7D02F | |
| Orange (row 4 col 1) | 0x0C | 0xF730CF | sunrise step 3 |
| Cyan (row 4 col 2) | 0x0D | 0xF7B04F | |
| Purple (row 4 col 3) | 0x0E | 0xF7708F | |
| STROBE | 0x0F | 0xF7F00F | |
| Light orange (row 5 col 1) | 0x10 | 0xF708F7 | sunrise step 4 |
| Teal (row 5 col 2) | 0x11 | 0xF78877 | |
| Violet (row 5 col 3) | 0x12 | 0xF748B7 | |
| FADE | 0x13 | 0xF7C837 | |
| Yellow (row 6 col 1) | 0x14 | 0xF728D7 | sunrise step 5 |
| Dark blue (row 6 col 2) | 0x15 | 0xF7A857 | |
| Pink (row 6 col 3) | 0x16 | 0xF76897 | |
| SMOOTH | 0x17 | 0xF7E817 | |

**Brightness:** 6 levels (full + 5 Bright− steps; presses beyond 5 do nothing). Measured 2026-09-28.
Brightness level is kept across colour changes (sunrise preview confirmed).

**Sunrise (verified working 2026-09-28, remote.html):** ON → R → Bright− ×7 (level 0), then 11 stages at
fractions of total time: R0 0.00, R1 .18, OrangeRed1 .32, OrangeRed2 .44, Orange2 .54, Orange3 .63,
LightOrange3 .71, LightOrange4 .79, Yellow4 .86, Yellow5 .93, W5 1.00. Colour sent twice (idempotent), Bright+ once.

Send via: `http://<IR_BOARD_IP>/send?proto=NEC&value=0xF7C03F&bits=32`
Wi-Fi drops ~1 in 6 packets on this 2.4 GHz channel — send each command 2–3× in automation.

## Remote 2 — RGB floor lamp (GCTECHING 120 cm) — addressable strip remote (IC Set, C3/C7/C16, Meteor)

**Same 24 NEC codes as Remote 1 (address 0xEF00)** — each lamp interprets them per its own layout, so any IR
command hits both lamps if both see the board. Floor-lamp meaning by position: 0x00 ↑, 0x01 ↓, 0x02 w/ww
(warm/cool white), 0x03 power toggle, 0x04 IC Set, 0x08 CS (single-colour / sound modes), 0x0C C3, 0x10 C7,
0x14 C16, 0x17 Meteor. Colour selection is "press N times" and the lamp stores last state → not reliable
for automation. Manual for this remote: Clas Ohlson SP-03LS3M-RGBPMD.

**Use Bluetooth for this lamp instead** (verified 2026-09-28): advertises as `MELK-OA10   70`
(don't confuse it with a neighbour's similarly-named BLE lamp advertising nearby — check the name
starts with `MELK`). App: LotusLamp X. GATT service FFF0, write char FFF3
(write without response), notify char FFF4. ELK-BLEDOM-style packets:

| Action | Packet (hex) |
|---|---|
| MELK init (send first) | `7e0783`, `7e0404` |
| Power on | `7e0404f00001ff00ef` |
| Power off | `7e0404000000ff00ef` |
| Colour RGB | `7e070503 RR GG BB 10ef` |
| Brightness 0–100 | `7e0401 BB ff000000ef` |

**Colour calibration:** green LEDs are ~3× too strong. (255,80,0) looks yellow; **(255,30,0) = orange**.
Scale G by ~0.3 when converting a standard sunrise palette. 1% brightness works and is dimmer than the
Sunset lamp's IR minimum.

**Windows PC controller (verified 2026-09-28):** `ssh my-windows-pc` (a private VPN/mesh network,
e.g. Tailscale/Headscale, reached at `<PC_VPN_IP>`), Windows 11, Intel BT (must be switched on), sees
lamp at −61 dBm, address `<LAMP_BLE_MAC>`. Tool:
`%USERPROFILE%\sunlight\melk.py` in venv with bleak — `venv\Scripts\python melk.py rgb 255 30 0`.
The PC also reaches the IR board (http://<IR_BOARD_IP>). BLE works over plain SSH once the radio is on.

Mac sender: scratchpad `melk` tool (CoreBluetooth), e.g. dim red = init + on + `7e070503ff000010ef` + `7e04010aff000000ef`.
