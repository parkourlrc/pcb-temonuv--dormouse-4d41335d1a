/*
 * app.c — Dormouse Zigbee sleepy temperature + humidity sensor, application logic.
 *
 * Built against Simplicity SDK 2026.6.0 (Zigbee App Framework, sl_zigbee_af_* API).
 *
 * Lifecycle:
 *   1. Boot -> sl_zigbee_af_main_init_cb inits the sensor + the measure event.
 *   2. The measure event: if not joined, run network steering and retry; once
 *      joined, read temperature + battery, write the ZCL attributes, emit a
 *      debug line, and reschedule at the current cadence (5 min, or 10 s in
 *      debug mode). The reporting engine pushes attribute changes to the
 *      coordinator; Power Manager returns the MCU to EM2 between events.
 */

#include "app.h"
#include "temp_sensor.h"
#include "debug.h"
#include "factory_reset.h"

#include "app/framework/include/af.h"
#include "network-steering.h"

#include "em_iadc.h"
#include "sl_clock_manager.h"
#include "sl_sleeptimer.h"

#define JOIN_RETRY_MS  (60u * 1000u)

// IADC clocking for the battery read (mirrors the SDK's battery-over-IADC ref).
#define IADC_CLK_SRC_FREQ  2000000u
#define IADC_CLK_ADC_FREQ  1000000u
#define IADC_RESULT_MAX    0xFFFu           // 12-bit single conversion full scale

// ---------------------------------------------------------------------------
// Periodic measurement event
// ---------------------------------------------------------------------------
static sl_zigbee_af_event_t measure_event;
static void measure_event_handler(sl_zigbee_af_event_t *event);
static void battery_init(void);

// --- Software watchdog (see WATCHDOG_GRACE_MS in app.h) ---------------------
static sl_sleeptimer_timer_handle_t watchdog_timer;

static void watchdog_expired(sl_sleeptimer_timer_handle_t *handle, void *data)
{
  (void)handle; (void)data;
  // A full measurement cycle was missed — the app hung. Reset to recover.
  NVIC_SystemReset();
}

// Re-arm the watchdog for 2× the current sample interval (+ grace). Called from
// init and at the top of every measure cycle; if it ever fires, we reset.
static void watchdog_kick(void)
{
  uint32_t ms = 2u * debug_measure_interval_ms() + WATCHDOG_GRACE_MS;
  // ms32 variant (out-param, not a return value): the watchdog timeout (minutes)
  // overflows the uint16 ms_to_tick. If the conversion is rejected, leave the
  // previously-armed timer running rather than disarming the watchdog.
  uint32_t ticks;
  if (sl_sleeptimer_ms32_to_tick(ms, &ticks) != SL_STATUS_OK) {
    return;
  }
  sl_sleeptimer_restart_timer(&watchdog_timer, ticks,
                              watchdog_expired, NULL, 0, 0);
}

static void schedule_next_measurement(void)
{
  // Cadence depends on mode: 10 s in debug, otherwise the configured interval.
  sl_zigbee_af_event_set_delay_ms(&measure_event, debug_measure_interval_ms());
}

/** Encode °C -> ZCL Temperature Measurement MeasuredValue (int16, 0.01 °C). */
static int16_t to_centidegrees(float celsius)
{
  return (int16_t)(celsius * 100.0f + (celsius >= 0 ? 0.5f : -0.5f));
}

/** Map a coin-cell voltage to the ZCL battery percentage attr (0.5 % units). */
static uint8_t battery_percent_half(uint16_t mv)
{
  if (mv >= BATTERY_FULL_MV)  return 200;   // 100 %
  if (mv <= BATTERY_EMPTY_MV) return 0;
  uint32_t pct = (uint32_t)(mv - BATTERY_EMPTY_MV) * 200u
                 / (BATTERY_FULL_MV - BATTERY_EMPTY_MV);
  return (uint8_t)pct;
}

