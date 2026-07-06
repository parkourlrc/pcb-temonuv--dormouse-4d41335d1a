#!/usr/bin/env bash
# Put the SLT-installed Silicon Labs toolchain on PATH for this shell.
#   source tools/env.sh
#
# Paths are resolved dynamically via `slt where`, so they keep working after an
# `slt update` / reinstall (the Conan cache dirs are content-hashed and move).
# Requires SLT installed; override its location with SLT_BIN if needed.

SLT_BIN="${SLT_BIN:-$HOME/slt-cli/slt}"
if [ ! -x "$SLT_BIN" ]; then
  echo "env.sh: SLT not found at '$SLT_BIN' — set SLT_BIN to your slt executable" >&2
  return 1 2>/dev/null || exit 1
fi

_slt_where() { "$SLT_BIN" where "$1" 2>/dev/null; }

SLC_DIR="$(_slt_where slc-cli)"                 # .../slc_cli   (contains ./slc)
COMMANDER_DIR="$(_slt_where commander)"         # contains ./commander
ZAP_DIR="$(_slt_where zap)"                     # contains ./zap
GCC_DIR="$(_slt_where gcc-arm-none-eabi)"       # toolchain root (has ./bin)
NINJA_DIR="$(_slt_where ninja)"                 # contains ./ninja
CMAKE_DIR="$(_slt_where cmake)"                 # has ./bin

# Exports the build script relies on.
export SI_SDK="$(_slt_where simplicity-sdk)"    # Simplicity SDK 2026.6.0 root
export ARM_GCC_DIR="$GCC_DIR"

export PATH="$SLC_DIR:$COMMANDER_DIR:$ZAP_DIR:$GCC_DIR/bin:$NINJA_DIR:$CMAKE_DIR/bin:$PATH"

echo "env.sh: SDK   = $SI_SDK"
echo "env.sh: slc   = $(command -v slc)"
echo "env.sh: gcc   = $GCC_DIR/bin/arm-none-eabi-gcc"
