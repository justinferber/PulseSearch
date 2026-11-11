#!/usr/bin/env bash
# No package repositories, Hugging Face download or public HTTP within the actual evaluation.
(
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1 PIP_NO_INDEX=1
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
A1REP="$D/Pulse_Search_R3A1_Run_XmiTzc5D/shadow/r3a1_quality_report.json"
STAGE="$HOME/.pulse-search-r3a2-research-v1.provisioning"
[[ -f "$STAGE/PROVISION_SUCCESS.json" && -x "$STAGE/venv/bin/python" ]] || { echo 'HOLD_PROVISION_NOT_COMPLETE'; exit 2; }
echo '=== VERIFY LOCKED MODEL / WHEELS BEFORE OFFLINE MODEL EXECUTION ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
(cd "$STAGE" && sha256sum --check wheels.sha256)
(cd "$STAGE/model" && sha256sum --check PULSE_APPROVED_MODEL.sha256)
printf '%s  %s\n' "$OWNER_SHA" "$OWNER" | sha256sum --check
"$STAGE/venv/bin/python" -B "$F/offline_integrity.py" --stage "$STAGE"
OUT="$(mktemp -d "$D/Pulse_Search_R3A2_Run_XXXXXXXX")"
mkdir -p "$OUT/source_r3a1" "$OUT/source_r2p35" "$OUT/source_p34" "$OUT/source_p33" "$OUT/source_p32" "$OUT/source_p31" "$OUT/source_p29" "$OUT/source_engine"
python3 -m zipfile -e "$F/accepted_R3A1.zip" "$OUT/source_r3a1"
A1="$OUT/source_r3a1/Pulse_Search_R3A1_20261026"
(cd "$A1" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$A1/accepted_R2P35.zip" "$OUT/source_r2p35"
P35="$OUT/source_r2p35/Pulse_Search_R2P35_20261025"
(cd "$P35" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P35/accepted_R2P34.zip" "$OUT/source_p34"
P34="$OUT/source_p34/Pulse_Search_R2P34_20261025"
(cd "$P34" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P34/accepted_R2P33.zip" "$OUT/source_p33"
P33="$OUT/source_p33/Pulse_Search_R2P33_20261025"
(cd "$P33" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P33/accepted_R2P32.zip" "$OUT/source_p32"
P32="$OUT/source_p32/Pulse_Search_R2P32_20261025"
(cd "$P32" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P32/accepted_R2P31.zip" "$OUT/source_p31"
P31="$OUT/source_p31/Pulse_Search_R2P31_20261025"
(cd "$P31" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" "$OUT/source_p29"
P29="$OUT/source_p29/Pulse_Search_R2P29_20261025"
(cd "$P29" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" "$OUT/source_engine"
(cd "$OUT/source_engine" && sha256sum --check MANIFEST.sha256 >/dev/null)

echo '=== APPLY AUDITED P17 SQLITE COMPATIBILITY OVERLAY ==='
"$STAGE/venv/bin/python" -I - "$OUT/source_engine/tests/test_p17.py" <<'PY_P17_FIX'
from pathlib import Path
import hashlib
import sys

p = Path(sys.argv[1])
original = p.read_bytes()

assert hashlib.sha256(original).hexdigest() == (
    "4f5cfd92177c65227b9ba2c80dcfbc06de07854094cee7bde885eade723a3ec5"
), "HOLD_ORIGINAL_P17_HASH_MISMATCH"

old = b"DELETE FROM sitemap_candidates LIMIT 1"
new = (
    b"DELETE FROM sitemap_candidates "
    b"WHERE rowid IN "
    b"(SELECT rowid FROM sitemap_candidates LIMIT 1)"
)

assert original.count(old) == 1, "HOLD_P17_PATCH_TARGET"

corrected = original.replace(old, new)

assert hashlib.sha256(corrected).hexdigest() == (
    "29fe01dbf2e547940a0ab76a2319f43c49c053521fe438ecc17f94f30b8819c9"
), "HOLD_P17_PATCH_HASH"

p.write_bytes(corrected)
print("PASS_AUDITED_P17_OVERLAY")
PY_P17_FIX

echo '=== RETAIN 15 R3-A1 +20 R2-P35 RELEVANCE/SECURITY REGRESSIONS ==='
PYTHONPATH="$A1:$P35" "$STAGE/venv/bin/python" -B -m unittest discover -s "$A1" -p test_r3a.py -q
PYTHONPATH="$P35" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P35" -p test_r2p35.py -q
echo '=== RETAIN 356 EARLIER ACCEPTED ENGINE & R2 REGRESSIONS ==='
PYTHONPATH="$P34:$P33:$P32:$P31" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P34" -p test_r2p34.py -q
PYTHONPATH="$P33:$P32:$P31" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P33" -p test_r2p33.py -q
PYTHONPATH="$P32:$P31" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P32" -p test_r2p32.py -q
PYTHONPATH="$P31" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P31" -p test_r2p31.py -q
PYTHONPATH="$P29:$OUT/source_engine" "$STAGE/venv/bin/python" -B -m unittest discover -s "$P29" -p test_r2p29.py -q
PYTHONPATH="$OUT/source_engine" "$STAGE/venv/bin/python" -B -m unittest discover -s "$OUT/source_engine/tests" -q
echo '=== REAL OFFLINE BGE vs ACCEPTED HYBRID (54 FROZEN QUESTIONS) ==='
PYTHONPATH="$F:$F/accepted_loader:$A1:$P35" "$STAGE/venv/bin/python" -B "$F/r3a2_eval.py" \
  --index "$OWNER" --owner-r3a1-report "$A1REP" \
  --model-dir "$STAGE/model" --out "$OUT/shadow"
echo '=== VERIFY OWNER INDEX UNCHANGED ==='
printf '%s  %s\n' "$OWNER_SHA" "$OWNER" | sha256sum --check
printf 'WINDOWS_REPORT=%s\n' "$(wslpath -w "$OUT/shadow/r3a2_bge_comparison_report.json")"
printf 'WINDOWS_HTML=%s\n' "$(wslpath -w "$OUT/shadow/r3a2_bge_comparison_review.html")"
printf 'WINDOWS_INDEPENDENT_REVIEW=%s\n' "$(wslpath -w "$OUT/shadow/r3a2_independent_review.csv")"
printf 'OUTPUT=%s\n' "$OUT"
echo 'SUCCESS_R3A2_RESEARCH_COMPARISON_COMPLETED_NO_DEPLOYMENT'
)
