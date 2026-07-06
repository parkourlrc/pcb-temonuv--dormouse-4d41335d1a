#!/usr/bin/env python3
"""
Dormouse device-identity consistency guard.

The Zigbee model id, manufacturer code, and debug-cluster id are duplicated
across three files that MUST agree, or Home Assistant and the firmware silently
disagree (see CLAUDE.md). This verifies:

  - Basic 'model identifier' (config/zcl/*.zap)  ==  converter zigbeeModel / model
  - MGM_MANUFACTURER_CODE     (src/app.h)         ==  converter MFG  ==  ZAP mfgCode
  - ZCL_DEBUG_CLUSTER         (src/app.h)         ==  converter DEBUG_CLUSTER

Exits non-zero on any mismatch. Run locally:  python3 tools/check_consistency.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = lambda *a: os.path.join(ROOT, *a)
errors = []


# ---- ZAP: model identifier + every manufacturer code ----------------------
zap = json.load(open(glob.glob(p("config/zcl/*.zap"))[0]))
model_zap = None
zap_mfg_codes = set()
for et in zap.get("endpointTypes", []):
    for cl in et.get("clusters", []):
        for at in cl.get("attributes", []):
            if at.get("name", "").lower() == "model identifier":
                model_zap = at.get("defaultValue")
            if at.get("mfgCode"):
                zap_mfg_codes.add(int(at["mfgCode"]))


# ---- src/app.h ------------------------------------------------------------
apph = open(p("src/app.h")).read()
def hexdef(name):
    m = re.search(rf"#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)", apph)
    return int(m.group(1), 0) if m else None
mfg_apph = hexdef("MGM_MANUFACTURER_CODE")
clus_apph = hexdef("ZCL_DEBUG_CLUSTER")


# ---- Zigbee2MQTT converter ------------------------------------------------
conv = open(glob.glob(p("integration/zigbee2mqtt/*.js"))[0]).read()
def jsstr(pat):
    m = re.search(pat, conv)
    return m.group(1) if m else None
def jshex(name):
    m = re.search(rf"{name}\s*=\s*(0x[0-9A-Fa-f]+|\d+)", conv)
    return int(m.group(1), 0) if m else None
model_conv = jsstr(r"model:\s*['\"]([^'\"]+)['\"]")
zbmodel_conv = jsstr(r"zigbeeModel:\s*\[\s*['\"]([^'\"]+)['\"]")
mfg_conv = jshex("MFG")
clus_conv = jshex("DEBUG_CLUSTER")


# ---- compare --------------------------------------------------------------
def check(label, values):
    if None in values:
        errors.append(f"{label}: could not extract a value — got {values}")
    elif len(set(values)) != 1:
        errors.append(f"{label}: MISMATCH {values}")
    else:
        shown = values[0]
        print(f"  OK  {label}: {hex(shown) if isinstance(shown, int) else shown!r}")

check("model id  (ZAP modelId / converter zigbeeModel / converter model)",
      [model_zap, zbmodel_conv, model_conv])
check("mfg code  (app.h / converter / ZAP mfgCode)",
      [mfg_apph, mfg_conv, *sorted(zap_mfg_codes)])
check("debug cluster id  (app.h / converter)",
      [clus_apph, clus_conv])

if errors:
    print("\nCONSISTENCY CHECK FAILED:")
    for e in errors:
        print("  ✗", e)
    sys.exit(1)
print("\nAll device-identity fields are consistent ✓")
