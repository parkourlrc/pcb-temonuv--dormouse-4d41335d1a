#ifndef DEBUG_H
#define DEBUG_H

#include <stdbool.h>
#include <stdint.h>

// Initialise debug state (disabled on every boot — debug mode is never sticky).
void debug_init(void);

bool     debug_is_enabled(void);
uint32_t debug_measure_interval_ms(void);   // 10 s in debug, else the normal interval

// Toggle debug mode. Enabling also forces the end device to stay awake so it
// polls fast and can receive the "disable" command promptly — this drains the
// coin cell, so debug mode is a bench/diagnostic tool, not a normal setting.
void debug_set_enabled(bool enabled);

// Override the normal (non-debug) sample interval, in seconds (clamped >= 1).
void debug_set_normal_interval_s(uint16_t seconds);

// Emit one log line. Always written to the SWD/RTT console; when debug mode is
// enabled it is also published to the ZCL debug_text / debug_status attributes,
// which the reporting engine pushes to Home Assistant.
void debug_log(uint8_t status, const char *fmt, ...);

#endif  // DEBUG_H
