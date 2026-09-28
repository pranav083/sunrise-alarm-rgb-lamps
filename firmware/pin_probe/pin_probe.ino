/*
 * pin_probe.ino
 *
 * Utility sketch to help discover which GPIO an IR receiver module is
 * physically wired to on an unfamiliar ESP32E-N4 IR board.
 *
 * It configures a set of "candidate" GPIOs as INPUT and continuously polls
 * digitalRead() on each of them. IR receiver modules idle HIGH and pulse
 * LOW when they see a demodulated IR carrier, so pressing a remote button
 * near the board should cause rapid toggling on the correct pin. Any pin
 * that changes state is reported over Serial.
 *
 * Usage:
 *   1. Flash this sketch.
 *   2. Open the serial monitor at 115200 baud.
 *   3. Point a remote at the board and hold a button.
 *   4. Watch for "GPIO xx toggled" messages - that is likely the IR pin.
 *
 * NOTE: This is a discovery aid only, not a substitute for checking the
 * board schematic. Some candidate pins are strapping/flash pins and are
 * skipped below because reconfiguring them as plain INPUT during boot can
 * be unsafe or unreliable (GPIO 0, 1, 3, 6-11, 12 is borderline but
 * commonly reserved for flash voltage select on some modules, so it is
 * included cautiously; GPIO 20, 24, 28-31, 37, 38, 40+ do not exist on
 * classic ESP32; ADC2 pins 0,2,4,12-15,25-27 cannot be used while WiFi is
 * active but are fine for plain digitalRead when WiFi is off).
 */

#include <Arduino.h>

// Candidate GPIOs to probe. GPIO 0, 1 (UART0 TX), 3 (UART0 RX), and 6-11
// (used for the integrated SPI flash) are intentionally excluded as unsafe.
const uint8_t candidatePins[] = {
  2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19,
  21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 39
};
const uint8_t numPins = sizeof(candidatePins) / sizeof(candidatePins[0]);

int lastState[sizeof(candidatePins) / sizeof(candidatePins[0])];

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println(F("========================================"));
  Serial.println(F(" Sunlight Ctrl - IR Pin Probe"));
  Serial.println(F("========================================"));
  Serial.print(F("Probing "));
  Serial.print(numPins);
  Serial.println(F(" candidate GPIOs for IR receiver activity."));
  Serial.println(F("Point a remote at the board and hold a button."));
  Serial.println(F("Pins that toggle will be reported below."));
  Serial.print(F("Candidates: "));
  for (uint8_t i = 0; i < numPins; i++) {
    Serial.print(candidatePins[i]);
    if (i < numPins - 1) Serial.print(F(", "));
  }
  Serial.println();
  Serial.println(F("========================================"));

  for (uint8_t i = 0; i < numPins; i++) {
    // GPIO 34-39 are input-only on the classic ESP32 and have no internal
    // pull resistors; INPUT mode still works for reading.
    pinMode(candidatePins[i], INPUT);
    lastState[i] = digitalRead(candidatePins[i]);
  }
}

void loop() {
  for (uint8_t i = 0; i < numPins; i++) {
    int state = digitalRead(candidatePins[i]);
    if (state != lastState[i]) {
      Serial.print(F("GPIO "));
      Serial.print(candidatePins[i]);
      Serial.print(F(" toggled: "));
      Serial.print(lastState[i]);
      Serial.print(F(" -> "));
      Serial.println(state);
      lastState[i] = state;
    }
  }
  // Tight-ish polling loop; IR pulses are short (tens of microseconds), so
  // this won't catch every edge, but repeated button presses will produce
  // enough transitions to identify the active pin.
}
