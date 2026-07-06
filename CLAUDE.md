# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Firmware for **Dormouse** — a **CR2032-powered Zigbee 3.0 temperature + humidity
sensor** on the Silicon Labs **MGM210LA22JNF2** module (EFR32MG21, Cortex-M33,
2.4 GHz). ("MGM210L"/"MGM210LA22JNF" name the *silicon*; "Dormouse" is the
*product*.) It is a Zigbee **sleepy end device**: it wakes every 5 minutes, reads
an external SHT4x/Si7021
I²C sensor, writes the ZCL Temperature Measurement, Relative Humidity, and Power
Configuration attributes, lets the reporting engine push them to the coordinator,
then returns to EM2 sleep. It integrates with Home Assistant via ZHA or Zigbee2MQTT.

## Build & flash

There is **no host/unit test suite** — this is on-target embedded firmware.
"Testing" means flashing to hardware and observing the join + reports (over RTT
logs and in ZHA/Z2M). Do not invent `npm test`/`pytest`-style commands.

Toolchain is installed via **SLT** (Silicon Labs Tool), not a manual SDK path:

```bash
# one-time: install SDK 2026.6.0 + slc/gcc/zap/commander into ~/.silabs/slt/
slt install -f tools/pkg.slt            # slt lives at ~/slt-cli/slt by default

source tools/env.sh     # puts slc, arm-none-eabi-gcc, commander, zap on PATH
tools/build.sh          # slc generate (runs ZAP) + make -> build/build/debug/*.s37
tools/build.sh clean    # remove ./build
tools/flash.sh          # commander flash over J-Link
commander rtt --device MGM210LA22JNF     # live device logs
```

