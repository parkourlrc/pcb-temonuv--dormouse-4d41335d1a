/*
 * temp_sensor.c — Sensirion SHT40 driver over the Silicon Labs I2CSPM
 * (I2C Simple Poll Master) driver instance named "sensor".
 *
 * Wiring (see docs/hardware.md): SHT40 SDA/SCL to the module's I2C pins with
 * ~4.7 kΩ pull-ups and a 100 nF cap across the sensor's VDD/VSS. It runs from
 * VDD; idle current is ~0.4 µA, so it stays powered between the 5-minute reads.
 *
 * SHT40 command 0xFD = measure T + RH at high precision (~8 ms conversion). To
 * use a Si7021 instead, keep the I2C plumbing and swap the command / formula
 * (Si7021: cmd 0xF3, T = -46.85 + 175.72*raw/65536).
 */

#include "temp_sensor.h"
#include "sl_i2cspm_instances.h"   // generated: exposes sl_i2cspm_sensor + init
#include "sl_sleeptimer.h"         // sl_sleeptimer_delay_millisecond()
#include "em_gpio.h"               // GPIO for I2C bus-recovery clock pulses

#include <stddef.h>

// I2C pin map — mirrors config/sl_i2cspm_sensor_config.h (SCL=PC00, SDA=PC01).
// Used only by the bus-recovery path; normal transfers go through I2CSPM.
#define I2C_SCL_PORT  gpioPortC
#define I2C_SCL_PIN   0
#define I2C_SDA_PORT  gpioPortC
#define I2C_SDA_PIN   1

#define SHT4X_ADDR            0x44          // 7-bit (SHT40-AD1B default address)
#define SHT4X_CMD_MEAS_HIGH   0xFD          // measure T+RH, high repeatability
#define SHT4X_CMD_SOFT_RESET  0x94          // soft reset -> known default state
#define SHT4X_CONVERSION_MS   10
#define SHT4X_SOFT_RESET_MS   1             // t_SR, max 1 ms per datasheet

// CRC-8, polynomial 0x31, init 0xFF (Sensirion standard).
static uint8_t sht4x_crc(const uint8_t *data, int len)
{
  uint8_t crc = 0xFF;
  for (int i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

// Recover a wedged bus: if a slave was reset mid-read it can hold SDA low,
// jamming every subsequent transfer. Take the pins off the I2C peripheral, clock
// SCL up to 9 times until SDA releases, issue a STOP, then hand the pins back to
// I2CSPM. Only called on an I2C error, so the ~20 ms of delays cost nothing in
// the normal path.
static void i2c_bus_recover(void)
{
  GPIO_PinModeSet(I2C_SCL_PORT, I2C_SCL_PIN, gpioModeWiredAnd, 1);  // open-drain, released
  GPIO_PinModeSet(I2C_SDA_PORT, I2C_SDA_PIN, gpioModeWiredAnd, 1);

  for (int i = 0; i < 9 && GPIO_PinInGet(I2C_SDA_PORT, I2C_SDA_PIN) == 0; i++) {
    GPIO_PinOutClear(I2C_SCL_PORT, I2C_SCL_PIN);
    sl_sleeptimer_delay_millisecond(1);
    GPIO_PinOutSet(I2C_SCL_PORT, I2C_SCL_PIN);
    sl_sleeptimer_delay_millisecond(1);
  }

  // STOP condition: SDA low->high while SCL is high.
  GPIO_PinOutClear(I2C_SDA_PORT, I2C_SDA_PIN);
  sl_sleeptimer_delay_millisecond(1);
  GPIO_PinOutSet(I2C_SDA_PORT, I2C_SDA_PIN);
  sl_sleeptimer_delay_millisecond(1);

  // Re-init the I2CSPM instance to restore peripheral (alternate-function) pin
  // control and a clean bus state.
  sl_i2cspm_init_instances();
}

void temp_sensor_init(void)
{
  // sl_i2cspm_init_instances() (generated startup) already brought the bus up.
  // The SHT40 stays powered across MCU resets, so issue a soft reset to force a
  // known state regardless of how the previous session left it (e.g. an MCU
  // reset mid-read). A failed reset — sensor absent or bus wedged — is ignored;
  // the first temp_sensor_read() reports the I2C error anyway.
  I2C_TransferSeq_TypeDef seq;
  uint8_t cmd = SHT4X_CMD_SOFT_RESET;
  seq.addr        = SHT4X_ADDR << 1;
  seq.flags       = I2C_FLAG_WRITE;
  seq.buf[0].data = &cmd;
  seq.buf[0].len  = 1;
  (void)I2CSPM_Transfer(sl_i2cspm_sensor, &seq);
  sl_sleeptimer_delay_millisecond(SHT4X_SOFT_RESET_MS);
}

static temp_sensor_status_t sht4x_measure(float *celsius_out, float *rh_out)
{
  I2C_TransferSeq_TypeDef seq;
  uint8_t cmd = SHT4X_CMD_MEAS_HIGH;
  uint8_t rx[6];

  // 1) Send the measurement command.
  seq.addr        = SHT4X_ADDR << 1;
  seq.flags       = I2C_FLAG_WRITE;
  seq.buf[0].data = &cmd;
  seq.buf[0].len  = 1;
  if (I2CSPM_Transfer(sl_i2cspm_sensor, &seq) != i2cTransferDone) {
    return TEMP_SENSOR_ERR_I2C;
  }

  // 2) Wait for the conversion, then read 6 bytes: T[2]+CRC, RH[2]+CRC.
  sl_sleeptimer_delay_millisecond(SHT4X_CONVERSION_MS);

  seq.addr        = SHT4X_ADDR << 1;
  seq.flags       = I2C_FLAG_READ;
  seq.buf[0].data = rx;
  seq.buf[0].len  = sizeof(rx);
  if (I2CSPM_Transfer(sl_i2cspm_sensor, &seq) != i2cTransferDone) {
    return TEMP_SENSOR_ERR_I2C;
  }

  if (sht4x_crc(&rx[0], 2) != rx[2] || sht4x_crc(&rx[3], 2) != rx[5]) {
    return TEMP_SENSOR_ERR_CRC;
  }

  // 3) Convert raw ticks.  T = -45 + 175 * ticks / 65535.
  if (celsius_out != NULL) {
    uint16_t t_ticks = (uint16_t)((rx[0] << 8) | rx[1]);
    *celsius_out = -45.0f + 175.0f * ((float)t_ticks / 65535.0f);
  }

  // RH = -6 + 125 * ticks / 65535, clamped to the physical 0..100 % range.
  if (rh_out != NULL) {
    uint16_t rh_ticks = (uint16_t)((rx[3] << 8) | rx[4]);
    float rh = -6.0f + 125.0f * ((float)rh_ticks / 65535.0f);
    *rh_out = (rh < 0.0f) ? 0.0f : (rh > 100.0f ? 100.0f : rh);
  }

  return TEMP_SENSOR_OK;
}

temp_sensor_status_t temp_sensor_read(float *celsius_out, float *rh_out)
{
  temp_sensor_status_t st = sht4x_measure(celsius_out, rh_out);
  if (st == TEMP_SENSOR_ERR_I2C) {
    // A bus error can mean a slave is holding SDA low. Clock the bus free and
    // retry once; a CRC error (bus OK, data bad) is returned as-is.
    i2c_bus_recover();
    st = sht4x_measure(celsius_out, rh_out);
  }
  return st;
}
