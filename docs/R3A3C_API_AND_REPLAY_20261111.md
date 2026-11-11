# Pulse Search — operational API smoke and frozen-query replay status (R3-A3C)

**Date:** 2026-11-11. **Status: API PASS on a rebuilt lab index; REPLAY_54x2 = HOLD / REPLAY_NOT_RUN.**

Harness: `tools/lab_smoke_and_probe.py`. Evidence: `docs/evidence/lab_smoke_and_probe.json`.

## The decisive finding

The accepted owner index **does not exist anywhere** on this machine. SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d` matches **no file** in the 338-file inventory (which contains no database entry at all) and no file in the workspace; the 150 `.db`/`.sqlite` files present are PulseChat browser-profile artefacts and unrelated fixtures. The BGE model directory and weights are also absent, and this interpreter has no `torch`, `transformers`, `sentence_transformers`, `numpy` or `onnxruntime`.

Consequence: the October corpus (120 pages / 120 FTS rows / 7 approved sources) cannot be queried, and the gated BGE mode cannot run without an unreviewed download. **The 54-question replay against the comparison-of-record corpus is therefore not run, and no retrieval score, delta or regression claim is made.** A replay that cannot run is reported as such rather than simulated.

## Operational API — PASS (lab index)

The original `pulse_search_engine.py` was executed unmodified: a loopback fixture server served 10 synthetic, self-authored pages, `initdb` + `crawl` indexed 8 of them, and the original `make_handler` API was served on loopback.

| Check | Result |
| --- | --- |
| Unauthenticated `/v1/search` | **401** as expected |
| Wrong bearer token | **401** as expected |
| `/health` | **200** |
| `/v1/stats` | **200**, reported indexed page count |
| `/v1/search?q=doctor` | **200** with real indexed hits |
| `/v1/search?q=javascript+programming` | **200** with real indexed hits |
| `/v1/search?q=register+to+vote` | **200** with real indexed hits |
| `limit=999` | **400** as expected |
| Unknown route | **404** as expected |

**9/9 checks passed.** Lab index SHA-256 `74bc724df83da8527b24cba8373d8d49cef3523dc89b7625ae48d7e9c0180bf8`; crawl 217 ms; 9 fetch requests, all to `127.0.0.1`. This proves the recovered API serves real indexed results and enforces its token gate and pagination bounds. It does **not** prove the accepted corpus is queryable.

## Frozen 54 — query path exercised, replay not run

All 54 frozen questions from `data/frozen_54.csv` were sent through both available rankers against the lab index to prove the query path accepts the exact wording and emits explicit receipts (including zero-result receipts), with no truncation to five candidates.

| Mode | Queries | With results | Explicit zero / not run | Errors | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| A — engine lexical FTS/BM25 | 54 | 48 | 6 | 0 | 0.43 ms | 1.42 ms |
| H — hybrid lexical (`HybridIndex`) | 54 | 8 | 46 | 0 | 0.37 ms | 1.11 ms |
| B — gated BGE dense | 54 | — | **54 (REPLAY_NOT_RUN)** | 0 | — | — |

These counts describe an 8-page synthetic lab corpus and **must not** be read as retrieval quality, precision, recall or a delta against October. `HybridIndex` reports `dense_model: DISABLED_UNLESS_LOCAL_PINNED_BACKEND_PROVIDED`.

## What would unblock the real replay

1. The accepted owner SQLite index (SHA-256 `bb8e5202…368c35d`) placed on disk, read-only, with a before/after hash receipt.
2. The pinned local BGE model directory with `PULSE_APPROVED_MODEL.sha256`, `PULSE_LICENSE_REVIEW_ACCEPTED.txt`, manifest SHA-256 `3955a9a2…c3c437`, plus a `sentence-transformers` runtime installed in an isolated venv — an explicitly reviewed dependency decision, not an automatic download.

**Result: OPERATIONAL_API = PASS (lab index; accepted index absent). REPLAY_54x2 = HOLD / REPLAY_NOT_RUN.**

> **R3-A3D correction (11 Nov 2026):** the accepted owner index `bb8e5202…` and the pinned BGE stage were subsequently located and verified — see `docs/R3A3D_ARTIFACT_RECOVERY_20261111.md` and `docs/R3A3D_REPLAY_20261111.md`. Statements in this file that either artifact was absent describe the R3-A3C search scope only, and are superseded.