static void measure_event_handler(sl_zigbee_af_event_t *event)
{
  (void)event;
  watchdog_kick();   // we reached the measure loop — the app is alive

  // Not commissioned yet? Try to join an open network, then retry later.
  if (sl_zigbee_af_network_state() != SL_ZIGBEE_JOINED_NETWORK) {
    sl_status_t st_steer = sl_zigbee_af_network_steering_start();
    (void)st_steer; // Steering might already be in progress (SL_STATUS_INVALID_STATE)
    sl_zigbee_af_event_set_delay_ms(&measure_event, JOIN_RETRY_MS);
    return;
  }

  float celsius = 0.0f, humidity = 0.0f;
  temp_sensor_status_t st = temp_sensor_read(&celsius, &humidity);
  int16_t  centi    = to_centidegrees(celsius);
  uint16_t rh_centi = (uint16_t)(humidity * 100.0f + 0.5f);   // ZCL 0.01 %RH units
  if (st == TEMP_SENSOR_OK) {
    sl_zigbee_af_write_server_attribute(
        SENSOR_ENDPOINT, ZCL_TEMP_MEASUREMENT_CLUSTER,
        ZCL_TEMP_MEASURED_VALUE_ATTR, (uint8_t *)&centi, ZCL_INT16S_ATTRIBUTE_TYPE);
    sl_zigbee_af_write_server_attribute(
        SENSOR_ENDPOINT, ZCL_HUMIDITY_MEASUREMENT_CLUSTER,
        ZCL_HUMIDITY_MEASURED_VALUE_ATTR, (uint8_t *)&rh_centi, ZCL_INT16U_ATTRIBUTE_TYPE);
  }

  uint16_t mv = app_read_battery_mv();
  uint8_t batt_100mv = (uint8_t)((mv + 50) / 100);       // round to 0.1 V
  uint8_t batt_half  = battery_percent_half(mv);
  sl_zigbee_af_write_server_attribute(
      SENSOR_ENDPOINT, ZCL_POWER_CONFIG_CLUSTER,
      ZCL_BATTERY_VOLTAGE_ATTR, &batt_100mv, ZCL_INT8U_ATTRIBUTE_TYPE);
  sl_zigbee_af_write_server_attribute(
      SENSOR_ENDPOINT, ZCL_POWER_CONFIG_CLUSTER,
      ZCL_BATTERY_PERCENT_ATTR, &batt_half, ZCL_INT8U_ATTRIBUTE_TYPE);

  // RTT log every cycle; mirrored to HA's debug cluster only in debug mode.
  int whole = centi / 100;
  int frac = (centi < 0 ? -centi : centi) % 100;
  debug_log((uint8_t)st, "T=%s%d.%02dC RH=%u%% bat=%umV st=%u",
            (centi < 0 && whole == 0) ? "-" : "", whole, frac,
            (unsigned)(rh_centi / 100), mv, (unsigned)st);

  schedule_next_measurement();
}

// ---------------------------------------------------------------------------
// App Framework callbacks
// ---------------------------------------------------------------------------
void sl_zigbee_af_main_init_cb(void)
{
  // Count this boot for the power-cycle factory-reset, before anything else so
  // the streak is captured even if later init misbehaves.
  factory_reset_boot_check();

  temp_sensor_init();
  battery_init();
  debug_init();
  watchdog_kick();                                 // arm the software watchdog
  sl_zigbee_af_event_init(&measure_event, measure_event_handler);
  sl_zigbee_af_event_set_active(&measure_event);   // kick off join + measurement
}

/** Stack came up / down (join, rejoin, parent change). */
void sl_zigbee_af_stack_status_cb(sl_status_t status)
{
  if (status == SL_STATUS_NETWORK_UP) {
    // Re-assert the coin-cell-safe TX power on every join/rejoin. Network steering
    // sets it for a fresh join, but a warm reboot of an already-joined device does
    // NOT steer — without this it would come up at the radio's default power and a
    // full-power TX pulse could brown out the CR2032. (sl_zigbee_set_radio_power is
    // the current SDK name for emberSetRadioPower — reconcile if the API shifts.)
    (void)sl_zigbee_set_radio_power(MGM_TX_POWER_DBM);
    sl_zigbee_af_event_set_active(&measure_event);  // start measuring promptly
  }
}

/** Commissioning finished — back off and retry on failure. */
void sl_zigbee_af_network_steering_complete_cb(sl_status_t status,
                                               uint8_t totalBeacons,
                                               uint8_t joinAttempts,
                                               uint8_t finalState)
{
  (void)totalBeacons; (void)joinAttempts; (void)finalState;
  if (status != SL_STATUS_OK) {
    sl_zigbee_af_event_set_delay_ms(&measure_event, JOIN_RETRY_MS);
  }
}

