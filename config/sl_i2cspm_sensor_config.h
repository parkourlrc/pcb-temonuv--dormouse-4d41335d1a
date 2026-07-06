/***************************************************************************//**
 * @brief I2CSPM "sensor" instance configuration for the MGM210L board.
 *
 * There is no Silicon Labs radio board file for a bespoke MGM210L design, so
 * this pin map is supplied by the project instead of by a board component.
 * Pins match the schematic (hardware/): SCL = PC00 (module pin 7), SDA = PC01
 * (module pin 8) — adjacent module pads, no series resistor, and they leave
 * PA01-04 for SWD and PD00/PD01 for an optional LFXO. Change here + in the
 * schematic together if your PCB routes differently.
 ******************************************************************************/
#ifndef SL_I2CSPM_SENSOR_CONFIG_H
#define SL_I2CSPM_SENSOR_CONFIG_H

// <<< Use Configuration Wizard in Context Menu >>>

// <h>I2CSPM settings

// <o SL_I2CSPM_SENSOR_REFERENCE_CLOCK> Reference clock frequency (Hz, 0 = current)
#define SL_I2CSPM_SENSOR_REFERENCE_CLOCK 0

// <o SL_I2CSPM_SENSOR_SPEED_MODE> Speed mode
// <0=> Standard mode (100kbit/s)
// <1=> Fast mode (400kbit/s)
// <2=> Fast mode plus (1Mbit/s)
#define SL_I2CSPM_SENSOR_SPEED_MODE      1
// </h>

// <<< sl:start pin_tool >>>
// <i2c signal=SCL,SDA> SL_I2CSPM_SENSOR
// $[I2C_SL_I2CSPM_SENSOR]
#define SL_I2CSPM_SENSOR_PERIPHERAL      I2C0
#define SL_I2CSPM_SENSOR_PERIPHERAL_NO   0

// I2C0 SCL — PC00 (module pin 7) -> SHT40 SCL
#define SL_I2CSPM_SENSOR_SCL_PORT        SL_GPIO_PORT_C
#define SL_I2CSPM_SENSOR_SCL_PIN         0

// I2C0 SDA — PC01 (module pin 8) -> SHT40 SDA
#define SL_I2CSPM_SENSOR_SDA_PORT        SL_GPIO_PORT_C
#define SL_I2CSPM_SENSOR_SDA_PIN         1
// [I2C_SL_I2CSPM_SENSOR]$
// <<< sl:end pin_tool >>>

#endif // SL_I2CSPM_SENSOR_CONFIG_H
