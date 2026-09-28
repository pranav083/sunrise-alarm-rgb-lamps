/*
 * ir_capture.ino
 *
 * Captures IR remote codes on an ESP32 using IRremoteESP8266, decodes known
 * protocols, and always prints the raw timing array (via resultToSourceCode)
 * so that even unrecognized/unknown protocols can be replayed later with
 * IRsend.
 *
 * Hardware: ESP32E-N4 dev board + IR receiver/transmitter modules.
 *
 * Library required: IRremoteESP8266 (crankyoldgit)
 *   arduino-cli lib install "IRremoteESP8266"
 */

#include <Arduino.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include <IRac.h>

// ---------------------------------------------------------------------------
// Pin configuration
// ---------------------------------------------------------------------------
// IMPORTANT: These pin numbers are DEFAULTS ONLY and MUST be verified against
// the actual wiring of the ESP32E-N4 IR board being used. Check the board's
// schematic/silkscreen before trusting these values; some ESP32-E N4 boards
// route the onboard IR receiver/emitter to different GPIOs, and some of the
// candidate pins may be strapping pins or otherwise unsafe on your variant.
#define IR_RECV_PIN 14  // VERIFY: IR receiver (demodulator) output pin on ESP32E-N4 IR board
#define IR_SEND_PIN 4   // VERIFY: IR LED transmitter pin on ESP32E-N4 IR board

// ---------------------------------------------------------------------------
// IRrecv configuration
// ---------------------------------------------------------------------------
const uint16_t kCaptureBufferSize = 1024;  // 1024-entry raw buffer
const uint8_t kTimeout = 50;               // 50ms timeout between IR pulses -> end of message

IRrecv irrecv(IR_RECV_PIN, kCaptureBufferSize, kTimeout, true);
IRsend irsend(IR_SEND_PIN);
decode_results results;

void printStartupBanner() {
  Serial.println();
  Serial.println(F("========================================"));
  Serial.println(F(" Sunlight Ctrl - IR Capture"));
  Serial.println(F("========================================"));
  Serial.print(F("IR_RECV_PIN : "));
  Serial.println(IR_RECV_PIN);
  Serial.print(F("IR_SEND_PIN : "));
  Serial.println(IR_SEND_PIN);
  Serial.print(F("Buffer size : "));
  Serial.println(kCaptureBufferSize);
  Serial.print(F("Timeout(ms) : "));
  Serial.println(kTimeout);
  Serial.println(F("NOTE: Verify IR_RECV_PIN/IR_SEND_PIN against the actual"));
  Serial.println(F("ESP32E-N4 IR board wiring before relying on these values."));
  Serial.println(F("Waiting for IR signals..."));
  Serial.println(F("========================================"));
}

void setup() {
  Serial.begin(115200);
  delay(500);

  irsend.begin();
  irrecv.setUnknownThreshold(12);
  irrecv.enableIRIn();

  printStartupBanner();
}

void loop() {
  if (irrecv.decode(&results)) {
    Serial.println(F("----------------------------------------"));

    // Protocol name
    Serial.print(F("Protocol : "));
    Serial.println(typeToString(results.decode_type, results.repeat));

    // Address / Command (not all protocols populate these)
    Serial.print(F("Address  : 0x"));
    Serial.println(results.address, HEX);
    Serial.print(F("Command  : 0x"));
    Serial.println(results.command, HEX);

    // Full value
    Serial.print(F("Value    : 0x"));
    Serial.println(uint64ToString(results.value, 16));

    // Bit length
    Serial.print(F("Bits     : "));
    Serial.println(results.bits);

    // Raw source code string, usable to replay via IRsend even for
    // UNKNOWN protocols.
    Serial.print(F("SourceCode: "));
    Serial.println(resultToSourceCode(&results));

    // Also dump the raw timing array explicitly for clarity/logging.
    Serial.print(F("RawData(us), count="));
    Serial.println(results.rawlen - 1);
    Serial.print(F("{"));
    for (uint16_t i = 1; i < results.rawlen; i++) {
      uint32_t usec = results.rawbuf[i] * kRawTick;
      Serial.print(usec);
      if (i < results.rawlen - 1) Serial.print(F(", "));
    }
    Serial.println(F("}"));

    Serial.println(F("----------------------------------------"));

    irrecv.resume();  // Ready for the next signal
  }
}
