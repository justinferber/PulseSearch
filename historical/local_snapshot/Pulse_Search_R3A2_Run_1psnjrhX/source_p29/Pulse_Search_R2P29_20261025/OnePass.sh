#!/usr/bin/env bash
(
set -euo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
INDEX="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
export PYTHONDONTWRITEBYTECODE=1

echo '=== R2-P29 VERIFY PINNED ENGINE / HUMAN / LIVE EVIDENCE ==='
(cd "$DIR" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' \
'984fd5126cd229f756ee7cc32153e6e50f979634047044d046181825f5b809e5' \
"$DIR/Pulse_Search_R2P21_Engine_Accepted.zip" | sha256sum --check

WORK="$(mktemp -d "$D/Pulse_Search_R2P29_Run_XXXXXXXX")"
STAGING="$WORK/accepted_engine"
mkdir "$STAGING"
python3 -m zipfile -e "$DIR/Pulse_Search_R2P21_Engine_Accepted.zip" "$STAGING"
(cd "$STAGING" && sha256sum --check MANIFEST.sha256 >/dev/null)
echo 'PASS: unchanged 285-test accepted source extracted to disposable output'

echo '=== R2-P29 NEW PRECISION / YEAR / ABSTENTION TESTS ==='
PYTHONPATH="$DIR" python3 -B -m unittest discover -s "$DIR" -p 'test_r2p29.py' -q

echo '=== ACCEPTED ENGINE REGRESSION SUITE (UNCHANGED) ==='
PYTHONPATH="$STAGING" python3 -B -m unittest discover -s "$STAGING/tests" -q

echo '=== OWNER 120-PAGE INDEX: FULLY READ-ONLY SEARCH COMPARISON ==='
PYTHONPATH="$STAGING:$DIR" python3 -B "$DIR/pulse_search_r2p29.py" \
  --owner-index "$INDEX" \
  --live-report "$DIR/live_100_report.json" \
  --corrected-review "$DIR/Pulse_Search_R2P23_Corrected_Reviewed.json" \
  --out "$WORK/shadow"

echo "WINDOWS_REVIEW_HTML=$(wslpath -w "$WORK/shadow/r2p29_shadow_review.html")"
echo "WINDOWS_REPORT=$(wslpath -w "$WORK/shadow/r2p29_shadow_report.json")"
echo "OUTPUT=$WORK"
echo 'SUCCESS: R2-P29 read-only 120-page research shadow acceptance; NOT deployed'
)
