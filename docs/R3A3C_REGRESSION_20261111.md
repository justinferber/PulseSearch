# Pulse Search — original regression tests on the recovered source (R3-A3C)

**Date:** 2026-11-11. **Status: PARTIAL.** Environment: Windows 11, CPython **3.13.16** (stdlib only), SQLite with FTS5 confirmed. No WSL, no Docker, no network egress.

## Method

A separate executable development copy was made **outside Git** (`PulseSearch_Dev_R3A3C_20261111/`, 135 files) and all 25 discovered `test_*.py` modules were executed individually with explicit import roots, because MSYS mangles `PYTHONPATH` values containing Windows drive letters.

Machine-readable matrix: `docs/evidence/regression_matrix_r3a3c.json`.

## Result

| | Count |
| --- | --- |
| Modules discovered | 25 |
| Modules passing cleanly | **14** |
| Tests executed | **361** |
| Tests inside passing modules | **275** |

Passing modules: `test_engine` (54), `test_p14` (32), `test_scheduler` (28), `test_p19` (24), `test_p16` (21), `test_quality` (20), `test_r2p29` (20), `test_r2p35` (20), `test_p12` (15), `test_r3a` (15), `test_real_questions` (12), `test_r2p31` (10), `test_r3a2r1` (3), `test_p11_extra` (1).

### Modules held, with cause

| Module | Tests | Cause |
| --- | --- | --- |
| `test_p10` | 6 | `WinError 32` on temporary-directory cleanup of a SQLite file |
| `test_p11` | 6 | `WinError 32` (same teardown lock) |
| `test_p15` | 18 | `WinError 32` (same teardown lock) |
| `test_p17` | 16 | `WinError 32` (same teardown lock) |
| `test_p21` | 16 | `WinError 32` (same teardown lock) |
| `test_p18` | 16 | `WinError 1314`: symlink test needs Windows Developer Mode / privilege |
| `test_r3a2r2` | 8 | interpreter policy rejects `3.13 win32` (`unsupported interpreter`) |
| `test_r3a2` | 0 | cross-package import of `hybrid_core` from the sibling `accepted_hybrid/` tree |
| `test_r2p32` | 0 | cross-package import of `pulse_search_r2p31` from the p31 snapshot |
| `test_r2p33` | 0 | cross-package import of `r2p32_candidate` |
| `test_r2p34` | 0 | cross-package import of `r2p33_candidate` |

## Interpretation

None of these are behavioural regressions attributable to the import: every hash matches the owner original byte-for-byte. Failures are (a) Windows temp-file handle release in `TemporaryDirectory` teardown, (b) a Windows symlink privilege, (c) an interpreter-platform allowlist that names POSIX platforms, and (d) milestone packages that import sibling packages by bare module name and were archived as separate directories rather than one installable tree.

The tests that matter most for engine behaviour — crawl/robots/redirect/indexer/API (`test_engine`, 54 tests) and the hybrid/semantic ranking suites (`test_r2p35`, 20; `test_r3a`, 15; `test_p14`, 32) — pass.

A POSIX or per-package virtualenv run would likely clear (a)–(d); WSL is unavailable and this work must not restart Docker or WSL. **Not verified on POSIX.**

**Result: REGRESSION_TESTS = PARTIAL** (14/25 modules clean, 361 tests executed, 11 modules held with documented causes).
