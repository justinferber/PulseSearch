#!/usr/bin/env bash
# Owner-approved ONLINE model and wheel acquisition -> SHA-lock -> OFFLINE test.
# No index/API/crawler writes, no model deployment.
(
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
F="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OWNER="$D/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
PARENT="$HOME/.pulse-search-r3a2-research-v1"
A1REP="$D/Pulse_Search_R3A1_Run_XmiTzc5D/shadow/r3a1_quality_report.json"
echo '=== VERIFY R3-A2 PACKAGE AND ACCEPTED OWNER INDEX ==='
(cd "$F" && sha256sum --check MANIFEST.sha256)
printf '%s  %s\n' '1fb591e8dc20e881314daef053c689bdad59a6bda82a190af6655abb1b16ccf8' "$F/accepted_R3A1.zip" | sha256sum --check
printf '%s  %s\n' "$OWNER_SHA" "$OWNER" | sha256sum --check
[[ -f "$A1REP" ]] || { echo 'HOLD_OWNER_R3A1_REPORT_MISSING'; exit 2; }
python3 -B "$F/verify_source_chain.py"
echo '=== VERIFY PREFLIGHT CAN RESOLVE ALL ACCEPTED LOCAL MODULES ==='
PYTHONPATH="$F:$F/accepted_loader:$F/accepted_hybrid" python3 -B -c 'import r3a_cases, r3a_eval, r3a_local_model, hybrid_core, semantic_ranker, r3a2_eval; print("R3A2_IMPORT_PATHS_VERIFIED")'
PYTHONPATH="$F:$F/accepted_loader:$F/accepted_hybrid" python3 -B "$F/preflight.py" --owner-report "$A1REP" --index "$OWNER"
echo '=== TEST R3-A2 SAFETY AND R3-A2R1 IMPORT REPAIR ==='
PYTHONPATH="$F:$F/accepted_loader:$F/accepted_hybrid" python3 -B -m unittest discover -s "$F" -p 'test_r3a2*.py' -q
ROOT="${PARENT}.provisioning"
if [[ -f "$ROOT/PROVISION_SUCCESS.json" ]]; then
  echo 'REUSING PREVIOUSLY PINNED ISOLATED PROVISIONING (NO NEW DOWNLOAD)'
else
  echo '=== AUTHORISED ONE-TIME HUGGING FACE + PYPI + PYTORCH CPU DOWNLOAD ==='
  PYTHON_BIN="$(python3 -B "$F/select_python.py")"
  "$PYTHON_BIN" -B "$F/provision.py" --root "$PARENT"
fi
bash "$F/Offline_Evaluate.sh"
)
