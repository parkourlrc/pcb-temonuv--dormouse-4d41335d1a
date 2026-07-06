#ifndef APP_H
#define APP_H

#include <stdint.h>
#include <stdbool.h>

// --- Device data model (must match the ZAP configuration) ---------------
#define SENSOR_ENDPOINT              1
#define ZCL_TEMP_MEASUREMENT_CLUSTER 0x0402
#define ZCL_TEMP_MEASURED_VALUE_ATTR 0x0000   // int16, centi-degrees C
#define ZCL_HUMIDITY_MEASUREMENT_CLUSTER 0x0405
#define ZCL_HUMIDITY_MEASURED_VALUE_ATTR 0x0000   // uint16, 0.01 %RH units
#define ZCL_POWER_CONFIG_CLUSTER     0x0001
#define ZCL_BATTERY_VOLTAGE_ATTR     0x0020   // uint8, units of 100 mV
#define ZCL_BATTERY_PERCENT_ATTR     0x0021   // uint8, units of 0.5 %

// Manufacturer-specific "debug" cluster (defined in the ZAP, server on EP 1).
// Lets Home Assistant flip debug mode on/off and read a live debug line.
#define MGM_MANUFACTURER_CODE        0x1002   // DIY placeholder — must match ZAP + Z2M
#define ZCL_DEBUG_CLUSTER            0xFC10   // 0xFC00 is taken by the SDK's sample XML
#define ZCL_DEBUG_ENABLED_ATTR       0x0000   // bool,        RW  (HA toggle)
#define ZCL_DEBUG_TEXT_ATTR          0x0001   // char string, reportable (log line)
#define ZCL_DEBUG_STATUS_ATTR        0x0002   // uint8,       reportable (0=OK,1=I2C,2=CRC)
#define ZCL_DEBUG_INTERVAL_ATTR      0x0003   // uint16 s,    RW  (normal cadence override)

// --- Behaviour tuning ----------------------------------------------------
#define MEASURE_INTERVAL_MS          (5u * 60u * 1000u)  // normal: 5 minutes
#define DEBUG_MEASURE_INTERVAL_MS    (10u * 1000u)       // debug:  10 seconds

// Coin-cell-safe radio TX power (dBm). A CR2032 (~10-40 Ω internal R) browns out
// on a full +20 dBm PA pulse, so hold TX power here. The .slcp only sets this for
// *network steering*; we re-assert it on every network-up (app.c) so it also
// applies after a warm reboot, when an already-joined device skips steering.
#define MGM_TX_POWER_DBM             8

// Software watchdog: a sleeptimer (low-power, runs in EM2) re-armed each measure
// cycle; if a whole cycle is missed the MCU is reset. Timeout = 2× the current
// sample interval + this grace, so it adapts to normal/debug/custom cadence and,
// unlike the hardware WDOG, spans the multi-minute sleep of a sleepy device.
#define WATCHDOG_GRACE_MS            30000u

// CR2032 discharge envelope used to derive battery %. A coin cell is
// essentially flat then falls off a cliff, so this is a coarse approximation.
#define BATTERY_FULL_MV              3000
#define BATTERY_EMPTY_MV             2200

// Read battery rail via the internal IADC (measures AVDD). Implemented in app.c.
uint16_t app_read_battery_mv(void);

#endif  // APP_H
