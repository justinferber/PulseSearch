# Pulse Search — original crawler / indexer / API source located

**Evidence date:** 11 November 2026. **Source:** owner WSL read-only source audit of the local `ChatGPTCode` working directory. **Independently cross-checked:** eight core SHA-256 values against `docs/evidence_inventory.json` from source commit `608cfd679b564f69af81d0f80229c2375f37ef7e`; **8/8 match**. No code imported and no runtime executed by this document.

## Authoritative local source roots

Base: `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`

- Core: `Pulse_Search_R3A2_Run_1psnjrhX/source_engine/`
- R2-P35 hybrid: `Pulse_Search_R3A2_Run_1psnjrhX/source_r2p35/Pulse_Search_R2P35_20261025/`
- R3-A2R2 evaluation package: `Pulse_Search_R3A2R2_20261026/`
- Earlier retained milestone snapshots: `Pulse_Search_R3A2_Run_1psnjrhX/source_p29/`, `source_p31/`, `source_p32/`, `source_p33/`, `source_p34/`, `source_r3a1/`.

The incomplete `Pulse_Search_R3A2_Run_F9zS4WJf` contains a source snapshot but **is not a second successful BGE comparison**; use `1psnjrhX` as the comparison of record.

## Eight exactly matched core files

| Source relative to `source_engine/` | Local WSL SHA-256 = Git inventory SHA-256 |
| --- | --- |
| `pulse_search_engine.py` | `edc7d8e91a232cd0676174a17ac0226085a6acb41bf88fb9e2c29729fd31cf86` |
| `pulse_search_p14.py` | `3c5008d99c552604aa47ad5d4f632e160aedd143099a6e7e315c02c75a363e7d` |
| `pulse_search_p17.py` | `479fe81ab39357848ee51236948859ef43cc54100afeb09df89ddb380ed8f5aa` |
| `pulse_search_p18.py` | `55a30006c956f153a502c3c0a87b479f676d1835676c46f7afd933b70e8acbcb` |
| `pulse_search_p21.py` | `4fa026c39c25a25b97d95d0864d38f783663dff3140d0105fbb471e483dbf3bc` |
| `pulse_search_scheduler.py` | `03aea6b12697e2a75e331d6f8e064b88c16df26d45e10d6ca497ebaf1f3d0404` |
| `pulse_search_quality.py` | `0362887ea324c4a10c7d08f8a3d9ce9b1c9f3472498c654302a0ff52a4ed432b` |
| `pulse_search_real_questions.py` | `f4188e22de3916ae5a7a21c4a5fb9ef567a4ba219440c29e6c9de6cccce3b687` |

## Function-level discovery from WSL audit

The `source_engine/` tree exposes `Fetcher`, `HTMLExtract`, `robots_allowed`, `sitemap_links`, `parse_sitemap`, `research_discover`, `dbopen`, `initdb`, `enqueue`, `search_payload`, `make_handler`, `api_smoke`, `run_benchmark`, scheduler cycle functions, and their original regression tests. The test tree contains **15 `test_*.py` files**. There are also R2-P35 hybrid modules (`hybrid_core.py`, `offline_encoder.py`, `semantic_context.py`) and R3-A2 modules (`r3a2_eval.py`, `semantic_ranker.py`).

The audited listing identifies functions, **not verified live behaviour**. The engine has not been rerun, the API has not been started, the crawler has not fetched new pages, and independent grading is still 0 signed rows. Earlier report: hybrid 19/54, BGE 27/54 *automated* retrieval labels.

## Immediate FB2 task

1. Fetch branch `fb2/r3-a3c-frozen54-replay-and-history-20261111`; validate its base and local cleanliness.
2. Run `tools/stage_historical_source.py` in dry-run, with `--root` pointing to `ChatGPTCode` and `--repo` to a clean PulseSearch worktree; confirm all eligible Python/Markdown files match the pinned Git evidence inventory. No change to the owner source folder.
3. Use `--apply` **only** after the dry-run is PASS. It stages *copies* under `historical/local_snapshot/` and a new manifest; review staged code for secrets/licence issues before `git add` and commit. Do not change `main` or rewrite dates/ancestry.
4. Establish correct module imports, read-only API smoke, original regression-test coverage, then replay the exact 54 frozen questions in **both** rankers; compare full top-10, filters and negative-case receipts.
5. Commit sanitised test evidence, create draft PR, link Issue #3. Do not merge or promote production.

**Explicitly prohibited:** uploading SQLite DB, source bodies, model weights, virtualenvs, tokens, `.env` or binary archives; downloading an unreviewed model, restarting Docker/WSL, enabling production search or rewriting accepted crawler and API.
