/*
 * ir_lab.ino - OTA-only safe firmware for ESP8266 IR lab board.
 *
 * SAFETY FIRST: this board has no serial/USB-TTL access. If firmware fails
 * to bring up Wi-Fi + a web update page, the board is bricked until the
 * user buys a USB-TTL adapter. Design rules followed:
 *
 *  - The soft-AP ("SUNLIGHT_IR", open, 192.168.4.1) is started
 *    unconditionally, before anything that could fail or block.
 *  - The web server + /update (ESP8266HTTPUpdateServer) is started before
 *    any IR peripheral init.
 *  - A boot counter stored in RTC user memory trips "safe mode" after 3
 *    consecutive boots that didn't reach 30s of uptime, skipping IR init
 *    entirely (Wi-Fi + web + /update still work in safe mode).
 *  - Nothing in setup() blocks: Wi-Fi STA connect is non-blocking, no
 *    delay() longer than 10ms anywhere.
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPUpdateServer.h>
#include <ESP8266mDNS.h>
#include <LittleFS.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>

// Bump on every build that gets flashed; shown on / and at /version.
static const char *FW_VERSION = "v3 (no-sleep wifi)";

// ---------- Pin map (Tasmota template for this board) ----------
static const uint8_t IR_SEND_PIN = 4;
static const uint8_t IR_RECV_PIN = 14;

// ---------- AP config ----------
static const char *AP_SSID = "SUNLIGHT_IR";
static const char *WIFI_FILE = "/wifi.txt";
static const char *MDNS_NAME = "sunlight-ir";

// ---------- RTC boot-counter safe mode ----------
struct RtcBootData {
  uint32_t magic;
  uint32_t bootCount;
};
static const uint32_t RTC_MAGIC = 0x53554E4C; // "SUNL"
static const uint8_t RTC_SLOT = 64;           // offset in 4-byte blocks, well clear of WiFi RTC use
static const uint32_t SAFE_MODE_THRESHOLD = 3;
bool safeMode = false;
bool bootCounterCleared = false;

// ---------- Web server ----------
ESP8266WebServer server(80);
ESP8266HTTPUpdateServer httpUpdater;

// ---------- Restart scheduling (non-blocking) ----------
bool restartPending = false;
unsigned long restartAtMs = 0;

// ---------- IR ----------
IRrecv *irrecv = nullptr;
IRsend *irsend = nullptr;
static const uint16_t kCaptureBufSize = 300; // NEC needs ~70; keeps RAM free
static const uint8_t kIrTimeoutMs = 50;

// ---------- Capture ring buffer ----------
static const uint8_t CAP_COUNT = 24;
static const uint16_t CAP_LINE_LEN = 160; // decoded fields + short raw prefix
struct Capture {
  char text[CAP_LINE_LEN];
  bool valid;
};
Capture captures[CAP_COUNT];
uint8_t capHead = 0; // next slot to write

void addCapture(const char *text) {
  strncpy(captures[capHead].text, text, CAP_LINE_LEN - 1);
  captures[capHead].text[CAP_LINE_LEN - 1] = '\0';
  captures[capHead].valid = true;
  capHead = (capHead + 1) % CAP_COUNT;
}

// ---------- RTC helpers ----------
void loadBootCounter() {
  RtcBootData d;
  if (!ESP.rtcUserMemoryRead(RTC_SLOT, (uint32_t *)&d, sizeof(d))) {
    d.magic = 0;
    d.bootCount = 0;
  }
  if (d.magic != RTC_MAGIC) {
    d.magic = RTC_MAGIC;
    d.bootCount = 0;
  }
  d.bootCount++;
  if (d.bootCount >= SAFE_MODE_THRESHOLD) {
    safeMode = true;
  }
  ESP.rtcUserMemoryWrite(RTC_SLOT, (uint32_t *)&d, sizeof(d));
}

void clearBootCounter() {
  RtcBootData d;
  d.magic = RTC_MAGIC;
  d.bootCount = 0;
  ESP.rtcUserMemoryWrite(RTC_SLOT, (uint32_t *)&d, sizeof(d));
  bootCounterCleared = true;
}

void clearBootCounterIfStable() {
  if (bootCounterCleared) return;
  if (millis() < 30000) return;
  clearBootCounter();
}

// ---------- Wi-Fi STA (non-blocking) ----------
bool staAttempted = false;
void trySta() {
  LittleFSConfig cfg;
  cfg.setAutoFormat(false); // never erase flash at boot
  LittleFS.setConfig(cfg);
  if (!LittleFS.begin()) {
    // Do not force-format here; safest to just skip STA and stay AP-only.
    return;
  }
  if (!LittleFS.exists(WIFI_FILE)) return;
  File f = LittleFS.open(WIFI_FILE, "r");
  if (!f) return;
  String ssid = f.readStringUntil('\n');
  String pass = f.readStringUntil('\n');
  f.close();
  ssid.trim();
  pass.trim();
  if (ssid.length() == 0) return;
  WiFi.begin(ssid.c_str(), pass.c_str()); // non-blocking
  staAttempted = true;
}

// ---------- HTML helpers ----------
void sendHeader(String &out, const char *title) {
  out.reserve(out.length() + 256);
  out += "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>";
  out += "<title>";
  out += title;
  out += "</title></head><body style='font-family:sans-serif'>";
}

// ---------- Route handlers ----------
void handleRoot() {
  // Stream in small chunks so no large heap buffer is ever needed.
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "text/html", "");
  char buf[200];
  server.sendContent(F("<!DOCTYPE html><html><head><meta http-equiv='refresh' content='5'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Sunlight IR Lab</title></head><body style='font-family:sans-serif'><h2>Sunlight IR Lab</h2>"));
  server.sendContent("<p><b>Firmware: ");
  server.sendContent(FW_VERSION);
  server.sendContent("</b></p>");
  if (safeMode) server.sendContent(F("<p style='color:red'><b>SAFE MODE (repeated reboots detected, IR disabled)</b></p>"));
  snprintf(buf, sizeof(buf), "<p>Uptime: %lus<br>Free heap: %u bytes<br>AP IP: %s<br>STA status: %s",
           millis() / 1000, ESP.getFreeHeap(), WiFi.softAPIP().toString().c_str(),
           WiFi.status() == WL_CONNECTED ? "connected" : "not connected");
  server.sendContent(buf);
  if (WiFi.status() == WL_CONNECTED) {
    snprintf(buf, sizeof(buf), " (%s)", WiFi.localIP().toString().c_str());
    server.sendContent(buf);
  }
  server.sendContent(F("</p><p><a href='/update'>Firmware update</a> | <a href='/wifi'>Wi-Fi setup</a> | "
    "<a href='/send'>Send IR</a> | <a href='/json'>JSON</a> | <a href='/restart'>Restart</a></p>"
    "<h3>Recent captures (newest first)</h3><table border='1' cellpadding='4' style='border-collapse:collapse;font-size:12px'>"));
  for (uint8_t i = 0; i < CAP_COUNT; i++) {
    int idx = (capHead - 1 - i + CAP_COUNT * 2) % CAP_COUNT;
    if (!captures[idx].valid) continue;
    server.sendContent("<tr><td>");
    server.sendContent(captures[idx].text);
    server.sendContent("</td></tr>");
  }
  server.sendContent(F("</table></body></html>"));
  server.sendContent("");
}

void handleWifiGet() {
  String page;
  page.reserve(800);
  page = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>";
  page += "<title>Wi-Fi setup</title></head><body style='font-family:sans-serif'>";
  page += "<h3>Home Wi-Fi setup</h3>";
  page += "<form method='POST' action='/wifi'>";
  page += "SSID: <input name='ssid'><br>Password: <input name='pass' type='password'><br>";
  page += "<input type='submit' value='Save & restart'></form>";
  page += "<p><a href='/'>Back</a></p></body></html>";
  server.send(200, "text/html", page);
}

void handleWifiPost() {
  String ssid = server.arg("ssid");
  String pass = server.arg("pass");
  bool ok = false;
  // User-initiated: format only here, while OTA is already reachable.
  bool mounted = LittleFS.begin() || (LittleFS.format() && LittleFS.begin());
  if (mounted) {
    File f = LittleFS.open(WIFI_FILE, "w");
    if (f) {
      f.print(ssid);
      f.print("\n");
      f.print(pass);
      f.print("\n");
      f.close();
      ok = true;
    }
  }
  String page = "<html><body>";
  page += ok ? "Saved. Restarting..." : "Failed to save (filesystem error).";
  page += "</body></html>";
  server.send(200, "text/html", page);
  if (ok) {
    // This is a voluntary restart, not a crash: clear the boot counter now
    // so a few quick Wi-Fi reconfigurations never trip safe mode.
    clearBootCounter();
    // Restart happens in loop() after a short grace period, set via flag.
    restartAtMs = millis() + 1000;
    restartPending = true;
  }
}

void handleSendGet() {
  String page;
  page.reserve(800);
  page = "<html><body style='font-family:sans-serif'><h3>Send IR</h3>";
  page += "<form method='GET' action='/send'>";
  page += "Protocol (e.g. NEC): <input name='proto'><br>";
  page += "Value (hex, e.g. 0xF7C03F): <input name='value'><br>";
  page += "Bits: <input name='bits' value='32'><br>";
  page += "<input type='submit' value='Send'></form>";
  page += "<p><a href='/'>Back</a></p></body></html>";
  server.send(200, "text/html", page);
}

void handleSend() {
  if (!server.hasArg("proto") || !server.hasArg("value")) {
    handleSendGet();
    return;
  }
  if (safeMode || irsend == nullptr) {
    server.send(200, "text/plain", "IR disabled (safe mode)");
    return;
  }
  String protoStr = server.arg("proto");
  String valueStr = server.arg("value");
  uint16_t bits = server.hasArg("bits") ? (uint16_t)server.arg("bits").toInt() : 32;
  decode_type_t type = strToDecodeType(protoStr.c_str());
  if (type == decode_type_t::UNKNOWN) {
    server.send(400, "text/plain", "Unknown protocol: " + protoStr);
    return;
  }
  uint64_t value = strtoull(valueStr.c_str(), nullptr, 0);
  irsend->send(type, value, bits);
  char buf[128];
  snprintf(buf, sizeof(buf), "Sent proto=%s value=0x%llX bits=%u",
           typeToString(type).c_str(), (unsigned long long)value, bits);
  server.send(200, "text/plain", buf);
}

void handleJson() {
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "application/json", "[");
  bool first = true;
  for (uint8_t i = 0; i < CAP_COUNT; i++) {
    int idx = (capHead - 1 - i + CAP_COUNT * 2) % CAP_COUNT;
    if (!captures[idx].valid) continue;
    server.sendContent(first ? "\"" : ",\"");
    first = false;
    server.sendContent(captures[idx].text); // capture text never contains quotes/backslashes
    server.sendContent("\"");
  }
  server.sendContent("]");
  server.sendContent("");
}

void handleRestart() {
  server.send(200, "text/plain", "Restarting...");
  // Voluntary restart: don't let it count towards the crash-loop safe-mode trigger.
  clearBootCounter();
  restartAtMs = millis() + 500;
  restartPending = true;
}

// ---------- IR decode formatting ----------
decode_results results;
void handleIrDecode() {
  if (irrecv == nullptr) return;
  if (!irrecv->decode(&results)) return;

  char line[CAP_LINE_LEN];
  int off = 0;
  off += snprintf(line + off, CAP_LINE_LEN - off, "%s addr=0x%llX cmd=0x%llX value=0x%llX bits=%u raw=",
                   typeToString(results.decode_type).c_str(),
                   (unsigned long long)results.address,
                   (unsigned long long)results.command,
                   (unsigned long long)results.value,
                   results.bits);
  // Append a truncated raw timing dump (first ~40 entries) without huge memory use.
  uint16_t n = results.rawlen > 9 ? 9 : results.rawlen;
  for (uint16_t i = 1; i < n && off < CAP_LINE_LEN - 12; i++) {
    off += snprintf(line + off, CAP_LINE_LEN - off, "%u,", results.rawbuf[i] * kRawTick);
  }
  if (results.rawlen > 9) {
    off += snprintf(line + off, CAP_LINE_LEN - off, "...(%u more)", results.rawlen - 9);
  }
  addCapture(line);
  irrecv->resume();
}

void setup() {
  Serial.begin(115200); // harmless even with nothing listening

  // 1. Boot-counter based safe mode decision (fast, non-blocking).
  loadBootCounter();

  // 2. AP always on, regardless of anything else.
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP); // mains powered: keep radio awake so requests never stall
  WiFi.softAP(AP_SSID); // open network, default IP 192.168.4.1

  // 4. Web server + OTA update endpoint, started before any IR init.
  httpUpdater.setup(&server, "/update");
  server.on("/", handleRoot);
  server.on("/wifi", HTTP_GET, handleWifiGet);
  server.on("/wifi", HTTP_POST, handleWifiPost);
  server.on("/send", HTTP_GET, handleSend);
  server.on("/json", HTTP_GET, handleJson);
  server.on("/restart", HTTP_GET, handleRestart);
  server.on("/version", HTTP_GET, []() { server.send(200, "text/plain", FW_VERSION); });
  server.begin();
  server.keepAlive(false);

  // 3. STA: best-effort, after OTA is reachable; skipped in safe mode.
  if (!safeMode) trySta();

  // Optional, best-effort mDNS.
  MDNS.begin(MDNS_NAME);
  MDNS.addService("http", "tcp", 80);

  // 5. Only now, if not in safe mode, bring up IR peripherals.
  if (!safeMode) {
    irrecv = new IRrecv(IR_RECV_PIN, kCaptureBufSize, kIrTimeoutMs, true);
    irrecv->setUnknownThreshold(12);
    irrecv->enableIRIn();
    irsend = new IRsend(IR_SEND_PIN);
    irsend->begin();
  }
}

void loop() {
  server.handleClient();
  MDNS.update();

  if (!safeMode) {
    handleIrDecode();
  }

  clearBootCounterIfStable();

  if (restartPending && (long)(millis() - restartAtMs) >= 0) {
    ESP.restart();
  }

  yield();
}
