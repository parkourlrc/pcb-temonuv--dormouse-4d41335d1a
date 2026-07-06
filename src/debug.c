/*
 * debug.c — runtime debug mode for the Dormouse Zigbee sensor.
 *
 * Two things happen when debug mode is on:
 *   1. The measurement cadence drops from 5 min to 10 s (see app.c, which asks
 *      debug_measure_interval_ms() when rescheduling).
 *   2. Each measurement's log line is published to a manufacturer-specific ZCL
 *      cluster so it shows up as a text sensor in Home Assistant.
 *
 * The authoritative, high-rate developer log is always RTT over SWD
 * (`commander rtt`). The ZCL debug_text attribute is a best-effort mirror of the
 * last line — Zigbee cannot stream a console, and this device is sleepy.
 *
 * SDK-name caveat (as in app.c): sl_zigbee_af_* names are the current Simplicity
 * SDK spelling; reconcile against ./build after the first `slc generate`.
 */

#include "debug.h"
#include "app.h"

#include "app/framework/include/af.h"
#include "sl_iostream.h"
#include "sl_iostream_handles.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static bool     s_enabled = false;
static uint16_t s_normal_interval_s = MEASURE_INTERVAL_MS / 1000u;

void debug_init(void)
{
  s_enabled = false;
}

bool debug_is_enabled(void)
{
  return s_enabled;
}

uint32_t debug_measure_interval_ms(void)
{
  return s_enabled ? DEBUG_MEASURE_INTERVAL_MS
                   : (uint32_t)s_normal_interval_s * 1000u;
}

void debug_set_normal_interval_s(uint16_t seconds)
{
  // Cap interval to 12 hours (43200s) to prevent sleeptimer ms32_to_tick overflow
  if (seconds > 43200) {
    seconds = 43200;
  }
  s_normal_interval_s = (seconds == 0) ? 1 : seconds;
}

void debug_set_enabled(bool enabled)
{
  s_enabled = enabled;
  // Keep the radio awake while debugging so downlinks (incl. "disable") arrive
  // promptly; release it — back to sleepy EM2 polling — when we leave debug.
  if (enabled) {
    sl_zigbee_af_add_to_current_app_tasks(SL_ZIGBEE_AF_STAY_AWAKE);
  } else {
    sl_zigbee_af_remove_from_current_app_tasks(SL_ZIGBEE_AF_STAY_AWAKE);
  }
}

void debug_log(uint8_t status, const char *fmt, ...)
{
  char msg[40];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  size_t len = (n < 0) ? 0u
             : ((size_t)n < sizeof(msg) ? (size_t)n : sizeof(msg) - 1u);

  // 1) Always to the RTT console.
  sl_iostream_write(sl_iostream_rtt_handle, msg, len);
  sl_iostream_write(sl_iostream_rtt_handle, "\r\n", 2);

  if (!s_enabled) {
    return;
  }

  // 2) Mirror to Home Assistant via the debug cluster. A ZCL character string
  // is a leading length byte followed by the characters.
  uint8_t zstr[1 + sizeof(msg)];
  zstr[0] = len;
  memcpy(&zstr[1], msg, len);
  sl_zigbee_af_write_manufacturer_specific_server_attribute(
      SENSOR_ENDPOINT, ZCL_DEBUG_CLUSTER, ZCL_DEBUG_TEXT_ATTR,
      MGM_MANUFACTURER_CODE, zstr, ZCL_CHAR_STRING_ATTRIBUTE_TYPE);
  sl_zigbee_af_write_manufacturer_specific_server_attribute(
      SENSOR_ENDPOINT, ZCL_DEBUG_CLUSTER, ZCL_DEBUG_STATUS_ATTR,
      MGM_MANUFACTURER_CODE, &status, ZCL_INT8U_ATTRIBUTE_TYPE);
}
