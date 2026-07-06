# ZCL data model (ZAP)

`config/zcl/mgm210l_zigbee_temp.zap` is the **temperature + humidity sensor**
data model, generated into the firmware's attribute table by `slc generate`.
It was authored programmatically (not the ZAP GUI); to tweak it interactively:

```bash
source tools/env.sh
zap config/zcl/mgm210l_zigbee_temp.zap --sdk "$SI_SDK"   # opens the ZAP editor
```

> **After editing the `.zap`, do a clean rebuild:** `tools/build.sh clean && tools/build.sh`.
> `slc generate` copies the `.zap` into `build/config/zcl/` only when that copy
> doesn't already exist — an incremental rebuild keeps reading the **stale** copy,
> so a value change (e.g. the Basic `modelId`) silently won't reach the firmware.
> A clean build forces a fresh copy. (Learned the hard way renaming the model to `Dormouse`.)

## The model — Endpoint 1, HA Temperature Sensor (`0x0302`, profile `0x0104`)

Server clusters:
- `Basic` (0x0000) — `modelId = Dormouse`, `manufacturerName = DIY`,
  power source = battery. `modelId` must match the Z2M converter's `zigbeeModel`.
- `Power Configuration` (0x0001) — `BatteryVoltage` (0x0020),
  `BatteryPercentageRemaining` (0x0021), both reportable.
- `Identify` (0x0003).
- `Temperature Measurement` (0x0402) — `MeasuredValue` (0x0000, INT16S) reportable.
- `Relative Humidity Measurement` (0x0405) — `MeasuredValue` (0x0000, INT16U) reportable.
- **MGM Debug** (manufacturer-specific, cluster **`0xFC10`**, mfr code `0x1002`):
  | ID | Name | Type | Access | Notes |
  |----|------|------|--------|-------|
  | 0x0000 | `debug_enabled`     | BOOLEAN     | R/W | HA toggle → 10 s cadence |
  | 0x0001 | `debug_text`        | CHAR_STRING | R, reportable | last log line |
  | 0x0002 | `debug_status`      | INT8U       | R, reportable | 0=OK 1=I2C 2=CRC |
  | 0x0003 | `sample_interval_s` | INT16U      | R/W | normal cadence override |

Attribute IDs/types/manufacturer code must stay in sync with the `#define`s in
`src/app.h` and the `MFG`/cluster in the Zigbee2MQTT converter.

## The custom cluster: `custom-clusters.xml`

The debug cluster is **not** a standard ZCL cluster, so ZAP needs an XML
definition for it — that's `config/zcl/custom-clusters.xml` (modeled on the SDK's
`…/zigbee/app/zcl/sample-extensions.xml`).

`slc generate` drives ZAP with the **SDK's** `zcl-zap.json`, and ignores any
custom-XML package referenced inside the `.zap` itself. So `tools/build.sh`
**injects** `custom-clusters.xml` into the SDK's ZCL set on every build
(copies it next to the SDK XMLs and adds it to that `zcl-zap.json`'s `xmlFile[]`).
This is idempotent and re-applies automatically after an `slt` SDK update — no
manual step. If you rename the cluster or its attributes, edit `custom-clusters.xml`,
`src/app.h`, the `.zap`, and the Z2M converter together.

> Cluster id is `0xFC10`, not `0xFC00`: the SDK's own `sample-extensions.xml`
> already defines a `0xFC00`/`0x1002` cluster, which would shadow ours.
