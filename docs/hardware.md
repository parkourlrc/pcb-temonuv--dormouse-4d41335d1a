# Hardware

## Datasheets

Not vendored in the repo (third-party copyright) — download from the vendor:

- **MGM210L module** — [datasheet PDF](https://www.silabs.com/documents/public/data-sheets/mgm210l-datasheet.pdf)
  · [product family](https://www.silabs.com/wireless/zigbee/efr32mg21-series-2-modules) (Silicon Labs)
- **Sensirion SHT40** — [SHT4x datasheet](https://sensirion.com/resource/datasheet/sht4x)
  · [product page](https://sensirion.com/products/catalog/SHT40)

## Module
**Silicon Labs MGM210LA22JNF2** — Mighty Gecko wireless module, 18-pin.
- SoC: **EFR32MG21A** (ARM Cortex-M33 @ up to 80 MHz), 2.4 GHz radio.
- Protocols: Zigbee 3.0 / Thread / Bluetooth LE (this project uses **Zigbee**).
- **Integrated PCB antenna** — ready-to-use module, *no external RF parts*. Place
  it at the **edge of the board** and keep the antenna area clear of copper/ground
  (datasheet §7). Mount horizontally for access to all pins.
- Pinout used here (datasheet Table 6.1): **VDD** = pin 13, **GND** = pins 6 & 14,
  **RESETn** = pin 11 (internal pull-up, no external R needed). Leave **DEC**
  (pin 5, internal decouple) and **DNC** (pin 12) unconnected.
- I²C to the SHT40 on **PC00 (pin 7) = SCL** and **PC01 (pin 8) = SDA** — adjacent
  pads for short routing, no series resistor (unlike PC02–PC05), and this keeps
  PA01–PA04 for SWD and PD00/PD01 free for an optional 32.768 kHz LFXO crystal.

> The MG21 has only an on-die temperature sensor (measures silicon temp, not
> ambient). An **external I²C sensor is required** for real room temperature —
> and an RH-capable part (SHT4x / Si7021) also gives **relative humidity**, which
> the firmware reads from the same transaction and exposes as a second HA entity.

## Bill of materials
| Part | Purpose | Notes |
|------|---------|-------|
| MGM210LA22JNF2 | MCU + radio | LGA module, needs a carrier/PCB |
| Sensirion **SHT40** | Temp + humidity | I²C addr 0x44 (SHT40-AD1B); ±0.2 °C, ±1.8 %RH; ~0.4 µA idle |
| CR2032 holder | Power | ~220 mAh, high internal resistance |
| 4.7 kΩ ×2 | I²C pull-ups | SDA + SCL to VDD |
| 10 µF + 100 nF | Module decoupling | near module VDD (pin 13); bulk cap absorbs TX pulses |
| 100 nF | SHT40 decoupling | across SHT40 VDD–VSS, close to the sensor (per datasheet) |
| — | Antenna | none — integrated in the module |

## Schematic

### Power rail (CR2032 → VDD)
```
   CR2032
   +3 V nominal
     (+) ●───┬────────┬────────┬─────────────────►  VDD  (module, SHT40, pull-ups)
             │        │        │
            ═╧═10µF   ═╧═100nF  (bulk + HF decoupling, placed close to module VDD —
             │        │         the bulk cap sources the radio TX current pulse the
     (–) ●───┴────────┴──┐      coin cell's high internal R cannot)
                         GND ───────────────────►  GND
```
No battery divider: the cell sits directly on VDD and firmware reads VDD through
the IADC's internal AVDD/4 input (see *Battery sensing* below).

### I²C sensor bus — Sensirion SHT40 (addr 0x44)
```
                     VDD
                      │
                ┌─────┴─────┐
              4.7kΩ       4.7kΩ         external pull-ups — the module GPIOs
                │(SDA)      │(SCL)       cannot drive the open-drain bus alone
   MGM210L      │           │             SHT40  (Sensirion)
   ┌─────────┐  │           │           ┌────────────┐
   │  PC01 ●─┼──┴───────────┼───────────┤ SDA ●      │
   │  PC00 ●─┼──────────────┴───────────┤ SCL ●      │
   │  VDD  ●─┼──────────────────────────┤ VDD ●─┐    │
   │         │                          │       ═╧═ 100 nF  (decouple AT the SHT40)
   │  GND  ●─┼──────────────────────────┤ VSS ●─┘    │
   └─────────┘                          └────────────┘
   PC00 (pin 7) = I2C0_SCL, PC01 (pin 8) = I2C0_SDA  (matches
   config/sl_i2cspm_sensor_config.h; adjacent module pads = short routing)
   The SHT40 returns temperature AND humidity in one read (cmd 0xFD, ~8 ms).
```

### SWD / debug
```
   MGM210L               J-Link / debug probe
   ┌───────────────┐
   │ PA01/SWCLK ●──┼── SWCLK
   │ PA02/SWDIO ●──┼── SWDIO
   │ RESETn(11) ●──┼── RESET
   │ VDD / GND  ●──┼── VDD / GND
   └───────────────┘  (SWD carries both flashing and SEGGER RTT logs —
                       no separate SWO pin needed for `commander rtt`)
   RF: none — the module has an integrated antenna (place module at board edge,
   keep the antenna area clear of copper/ground).
```

### Battery sensing (no external parts)
The firmware measures the supply rail with the on-chip **IADC**: input
`iadcPosInputAvdd` samples **AVDD ÷ 4** against the internal **1.21 V** reference,
and `app_read_battery_mv()` scales it back to millivolts. That value feeds the ZCL
Power Configuration battery voltage/percentage attributes. Because the CR2032 is
wired straight to VDD, no divider, extra pin, or GPIO is required.

## Power design for CR2032
A coin cell has ~10–40 Ω internal resistance, so a full-power radio TX pulse
sags the rail and can brown-out the MCU. To stay reliable for years:
- Cap TX power at **0–8 dBm** (see `SL_..._RADIO_TX_POWER` in the `.slcp`), not
  the module's +20 dBm max.
- Keep the **10 µF bulk + 100 nF** decoupling close to VDD to source the pulse.
- Sleep in **EM2** between the 5-min reads (Power Manager handles this); the
  sensor's own sleep current (~80 nA) lets it stay powered.
- Budget: ~1–3 µA average sleep + a few ms of radio per 5 min ⇒ multi-year life,
  dominated by the CR2032's self-discharge, not the firmware.

## Debug / flash header
SWD only: **SWCLK, SWDIO, RESET, GND** to a J-Link. Add the module's VCOM/RTT
pins if you want live `commander rtt` logs. Pull the `segger_rtt` / `iostream_rtt`
components from the `.slcp` for production builds to shave idle current.
