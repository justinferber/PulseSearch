# Pulse Search — original source and fixture import (R3-A3C)

**Date:** 2026-11-11. **Branch:** `fb2/r3-a3c-frozen54-replay-and-history-20261111`. **Project:** standalone Pulse Search only. **Status:** research-only; production HOLD.

## What was imported

`tools/stage_historical_source.py` was run twice: a read-only dry run, then `--apply` after review. The second pass used the new `--include-fixtures` flag, because the original regression modules read frozen `.json`/`.sh` fixtures by relative path and a source-only import left six modules unable to import their own data.

| Property | Value |
| --- | --- |
| Files | **135** (95 `.py`/`.md` + 40 `.json`/`.sh`) |
| Bytes | **1,487,581** (manifest `total_bytes`) |
| Hash mismatches against `docs/evidence_inventory.json` | **0** |
| Destination | `historical/local_snapshot/<original package path>` |
| Manifest | `historical/SOURCE_IMPORT_MANIFEST_20261111.json` |
| Owner originals modified | **No** (`ORIGINAL_SOURCE_MODIFIED=NO`) |

Staged families include `source_engine/` (56 files), `source_p29` (6), `source_p31` (10), `source_p32` (7), `source_p33` (8), `source_p34` (8), `source_r2p35` (10), `source_r3a1` (8) and the R3-A2R2 evaluation package.

## Provenance and honesty

These are **snapshot imports, not original Git history**. The commits record what exists on disk today, verified by hash; they do not claim original author dates, original commit ancestry, or that the owner's working tree ever was a repository. The manifest states this explicitly (`"kind": "PulseSearch historical snapshot import; NOT original Git ancestry"`).

## Confidentiality, licence and secret review

Performed before `--apply`, over all eligible files:

- No private-key blocks, GitHub/AWS/Slack tokens, `Bearer` literals or `sk-`-style keys.
- Only two `@` strings, both reserved example addresses in test data (`pw@example.com`, `b@example.com`).
- Only secret-shaped token is the **variable name** `PULSE_SEARCH_TOKEN` read from the environment; no value is stored.
- No `.env`, credentials, virtualenvs, SQLite databases, model weights, or publisher body text. `git add` preview confirmed only `.py`/`.md`/`.json`/`.sh`.
- Licensing: the code is owner-authored; there is no vendored third-party source. Optional runtime dependencies (`numpy`, `sentence_transformers`) are imported behind explicit availability guards and are **not installed or downloaded here**.

## Why fixture import is safe

The 40 fixtures are frozen research inputs (seed lists, reviewed-source metadata, owner review JSON, offline runners) already covered by the 338-file pinned inventory with `publish: true`. The flag keeps every gate: pinned SHA-256, byte length, total-size cap, credential regexes, no-overwrite, clean-worktree and branch assertions.

## Reproduce

```bash
python tools/stage_historical_source.py \
  --root <ChatGPTCode> --repo <clean PulseSearch worktree> --include-fixtures        # dry run
python tools/stage_historical_source.py \
  --root <ChatGPTCode> --repo <clean PulseSearch worktree> --include-fixtures --apply
```

**Result: HISTORY_BACKFILL = PASS** (verified, reviewed, imported, committed).
