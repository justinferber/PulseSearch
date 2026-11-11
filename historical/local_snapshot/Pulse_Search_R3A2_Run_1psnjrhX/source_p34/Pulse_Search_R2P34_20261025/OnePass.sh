#!/usr/bin/env bash
(
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
echo '=== R2-P34 EXACT FILE/SOURCE/DB SHA VERIFICATION ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' 'f078f5277d9c2e160ef28630c3408a04108196a7bced743ebca079aa24c484f8' "$F/accepted_R2P33.zip" | sha256sum --check
printf '%s  %s\n' '3d86e678fb1208d63b3021f04680304f25354c39b5c7f3248b25c2933104e625' "$F/owner_R2P31_report.json" | sha256sum --check
printf '%s  %s\n' '2414d557213283c47df297d30e242111cf27b5690de0b2c3290c456e0043414f' "$F/owner_R2P32_report.json" | sha256sum --check
[[ -f "$OWNER" ]] || { echo 'HOLD: exact accepted research index not found'; exit 2; }
printf '%s  %s\n' 'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d' "$OWNER" | sha256sum --check
RUN="$(mktemp -d "$D/Pulse_Search_R2P34_Run_XXXXXXXX")"
mkdir -p "$RUN/p33_src" "$RUN/p32_src" "$RUN/p31_src" "$RUN/p29_src" "$RUN/engine"
python3 -m zipfile -e "$F/accepted_R2P33.zip" "$RUN/p33_src"
P33="$RUN/p33_src/Pulse_Search_R2P33_20261025"
(cd "$P33" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' 'f05a6cf68ca572765e15ca0781cc3b36af2b896c7ab80eeec73a459faadaff7d' "$P33/accepted_R2P32.zip" | sha256sum --check
python3 -m zipfile -e "$P33/accepted_R2P32.zip" "$RUN/p32_src"
P32="$RUN/p32_src/Pulse_Search_R2P32_20261025"
(cd "$P32" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' 'bc37c270c9ac10d16c82e0f162554324f9069380ddc8d11f58f3f1675156d4fa' "$P32/accepted_R2P31.zip" | sha256sum --check
python3 -m zipfile -e "$P32/accepted_R2P31.zip" "$RUN/p31_src"
P31="$RUN/p31_src/Pulse_Search_R2P31_20261025"
(cd "$P31" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' '459670257dcfef8cab4fb46c101990c9aeb59d4dffb02da6c72e5b2891b70e88' "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" | sha256sum --check
python3 -m zipfile -e "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" "$RUN/p29_src"
P29="$RUN/p29_src/Pulse_Search_R2P29_20261025"
(cd "$P29" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' '984fd5126cd229f756ee7cc32153e6e50f979634047044d046181825f5b809e5' "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" | sha256sum --check
python3 -m zipfile -e "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" "$RUN/engine"
(cd "$RUN/engine" && sha256sum --check MANIFEST.sha256 >/dev/null)

echo '=== 14 R2-P34 NEW SERIES/NEGATION/GENERALISATION TESTS ==='
PYTHONPATH="$F:$P33:$P32:$P31" python3 -B -m unittest discover -s "$F" -p 'test_r2p34.py' -q
echo '=== 15 R2-P33 RETAINED TESTS ==='
PYTHONPATH="$P33:$P32:$P31" python3 -B -m unittest discover -s "$P33" -p 'test_r2p33.py' -q
echo '=== 12 R2-P32 RETAINED TESTS ==='
PYTHONPATH="$P32:$P31" python3 -B -m unittest discover -s "$P32" -p 'test_r2p32.py' -q
echo '=== 10 R2-P31 RETAINED TESTS ==='
PYTHONPATH="$P31" python3 -B -m unittest discover -s "$P31" -p 'test_r2p31.py' -q
echo '=== 20 R2-P29 RETAINED TESTS ==='
PYTHONPATH="$P29:$RUN/engine" python3 -B -m unittest discover -s "$P29" -p 'test_r2p29.py' -q
echo '=== 285 ACCEPTED ENGINE REGRESSIONS ==='
PYTHONPATH="$RUN/engine" python3 -B -m unittest discover -s "$RUN/engine/tests" -q

echo '=== READ-ONLY REAL 120-PAGE GENERALISATION AUDIT ==='
PYTHONPATH="$F:$P33:$P32:$P31" python3 -B "$F/r2p34_audit.py" \
 --owner-index "$OWNER" --p32-report "$F/owner_R2P32_report.json" \
 --p31-report "$F/owner_R2P31_report.json" --out "$RUN/shadow"

echo '=== VERIFY ORIGINAL DATABASE SHA256 UNCHANGED ==='
printf '%s  %s\n' 'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d' "$OWNER" | sha256sum --check
printf 'WINDOWS_REPORT=%s\n' "$(wslpath -w "$RUN/shadow/r2p34_generalisation_report.json")"
printf 'WINDOWS_HTML=%s\n' "$(wslpath -w "$RUN/shadow/r2p34_generalisation_review.html")"
echo "OUTPUT=$RUN"
echo 'SUCCESS: R2-P34 owner read-only retrieval diagnostic completed; NOT DEPLOYED; NO FACTUAL ANSWERS CERTIFIED'
)
