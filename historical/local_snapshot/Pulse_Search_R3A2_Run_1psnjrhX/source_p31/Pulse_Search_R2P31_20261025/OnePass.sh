#!/usr/bin/env bash
(
set -euo pipefail
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
export PYTHONDONTWRITEBYTECODE=1

echo '=== PINNED R2-P31 SOURCE / REVIEW / INDEX PROVENANCE ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' '459670257dcfef8cab4fb46c101990c9aeb59d4dffb02da6c72e5b2891b70e88' "$F/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" | sha256sum --check
printf '%s  %s\n' '3cd67802d2dcedb00a0e9c9097e98f682a17d83df92381076d9e860087b08514' "$F/r2p30_recall_report.json" | sha256sum --check
printf '%s  %s\n' '328f3129f190f1d50905a37fd8ccd829104c9418808c79be161b5b02dfb32d5c' "$F/r2p29_shadow_report.json" | sha256sum --check
printf '%s  %s\n' '5b343dc1710663e248a958f486f293a1af67702ebe8980aa7b31641ad05e6787' "$F/live_100_report.json" | sha256sum --check
if [[ ! -f "$OWNER" ]]; then echo 'HOLD: ACCEPTED 120-PAGE OWNER INDEX NOT FOUND'; exit 2; fi
printf '%s  %s\n' 'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d' "$OWNER" | sha256sum --check

WORK="$(mktemp -d "$D/Pulse_Search_R2P31_Run_XXXXXXXX")"
mkdir -p "$WORK/accepted_src" "$WORK/accepted_engine"
python3 -m zipfile -e "$F/Pulse_Search_R2P29_ReadOnly_Ranking_20261025.zip" "$WORK/accepted_src"
P29="$WORK/accepted_src/Pulse_Search_R2P29_20261025"
(cd "$P29" && sha256sum --check MANIFEST.sha256 >/dev/null)
printf '%s  %s\n' '984fd5126cd229f756ee7cc32153e6e50f979634047044d046181825f5b809e5' "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" | sha256sum --check
python3 -m zipfile -e "$P29/Pulse_Search_R2P21_Engine_Accepted.zip" "$WORK/accepted_engine"
(cd "$WORK/accepted_engine" && sha256sum --check MANIFEST.sha256 >/dev/null)

echo '=== R2-P31 36-QUERY PROXY + 20 EXTRA QUESTION TESTS ==='
PYTHONPATH="$F" python3 -B -m unittest discover -s "$F" -p 'test_r2p31.py' -q

echo '=== RETAINED R2-P29 RANKER REGRESSIONS ==='
PYTHONPATH="$P29:$WORK/accepted_engine" python3 -B -m unittest discover -s "$P29" -p 'test_r2p29.py' -q

echo '=== RETAINED R2-P21 ACCEPTED ENGINE REGRESSIONS ==='
PYTHONPATH="$WORK/accepted_engine" python3 -B -m unittest discover -s "$WORK/accepted_engine/tests" -q

echo '=== READ-ONLY OWNER 120-PAGE EVALUATION ==='
PYTHONPATH="$F:$P29:$WORK/accepted_engine" python3 -B "$F/pulse_search_r2p31.py" \
 --owner-index "$OWNER" \
 --r2p30-report "$F/r2p30_recall_report.json" \
 --live-report "$F/live_100_report.json" \
 --prior-shadow-report "$F/r2p29_shadow_report.json" \
 --r2p30-source-report "$F/r2p29_shadow_report.json" \
 --out "$WORK/shadow"

echo "WINDOWS_REVIEW_HTML=$(wslpath -w "$WORK/shadow/r2p31_rank_review.html")"
echo "WINDOWS_REPORT=$(wslpath -w "$WORK/shadow/r2p31_rank_report.json")"
echo "OUTPUT=$WORK"
echo 'SUCCESS: R2-P31 read-only owner 120-page research evaluation, not deployed'
)
