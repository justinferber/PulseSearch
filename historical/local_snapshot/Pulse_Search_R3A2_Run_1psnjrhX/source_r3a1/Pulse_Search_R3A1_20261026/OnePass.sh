#!/usr/bin/env bash
(
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
echo '=== R3-A1 VERIFY PACKAGE, R2-P35 ACCEPTED SOURCE, OWNER REPORT AND OWNER INDEX ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' 'de461cfb31b5913eb754cb7705e523da20405edaae1ed7c8bb88f6831da0e4c4' "$F/accepted_R2P35.zip" | sha256sum --check
printf '%s  %s\n' 'ca056b51a7af76d095d9b4b76f0b3b082cdf92209a45e02aa190ee083f2d5fc1' "$F/owner_R2P35_report.json" | sha256sum --check
[[ -f "$OWNER" ]] || { echo 'HOLD_OWNER_INDEX_MISSING'; exit 2; }
printf '%s  %s\n' "$OWNER_SHA" "$OWNER" | sha256sum --check
RUN="$(mktemp -d "$D/Pulse_Search_R3A1_Run_XXXXXXXX")"
mkdir -p "$RUN/p35_src" "$RUN/p34_src" "$RUN/p33_src" "$RUN/p32_src" "$RUN/p31_src" "$RUN/p29_src" "$RUN/engine"
python3 -m zipfile -e "$F/accepted_R2P35.zip" "$RUN/p35_src"
P35="$RUN/p35_src/Pulse_Search_R2P35_20261025"
(cd "$P35" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P35/accepted_R2P34.zip" "$RUN/p34_src"
P34="$RUN/p34_src/Pulse_Search_R2P34_20261025"
(cd "$P34" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P34/accepted_R2P33.zip" "$RUN/p33_src"
P33="$RUN/p33_src/Pulse_Search_R2P33_20261025"
(cd "$P33" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P33/accepted_R2P32.zip" "$RUN/p32_src"
P32="$RUN/p32_src/Pulse_Search_R2P32_20261025"
(cd "$P32" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P32/accepted_R2P31.zip" "$RUN/p31_src"
P31="$RUN/p31_src/Pulse_Search_R2P31_20261025"
(cd "$P31" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" "$RUN/p29_src"
P29="$RUN/p29_src/Pulse_Search_R2P29_20261025"
(cd "$P29" && sha256sum --check MANIFEST.sha256 >/dev/null)
python3 -m zipfile -e "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" "$RUN/engine"
(cd "$RUN/engine" && sha256sum --check MANIFEST.sha256 >/dev/null)
echo '=== 15 NEW R3 INDEPENDENT QUALITY GATE AND MODEL INTEGRITY TESTS ==='
PYTHONPATH="$F:$P35" python3 -B -m unittest discover -s "$F" -p 'test_r3a.py' -q
echo '=== 20 ACCEPTED R2-P35 HYBRID TESTS ==='
PYTHONPATH="$P35" python3 -B -m unittest discover -s "$P35" -p 'test_r2p35.py' -q
echo '=== 14 RETAINED R2-P34 TESTS ==='
PYTHONPATH="$P34:$P33:$P32:$P31" python3 -B -m unittest discover -s "$P34" -p 'test_r2p34.py' -q
echo '=== 15 RETAINED R2-P33 TESTS ==='
PYTHONPATH="$P33:$P32:$P31" python3 -B -m unittest discover -s "$P33" -p 'test_r2p33.py' -q
echo '=== 12 RETAINED R2-P32 TESTS ==='
PYTHONPATH="$P32:$P31" python3 -B -m unittest discover -s "$P32" -p 'test_r2p32.py' -q
echo '=== 10 RETAINED R2-P31 TESTS ==='
PYTHONPATH="$P31" python3 -B -m unittest discover -s "$P31" -p 'test_r2p31.py' -q
echo '=== 20 RETAINED R2-P29 TESTS ==='
PYTHONPATH="$P29:$RUN/engine" python3 -B -m unittest discover -s "$P29" -p 'test_r2p29.py' -q
echo '=== 285 ACCEPTED ENGINE TESTS ==='
PYTHONPATH="$RUN/engine" python3 -B -m unittest discover -s "$RUN/engine/tests" -q
echo '=== R3-A1 REAL OWNER 120-PAGE ADVERSARIAL QUALITY SCORECARD: READ-ONLY ==='
ARGS=()
if [[ -n "${PULSE_R3_OWNER_APPROVED_MODEL_DIR:-}" ]]; then
  ARGS=(--owner-approved-model-dir "$PULSE_R3_OWNER_APPROVED_MODEL_DIR")
  echo 'OWNER REQUESTED LOCAL ONLY PINNED EMBEDDING MODEL MODE'
else
  echo 'NO OWNER-AUTHORISED EMBEDDING MODEL: BASELINE MODE, SEMANTIC MODEL GATE REMAINS HOLD'
fi
PYTHONPATH="$F:$P35" python3 -B "$F/r3a_eval.py" --index "$OWNER" \
  --report "$F/owner_R2P35_report.json" --out "$RUN/shadow" "${ARGS[@]}"
echo '=== VERIFY OWNER INDEX SHA-256 STILL UNCHANGED ==='
printf '%s  %s\n' "$OWNER_SHA" "$OWNER" | sha256sum --check
printf 'WINDOWS_REPORT=%s\n' "$(wslpath -w "$RUN/shadow/r3a1_quality_report.json")"
printf 'WINDOWS_HTML=%s\n' "$(wslpath -w "$RUN/shadow/r3a1_quality_review.html")"
printf 'WINDOWS_HUMAN_REVIEW_CSV=%s\n' "$(wslpath -w "$RUN/shadow/r3a1_human_review_template.csv")"
echo "OUTPUT=$RUN"
echo 'SUCCESS: R3-A1 quality DIAGNOSTIC complete; research only, semantic/factual certification NOT passed, NOT DEPLOYED'
)