This flow is **verified working**: SDK 2026.6.0, slc-cli 6.0.22, GCC 14.2 —
`slc generate` → compile → link produces a ~176 KB flashable `.s37` that fits the
part (1 MB flash / 96 KB RAM; the "~130 KB bss" reported by `size` is the memory
manager's heap auto-sized to fill RAM, not static usage).

The build is two stages, and this matters:
1. **`slc generate`** reads `mgm210l_zigbee_temp.slcp`, pulls the listed SDK
   components, runs **ZAP** over `config/zcl/*.zap`, and writes a Makefile project
   into `./build`. `build.sh` then copies `config/sl_i2cspm_sensor_config.h` over
   the generated one (a bespoke module has no board file, so slc emits a pin-less
   I²C template — our pin map must overwrite it every generate).
2. **`make`** compiles the generated project + `src/` with `arm-none-eabi-gcc`.

Gotchas that cost real debugging (all baked into the `.slcp` / scripts now):
- **SDK id** must be `silabs.simplicity_sdk` with an **exact** version
  (`2026.6.0`, not a `>=` range).
- **Target part is `MGM210LA22JNF`** — the OPN's trailing `2` is a tape-and-reel
  code, not part of the device component id. Passed via `--with`, not in `.slcp`.
- The low-power **leaf stack** requires `SLI_ZIGBEE_PRIMARY_NETWORK_DEVICE_TYPE =
  ..._SLEEPY_END_DEVICE` in the `.slcp` `configuration:` block, or generation is
  refused.
- `main()` comes from the **`sl_main`** component (auto-generated) — do **not**
  add your own `main.c` (double definition).
- `slc --sdk` / `slc configuration` are deprecated in favour of
  `--sdk-package-path` / `.slconf`; scripts use the former for now.

## Architecture

**`mgm210l_zigbee_temp.slcp` is the source of truth.** Components, the target
part, sleepy-device timing, and TX power all live there. To change what the
firmware *includes* (a cluster, a peripheral, the stack variant), edit the
`.slcp` and **regenerate** — do not hand-edit anything under `./build`, it is
overwritten on every generate.

Two layers of config, do not confuse them:
- **`.slcp`** = which components/peripherals exist + their tuning knobs.
- **`config/zcl/*.zap`** = the Zigbee data model (endpoints, clusters,
  attributes). Edit it with the ZAP tool (`zap config/zcl/…​.zap`) or Simplicity
  Studio, never by hand. The `#define`s in `src/app.h` mirror this model and
  must stay in sync with it.

Application flow (`src/app.c`), all event-driven, no RTOS:
- `sl_zigbee_af_main_init_cb` → init sensor + the periodic `measure_event`.
- Not on a network → the measure event calls `sl_zigbee_af_network_steering_start()`
  and retries; on `SL_STATUS_NETWORK_UP` (`sl_zigbee_af_stack_status_cb`) the
  measurement event goes active.
- `measure_event` → `temp_sensor_read`, `app_read_battery_mv`, write the three
  ZCL attributes, emit a `debug_log` line, reschedule at
  `debug_measure_interval_ms()` (5 min normally, 10 s in debug mode). The
  `zigbee_reporting` component turns attribute writes into reports; Power Manager
  puts the MCU back to EM2 between events.

`src/debug.c` implements **debug mode**, toggled at runtime from Home Assistant.
See the dedicated section below.

`src/temp_sensor.c` is a self-contained **SHT4x** driver over the Silicon Labs
I²CSPM instance named `sensor` (CRC-8 poly 0x31 verified). Swapping to a Si7021
means changing only the command byte + conversion formula, not the plumbing.

The ZCL model exposed on **endpoint 1** (HA profile 0x0104, device 0x0302 HA
Temperature Sensor): Basic (0x0000), Power Configuration (0x0001), Identify
(0x0003), Temperature Measurement (0x0402), Relative Humidity Measurement
(0x0405), and the manufacturer-specific MGM Debug cluster (0xFC10). Encodings that
must be exact or HA shows values off by 100×/2×: temperature int16 **centi-degrees**
(°C × 100), humidity uint16 **0.01 % units** (%RH × 100), battery percentage
**0.5 % units** (0–200). The model lives in `config/zcl/mgm210l_zigbee_temp.zap`
and the `#define`s in `src/app.h` mirror it — see `config/zcl/README.md` (and note
the custom-cluster XML injection that `build.sh` performs for 0xFC10).

## Application API notes (`src/app.c`)

The sources are written against the **Simplicity SDK 2026.6.0** Zigbee App
Framework and compile clean, using the current API surface (verified against the
`zigbee_z3_switch` example):
- Entry callbacks: `sl_zigbee_af_main_init_cb`, `sl_zigbee_af_stack_status_cb`
  (`sl_status_t`, compare `SL_STATUS_NETWORK_UP`), `sl_zigbee_af_post_attribute_change_cb`.
- Events: `sl_zigbee_af_event_t` + `sl_zigbee_af_event_init/set_active/set_delay_ms`.
- Attributes: `sl_zigbee_af_write_server_attribute` /
  `..._manufacturer_specific_server_attribute`; ZCL types are `ZCL_*_ATTRIBUTE_TYPE`.
- Network: `sl_zigbee_af_network_state()` vs `SL_ZIGBEE_JOINED_NETWORK`,
  `sl_zigbee_af_network_steering_start()`.
- Stay-awake (debug): `sl_zigbee_af_add_to_current_app_tasks(SL_ZIGBEE_AF_STAY_AWAKE)`.

If you ever move to a different SDK generation, these `sl_zigbee_af_*` names may
shift (older EmberZNet used `emberAf*`) — reconcile against the generated headers.

`app_read_battery_mv()` is **implemented** via the IADC (`emlib_iadc` +
`clock_manager`): `battery_init()` (called from main init) configures a single
conversion of `iadcPosInputAvdd` (AVDD/4) against the internal 1.21 V ref, and
the read polls `IADC_IF_SINGLEDONE` then scales `4·raw·vref/4095`. The CR2032 is
on VDD, so this reads the cell directly — no divider. Modelled on the SDK's
`esl_tag_battery_iadc.c`; the busy-wait poll is fine for a 5-min cadence.

## Power model (why the code is shaped this way)

Everything is subordinate to CR2032 battery life:
- **Sleepy end device**, not router — the radio is off between polls; the device
  sleeps in EM2. Long poll interval is 300 s (matches the 5-min cadence).
- **TX power is capped at 8 dBm** in the `.slcp`, *not* the module's +20 dBm max
  — a coin cell (~10–40 Ω internal R) browns out on a full-power TX pulse. If you
  raise it, you must revisit decoupling (see `docs/hardware.md`).
- Prefer size optimization (`-Os`) and pull debug components (`segger_rtt`,
  `iostream_rtt`) for production — RTT/idle logging costs current.
- When adding features, ask "what does this cost per wake / in sleep current?"
  A busy-wait, a kept-open peripheral, or a shorter poll interval directly cuts
  months off the battery.

## Debug mode

A runtime debug mode (`src/debug.c`) that Home Assistant controls, for bench
diagnostics. Enabling it does two things: drops the sample cadence from 5 min to
**10 s**, and mirrors each log line into Home Assistant.

It is exposed through a **manufacturer-specific ZCL cluster `0xFC10`** (mfr code
`0x1002`) on endpoint 1 — defined in `config/zcl/custom-clusters.xml` (which
`build.sh` injects into the SDK's ZCL set), mirrored by the `#define`s in
`src/app.h`, and consumed by the Z2M converter. Attributes: `debug_enabled`
(RW bool — the HA toggle), `debug_text` (reportable string — last log line),
`debug_status` (reportable uint8 — 0=OK/1=I2C/2=CRC), `sample_interval_s` (RW —
normal cadence override). If you add/rename an attribute you must change all
three places or HA and firmware silently disagree.

Control flow: HA writes `debug_enabled` → `emberAfPostAttributeChangeCallback`
(app.c) → `debug_set_enabled()` flips the cadence and calls
`sl_zigbee_af_force_end_device_to_stay_awake()`; `debug_log()` (app.c's measure
loop) then publishes each line to `debug_text`/`debug_status`.

Things to keep true when touching this:
- **RTT is the real log.** `debug_log()` always writes to the SWD/RTT console
  (`commander rtt`); the ZCL `debug_text` is a best-effort mirror of the *last*
  line only. Zigbee cannot stream a console, and the device is sleepy — don't
  try to turn `debug_text` into a full log stream.
- **Enabling debug can lag by up to one poll interval** — a sleepy end device
  only receives the downlink write on its next parent poll. Once enabled it
  stays awake, so disabling is prompt. This asymmetry is intentional; document
  it if you change the poll strategy.
- **Debug mode is not sticky** — `debug_init()` forces it off on every boot, on
  purpose (10 s sampling would flatten the CR2032 in days). Do not persist it to
  a token without a strong reason.
- Keep `debug_log()` cheap: it uses a fixed 40-byte buffer and `vsnprintf`; don't
  add heap allocation or blocking I/O to the measurement path.

## Home Assistant integration

- **ZHA**: temperature, humidity + battery are zero-config (derived from the
  standard clusters). The custom debug cluster (`0xFC10`) does **not** auto-expose
  — it needs a ZHA quirk (zha-device-handlers) to appear as switch/sensor entities.
- **Zigbee2MQTT**: needs `integration/zigbee2mqtt/dormouse.js` as an external
  converter, and the Basic cluster `modelId` in the ZAP must match its
  `zigbeeModel` (`Dormouse`). The converter exposes temperature, humidity,
  battery, and the debug entities (`debug_mode` switch, `debug_log`, `debug_status`,
  `sample_interval`). It also sets reporting to ≤5 min / 0.2 °C change — keep
  that in sync with any change to `MEASURE_INTERVAL_MS`. The `MFG` code in the
  converter must equal `MGM_MANUFACTURER_CODE` in `src/app.h` and the ZAP.
