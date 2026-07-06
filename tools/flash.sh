#!/usr/bin/env bash
# Flash the built image to an MGM210L over a J-Link / debug probe.
#
# Prereqs: tools/env.sh (puts Simplicity Commander on PATH), probe on the
# module's SWD pins (SWCLK/SWDIO/RESET/GND, plus VCOM/RTT for live logs).
#
# Usage:  tools/flash.sh [path-to-image.s37]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:-$ROOT/build/build/debug/mgm210l_zigbee_temp.s37}"
DEVICE="MGM210LA22JNF"

# shellcheck source=/dev/null
source "$ROOT/tools/env.sh"

[[ -f "$IMAGE" ]] || { echo "image not found: $IMAGE (run tools/build.sh first)"; exit 1; }

commander flash "$IMAGE" --device "$DEVICE"
echo "flashed $IMAGE"

# Live logs over SEGGER RTT (Ctrl-C to stop):
#   commander rtt --device MGM210LA22JNF
# Read the factory-unique EUI-64 (how HA/coordinator identifies each unit):
#   commander device info --device MGM210LA22JNF
