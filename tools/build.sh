#!/usr/bin/env bash
# Generate the SDK project from the .slcp and build the firmware image.
# Verified working against Simplicity SDK 2026.6.0 + slc-cli 6.0.22 + GCC 14.2.
#
# Prereqs: SLT-installed toolchain (see tools/pkg.slt). tools/env.sh puts slc,
# arm-none-eabi-gcc, ninja, cmake and commander on PATH and exports SI_SDK.
#
# Usage:  tools/build.sh [clean]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="mgm210l_zigbee_temp"
PART="MGM210LA22JNF"        # device component id = module OPN minus the reel "2"
GENDIR="$ROOT/build"

# shellcheck source=/dev/null
source "$ROOT/tools/env.sh"

if [[ "${1:-}" == "clean" ]]; then
  rm -rf "$GENDIR"
  echo "cleaned $GENDIR"
  exit 0
fi

# Trust the SDK (idempotent; harmless if already trusted).
slc signature trust --sdk "$SI_SDK" >/dev/null 2>&1 || true

# Register our manufacturer-specific cluster XML into the SDK's ZCL set. slc
# drives ZAP with the SDK's zcl-zap.json (see build/config/zcl/slc_args.json) and
# ignores per-.zap standalone packages, so the custom cluster (0xFC10) must be
# listed there. Idempotent; re-applied automatically after any `slt` SDK update.
SDK_ZCL="$SI_SDK/zigbee/app/zcl"
cp "$ROOT/config/zcl/custom-clusters.xml" "$SDK_ZCL/mgm-custom-clusters.xml"
python3 - "$SDK_ZCL/zcl-zap.json" <<'PY'
import json, sys
p = sys.argv[1]; j = json.load(open(p))
if "mgm-custom-clusters.xml" not in j["xmlFile"]:
    j["xmlFile"].append("mgm-custom-clusters.xml")
    json.dump(j, open(p, "w"), indent=1)
PY

# 1) Generate the Makefile project (resolves components + runs ZAP over config/zcl).
slc generate "$ROOT/$PROJECT.slcp" -d "$GENDIR" -o makefile \
  --with "$PART" --sdk-package-path "$SI_SDK"

# 2) Apply our I2C pin map. A bespoke MGM210L design has no Silabs board file, so
#    slc emits a pin-less template; overwrite it with the project's real config.
cp "$ROOT/config/sl_i2cspm_sensor_config.h" "$GENDIR/config/sl_i2cspm_sensor_config.h"

# 3) Compile.  Produces $GENDIR/build/debug/$PROJECT.{s37,hex,bin,out}.
make -C "$GENDIR" -f "$PROJECT.Makefile" -j"$(nproc)" ARM_GCC_DIR="$ARM_GCC_DIR"

echo "built: $GENDIR/build/debug/$PROJECT.s37"
