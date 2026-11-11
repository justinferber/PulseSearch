#!/usr/bin/env bash
# R3-A3D POSIX regression matrix.
# Runs every archived test module with the original provisioning interpreter.
# Read-only: imports nothing from the network and writes only to stdout.
# Usage: posix_regression_matrix.sh <snapshot-dir> <python> [module-filter-regex]
set -uo pipefail

S="${1:?snapshot dir required}"
PY="${2:?python interpreter required}"
FILTER="${3:-.}"

ENG="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_engine"
P29="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_p29/Pulse_Search_R2P29_20261025"
P31="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_p31/Pulse_Search_R2P31_20261025"
P32="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_p32/Pulse_Search_R2P32_20261025"
P33="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_p33/Pulse_Search_R2P33_20261025"
P34="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_p34/Pulse_Search_R2P34_20261025"
R35="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_r2p35/Pulse_Search_R2P35_20261025"
A1="$S/Pulse_Search_R3A2_Run_1psnjrhX/source_r3a1/Pulse_Search_R3A1_20261026"
A2="$S/Pulse_Search_R3A2R2_20261026"
BASE="$ENG:$P29:$P31:$P32:$P33:$P34:$R35:$A1:$A2"

export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PIP_NO_INDEX=1

"$PY" -V

for f in $(find "$S" -name 'test_*.py' | sort); do
  m=$(basename "$f" .py)
  printf '%s' "$m" | grep -Eq "$FILTER" || continue
  d=$(dirname "$f")
  out=$(cd "$d" && PYTHONPATH="$d:$BASE:$d/accepted_loader:$d/accepted_hybrid" "$PY" -B \
        -m unittest discover -s "$d" -p "$m.py" -q 2>&1)
  ran=$(printf '%s\n' "$out" | sed -n 's/^Ran \([0-9]*\) test.*/\1/p' | tail -1)
  if printf '%s\n' "$out" | grep -qE '^OK( |$)'; then
    st=PASS
  else
    st=FAIL
  fi
  echo "MATRIX|$m|$st|${ran:-0}|$d"
  if [ "$st" = FAIL ]; then
    printf '%s\n' "$out" | grep -E '^(FAIL|ERROR|ModuleNotFoundError|AssertionError|[A-Za-z_.]*Error)' | head -4 | sed 's/^/  CAUSE| /'
  fi
done