/*
 * Fires whenever a ZCL attribute is written locally — including by the
 * coordinator over the air. Used to react to Home Assistant toggling debug mode.
 * Note: this is a sleepy end device, so a write from HA is queued at the parent
 * and delivered on the next poll — enabling debug can lag one poll interval;
 * once enabled the device stays awake, so disabling is prompt.
 */
void sl_zigbee_af_post_attribute_change_cb(uint8_t endpoint,
                                           sl_zigbee_af_cluster_id_t clusterId,
                                           sl_zigbee_af_attribute_id_t attributeId,
                                           uint8_t mask,
                                           uint16_t manufacturerCode,
                                           uint8_t type,
                                           uint8_t size,
                                           uint8_t *value)
{
  (void)mask; (void)manufacturerCode; (void)type; (void)size;
  if (endpoint != SENSOR_ENDPOINT || clusterId != ZCL_DEBUG_CLUSTER) {
    return;
  }

  switch (attributeId) {
    case ZCL_DEBUG_ENABLED_ATTR:
      debug_set_enabled(value[0] != 0);
      sl_zigbee_af_event_set_active(&measure_event);   // apply new cadence now
      break;
    case ZCL_DEBUG_INTERVAL_ATTR:
      debug_set_normal_interval_s((uint16_t)(value[0] | (value[1] << 8)));
      sl_zigbee_af_event_set_active(&measure_event);
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Battery measurement (internal IADC against AVDD)
//
// The CR2032 connects straight to VDD, so measuring the supply rail *is* the
// battery voltage — no external divider needed. The IADC's iadcPosInputAvdd
// input measures AVDD/4 internally against the default 1.21 V reference.
// ---------------------------------------------------------------------------
static uint32_t iadc_vref_mv;

static void battery_init(void)
{
  IADC_Init_t        init        = IADC_INIT_DEFAULT;
  IADC_AllConfigs_t  all_configs = IADC_ALLCONFIGS_DEFAULT;
  IADC_InitSingle_t  init_single = IADC_INITSINGLE_DEFAULT;
  IADC_SingleInput_t input       = IADC_SINGLEINPUT_DEFAULT;

  sl_clock_manager_enable_bus_clock(SL_BUS_CLOCK_IADC0);

  init.srcClkPrescale = IADC_calcSrcClkPrescale(IADC0, IADC_CLK_SRC_FREQ, 0);
  init.warmup = iadcWarmupNormal;                       // power down between reads
  all_configs.configs[0].osrHighSpeed = iadcCfgOsrHighSpeed2x;  // -> 12-bit result
  all_configs.configs[0].adcClkPrescale =
      IADC_calcAdcClkPrescale(IADC0, IADC_CLK_ADC_FREQ, 0,
                              iadcCfgModeNormal, init.srcClkPrescale);

  input.posInput = iadcPosInputAvdd;                    // internally AVDD/4
  input.negInput = iadcNegInputGnd;
  iadc_vref_mv   = all_configs.configs[0].vRef;         // default internal 1.21 V

  IADC_init(IADC0, &init, &all_configs);
  IADC_initSingle(IADC0, &init_single, &input);
}

uint16_t app_read_battery_mv(void)
{
  IADC_command(IADC0, iadcCmdStartSingle);
  // A single 12-bit conversion takes only a few µs, so this normally spins a
  // handful of times. The guard keeps an IADC hardware fault (SINGLEDONE never
  // asserting) from hanging the whole device on a battery-powered node.
  uint32_t guard = 100000u;
  while (!(IADC_getInt(IADC0) & IADC_IF_SINGLEDONE)) {
    if (--guard == 0u) {
      return 0u;   // conversion never completed — report 0 mV rather than block
    }
  }
  IADC_clearInt(IADC0, IADC_IF_SINGLEDONE);
  IADC_Result_t sample = IADC_pullSingleFifoResult(IADC0);

  // AVDD was divided by 4 before the ADC, so multiply back up.  Rounded.
  return (uint16_t)(((4u * sample.data * iadc_vref_mv) + (IADC_RESULT_MAX / 2u))
                    / IADC_RESULT_MAX);
}
