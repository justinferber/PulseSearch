#!/usr/bin/env bash
(
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
EXPECTED='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
echo '=== R2-P35 HYBRID RESEARCH: SHA VERIFY SOURCE / ACCEPTED DB ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' '5159cc45926135253a7676b0b2dd878e6ab66a24156da07d81fd4c7753013db3' "$F/accepted_R2P34.zip" | sha256sum --check
printf '%s  %s\n' 'c15eaba6344394dffc387ecc0599a05c6f924f770ab0de87010d1e27ad02e4ce' "$F/owner_R2P34_report.json" | sha256sum --check
[[ -f "$OWNER" ]] || { echo 'HOLD: accepted exact owner research index not present'; exit 2; }
printf '%s  %s\n' "$EXPECTED" "$OWNER" | sha256sum --check
RUN="$(mktemp -d "$D/Pulse_Search_R2P35_Run_XXXXXXXX")"
mkdir -p "$RUN/p34_src" "$RUN/p33_src" "$RUN/p32_src" "$RUN/p31_src" "$RUN/p29_src" "$RUN/engine"
python3 -m zipfile -e "$F/accepted_R2P34.zip" "$RUN/p34_src"
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
# Tested research package. No model weights provisioned; no downloads or DB updates.
echo '=== 20 NEW HYBRID / RIGHTS / ABSTENTION / CALIBRATION TESTS ==='
PYTHONPATH="$F" python3 -B -m unittest discover -s "$F" -p 'test_r2p35.py' -q
echo '=== 14 R2-P34 RETAINED TESTS ==='
PYTHONPATH="$P34:$P33:$P32:$P31" python3 -B -m unittest discover -s "$P34" -p 'test_r2p34.py' -q
echo '=== 15 R2-P33 RETAINED TESTS ==='
PYTHONPATH="$P33:$P32:$P31" python3 -B -m unittest discover -s "$P33" -p 'test_r2p33.py' -q
echo '=== 12 R2-P32 RETAINED TESTS ==='
PYTHONPATH="$P32:$P31" python3 -B -m unittest discover -s "$P32" -p 'test_r2p32.py' -q
echo '=== 10 R2-P31 RETAINED TESTS ==='
PYTHONPATH="$P31" python3 -B -m unittest discover -s "$P31" -p 'test_r2p31.py' -q
echo '=== 20 R2-P29 RETAINED TESTS ==='
PYTHONPATH="$P29:$RUN/engine" python3 -B -m unittest discover -s "$P29" -p 'test_r2p29.py' -q
echo '=== 285 ACCEPTED ENGINE TESTS ==='
PYTHONPATH="$RUN/engine" python3 -B -m unittest discover -s "$RUN/engine/tests" -q
echo '=== READ-ONLY REAL 120-PAGE HYBRID ARCHITECTURE DIAGNOSTIC ==='
PYTHONPATH="$F" python3 -B "$F/r2p35_audit.py" --index "$OWNER" \
 --prior-report "$F/owner_R2P34_report.json" --out "$RUN/shadow"
echo '=== OWNER INDEX SHA256 IMMUTABLE ==='
printf '%s  %s\n' "$EXPECTED" "$OWNER" | sha256sum --check
printf 'WINDOWS_REPORT=%s\n' "$(wslpath -w "$RUN/shadow/r2p35_hybrid_report.json")"
printf 'WINDOWS_HTML=%s\n' "$(wslpath -w "$RUN/shadow/r2p35_hybrid_review.html")"
echo "OUTPUT=$RUN"
echo 'SUCCESS: R2-P35 read-only architecture diagnostic completed, NOT DEPLOYED; semantics/facts NOT CERTIFIED'
)
