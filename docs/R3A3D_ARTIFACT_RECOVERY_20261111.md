# R3-A3D — artifact recovery: the October index and pinned BGE stage both survive

**Date:** 11 November 2026. **Scope:** standalone Pulse Search, research only. **Production: HOLD.**
**Branch:** `fb2/r3-a3d-readonly-artifact-recovery-20261111` (from `6019ec9`).
**Run as:** the original WSL account `pulse`, interpreter `~/.pulse-search-r3a2-research-v1.provisioning/venv/bin/python` (CPython 3.12.15).

## Correction to the R3-A3C record

R3-A3C reported that the accepted owner index `bb8e5202…368c35d` existed "nowhere on this machine".
That statement was wrong, and it was wrong for exactly the reason the independent review gave: the
search was limited to Windows-side `Pulse_Search_*` directories and to a WSL instance that FB2 could
not reach at the time. It never probed the exact pinned path, and never read the `pulse` WSL home.

Retracted claims, superseded by this document:

- "the inventory contains no database entry, and all 150 local `.db` files are unrelated"
- "BGE weights and any `torch`/`sentence-transformers` runtime are absent"
- "corpus-faithful replay impossible"

Each was a statement about a search scope, not about the machine. `docs/R3A3C_API_AND_REPLAY_20261111.md`
and `docs/STATUS_R3A3C_20261111.md` carry an appended correction pointing here.

## Probe executed

`tools/read_only_replay_artifact_probe.py` (committed on this branch) was run **from the `pulse`
account**, by its worktree path, against the exact pinned root:

```
INDEX=PASS_SHA256
INDEX_PATH=/mnt/c/Users/justi/Desktop/pulseunity/ChatGPTCode/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite
SQLITE_QUICK_CHECK=ok
SQLITE_COUNT_PAGES=120
SQLITE_COUNT_SOURCES=7
MODEL=PASS_PINNED_FILES_NO_INFERENCE
MODEL_PATH=/home/pulse/.pulse-search-r3a2-research-v1.provisioning/model
MODEL_FILES_VERIFIED=12
MODEL_VENV=PRESENT_NOT_EXECUTED
INDEX_STATUS=PASS
MODEL_STATUS=PASS_FILES_ONLY
RESULT=ARTIFACTS_FOUND_NOT_REPLAYED
```

Full stdout: `docs/evidence/r3a3d_artifact_probe.txt`.

## Index

| Property | Observed | Required |
| --- | --- | --- |
| Path | `…/Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite` | exact original path |
| SHA-256 | `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d` | same |
| Bytes | 5,103,616 | — |
| `PRAGMA integrity_check` / `quick_check` | `ok` / `ok` | not corrupt |
| Pages / FTS rows / approved sources | 120 / 120 / 7 | 120 / 120 / 7 |
| Journal mode | `delete` | — |
| Adjoining files | `-wal` 0 bytes, `-shm` 32,768 bytes | untouched |

Read-only proof: hashed before and after every probe and every replay stage; both digests equal, and
the replay opened it with `?mode=ro` plus `PRAGMA query_only=ON`. `owner_index_writes=0`.

## Pinned BGE stage

Stage: `/home/pulse/.pulse-search-r3a2-research-v1.provisioning/` (1.7 GB), dated 26 October 2026.

| Artifact | Observed | Required |
| --- | --- | --- |
| `model/model.safetensors` | `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad`, 133,466,304 bytes | same |
| `model/PULSE_APPROVED_MODEL.sha256` | `3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437` | same |
| Manifest entries verified | 12/12 (paths relative, no symlinks, no `..`) | all |
| `PROVISION_SUCCESS.json` | `ready: true`, weight + manifest hashes match, 33 wheels | ready |
| `requirements-locked.txt` | `sentence-transformers==5.1.2`, `torch` pinned by hash, `numpy==2.5.4` | — |
| `wheelhouse/` | 33 wheels present | — |
| License review | `PULSE_LICENSE_REVIEW_ACCEPTED.txt` contains `APPROVED` | approved |

Provenance (`PROVISION_SUCCESS.json`, sanitised): model revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`,
`wheels_manifest_sha256` `91b8d009…814e651e`.

## Runtime

`venv/bin/python` is CPython **3.12.15** with `torch 2.6.0+cpu`, `transformers 4.57.1`,
`sentence-transformers 5.1.2`, `numpy 2.5.4`, `cuda False`, `torch threads 6`.
The interpreter, wheels and model all predate this task; nothing was installed, upgraded or downloaded
(`PIP_NO_INDEX=1`, `HF_HUB_OFFLINE=1`, no `~/.cache/huggingface`).

The system `python3` (3.14.4) has none of these packages — which is why the stage's own venv, not the
system interpreter, must be used. That is the environment the original October run used.

## Read-only guarantees

- No owner file was written: index hash identical before and after all work.
- No `pip`, `apt`, model download or network egress; all API traffic was `127.0.0.1`.
- Docker and WSL were not restarted or shut down; `wsl.exe` was used only to read and execute.
- No database or weight file is committed to Git.

## Evidence

`docs/evidence/r3a3d_artifact_probe.txt` — probe stdout with host context.
`docs/R3A3D_REPLAY_20261111.md` — the replay executed on these artifacts.
