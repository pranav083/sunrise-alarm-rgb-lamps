# iPhone Shortcuts for the sunrise alarm

Four shortcuts that drive the service's web API. Replace `https://light.example.com:8444`
below with your own address (the same one the web page uses).

**Before you start:** the phone must be able to reach that address. If it is a VPN-only name
(Tailscale / Headscale), turn on the VPN app's always-on / on-demand option so the shortcuts
also work when the phone wakes up at 6 AM.

All four use the same action: **Get Contents of URL** (in the Shortcuts app: *Add Action →
search "Get Contents of URL"*). Tap **Show More** on it to set the method and body.

| Endpoint | Method | Body | Does |
|---|---|---|---|
| `/api/wake` | POST | — | I'm up: jump to full brightness and stay lit (then the usual hold / auto-off) |
| `/api/stop` | POST | — | Lights off: cancel anything running, both lamps off |
| `/api/settings` | PUT | JSON `{"wake": "HH:MM", "enabled": true}` | Set the alarm time and switch it on |
| `/api/sunrise-now` | POST | JSON `{"minutes": 20}` (optional) | Start a real sunrise right now |

---

## 1. "I'm up" when you stop your iPhone alarm (automation)

1. Shortcuts → **Automation** → **+** → **Alarm** → **Is Stopped** → choose *Any Alarm* (or your
   wake-up alarm) → **Run Immediately** → **Next**.
2. **New Blank Automation** → add **Get Contents of URL**:
   - URL: `https://light.example.com:8444/api/wake`
   - Method: **POST**
3. **Done.**

Now stopping your phone alarm turns the lamps straight to full. (If no sunrise is running it does
nothing, so it is safe to leave on for every alarm.)

## 2. "Lights off" (Siri)

1. Shortcuts → **Shortcuts** tab → **+**. Name it **Lights off**.
2. Add **Get Contents of URL**:
   - URL: `https://light.example.com:8444/api/stop`
   - Method: **POST**
3. Say *"Hey Siri, lights off"*.

## 3. "Set sunrise" (one tap to set the wake time)

1. New shortcut, name it **Set sunrise**.
2. Add **Ask for Input** → Input Type **Time**, prompt *"Wake up at?"*.
3. Add **Format Date** → Date: *Provided Input* → Date Format **Custom** → `HH:mm`.
4. Add **Get Contents of URL**:
   - URL: `https://light.example.com:8444/api/settings`
   - Method: **PUT**
   - Request Body: **JSON** → add field `wake` (Text) = *Formatted Date*;
     add field `enabled` (Boolean) = **true**.
5. Optional: add **Show Result** with *Contents of URL* to see the saved settings.

The sunrise ends at the time you enter (it starts *length* minutes earlier). Days and lamps are
whatever is set on the web page.

Apple does not let Shortcuts read your alarm time automatically, so this is the closest to
"follow my iPhone alarm": run it when you set your alarm, or attach it to an automation such as
*Sleep → Wind Down begins*.

## 4. "Sunrise now" (Siri or a bedtime / nap automation)

1. New shortcut, name it **Sunrise now**.
2. Add **Get Contents of URL**:
   - URL: `https://light.example.com:8444/api/sunrise-now`
   - Method: **POST**
   - Request Body: **JSON** → add field `minutes` (Number) = `20` (1–60; leave the body out to
     use the length set on the web page).
3. Say *"Hey Siri, sunrise now"*.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Could not connect to the server" | VPN not connected, or the name does not resolve on this network — open the web page in Safari to check |
| HTTP 409 | A sunrise or demo is already running — use *Lights off* first |
| HTTP 400 | Bad body — check field names/types (`wake` text `HH:MM`, `minutes` whole number 1–60) |
| Automation asks before running | Make sure **Run Immediately** is selected and "Notify When Run" is off |
