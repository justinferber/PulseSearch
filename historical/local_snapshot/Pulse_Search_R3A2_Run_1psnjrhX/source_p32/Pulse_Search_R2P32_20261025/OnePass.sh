#!/usr/bin/env bash
(
set -euo pipefail
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
export PYTHONDONTWRITEBYTECODE=1

echo '=== VERIFY R2-P32 EXACT SOURCE AND ACCEPTED P31 EVIDENCE ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' 'bc37c270c9ac10d16c82e0f162554324f9069380ddc8d11f58f3f1675156d4fa' "$F/accepted_R2P31.zip" | sha256sum --check
printf '%s  %s\n' '3d86e678fb1208d63b3021f04680304f25354c39b5c7f3248b25c2933104e625' "$F/owner_R2P31_report.json" | sha256sum --check
if [[ ! -f "$OWNER" ]]; then echo 'HOLD: OWNER 120-PAGE INDEX NOT FOUND'; exit 2; fi
printf '%s  %s\n' 'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d' "$OWNER" | sha256sum --check

RUN="$(mktemp -d "$D/Pulse_Search_R2P32_Run_XXXXXXXX")"
mkdir -p "$RUN/src_p31" "$RUN/src_p29" "$RUN/accepted_engine"
python3 -m zipfile -e "$F/accepted_R2P31.zip" "$RUN/src_p31"
P31="$RUN/src_p31/Pulse_Search_R2P31_20261025"
(cd "$P31" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' '459670257dcfef8cab4fb46c101990c9aeb59d4dffb02da6c72e5b2891b70e88' "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" | sha256sum --check
python3 -m zipfile -e "$P31/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" "$RUN/src_p29"
P29="$RUN/src_p29/Pulse_Search_R2P29_20261025"
(cd "$P29" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' '984fd5126cd229f756ee7cc32153e6e50f979634047044d046181825f5b809e5' "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" | sha256sum --check
python3 -m zipfile -e "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" "$RUN/accepted_engine"
(cd "$RUN/accepted_engine" && sha256sum --check MANIFEST.sha256 >/dev/null)

echo '=== 12 NEW ADVERSARIAL / RIGHTS / READ-ONLY TESTS ==='
PYTHONPATH="$F:$P31" python3 -B -m unittest discover -s "$F" -p 'test_r2p32.py' -q
echo '=== 10 RETAINED R2-P31 TESTS ==='
PYTHONPATH="$P31" python3 -B -m unittest discover -s "$P31" -p 'test_r2p31.py' -q
echo '=== 20 RETAINED R2-P29 TESTS ==='
PYTHONPATH="$P29:$RUN/accepted_engine" python3 -B -m unittest discover -s "$P29" -p 'test_r2p29.py' -q
echo '=== 285 RETAINED ACCEPTED CRAWLER TESTS ==='
PYTHONPATH="$RUN/accepted_engine" python3 -B -m unittest discover -s "$RUN/accepted_engine/tests" -q

echo '=== OWNER REAL 120-PAGE BODY-SIGNAL / HELDOUT RANKING AUDIT: READ-ONLY ==='
PYTHONPATH="$F:$P31" python3 -B "$F/r2p32_evidence.py" \
 --owner-index "$OWNER" --prior-report "$F/owner_R2P31_report.json" --out "$RUN/shadow"

echo '=== OWNER INDEX SHA-256 UNCHANGED ==='
printf '%s  %s\n' 'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d' "$OWNER" | sha256sum --check
echo "WINDOWS_REPORT=$(wslpath -w "$RUN/shadow/r2p32_adversarial_report.json")"
echo "WINDOWS_HTML=$(wslpath -w "$RUN/shadow/r2p32_adversarial_review.html")"
echo "OUTPUT=$RUN"
echo 'SUCCESS: R2-P32 adversarial research DIAGNOSTIC completed, even if report contains misses; NOT deployed'
)
