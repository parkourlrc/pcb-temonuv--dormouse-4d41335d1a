#ifndef TEMP_SENSOR_H
#define TEMP_SENSOR_H

#include <stdbool.h>

typedef enum {
  TEMP_SENSOR_OK = 0,
  TEMP_SENSOR_ERR_I2C,   // bus transfer failed
  TEMP_SENSOR_ERR_CRC,   // checksum mismatch
} temp_sensor_status_t;

// Power up the I2C bus / sensor instance. Call once at boot.
void temp_sensor_init(void);

// Trigger a high-precision conversion and return temperature (°C) and relative
// humidity (%RH). Blocks ~10 ms for the conversion. Either output pointer may be
// NULL if that value is not needed. Returns TEMP_SENSOR_OK on success.
// Target sensor: Sensirion SHT40 — temperature + humidity from one transaction.
temp_sensor_status_t temp_sensor_read(float *celsius_out, float *rh_out);

#endif  // TEMP_SENSOR_H
