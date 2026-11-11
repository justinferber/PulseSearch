# R3-A3D — independent review and recovery of the genuine 54-query replay artifacts

**Date:** 11 November 2026. **Owner scope:** standalone Pulse Search, research-only. **Production HOLD**. Previous work: [draft PR #4](https://github.com/justinferber/PulseSearch/pull/4), head `1c2c7ff496f812afe41215f988224099b5885deb`.

## Independent review of R3-A3C

**Verified against GitHub:** PR #4 is open, draft, unmerged, base `main`, head `1c2c7ff`, 151 changed files. It includes a 135-file honest historical source+fixture snapshot (manifest 1,487,581 bytes), local API smoke, a 25-module regression matrix and frozen-grading HOLD evidence. No source-history ancestry was fabricated.

**Accepted (limited):** source snapshot and provenance **recovered**. Core crawler/indexer and loopback API work in a synthetic test environment. Original tests **PARTIAL** (14/25 modules clean, 275 tests within those modules; 361 tests attempted total). Does not establish an accepted production service, a current real-world crawl, or factual correctness.

**Critical API quality correction:** `docs/evidence/lab_smoke_and_probe.json` shows that `search_doctor` returned HTTP 200 with `count: 0`, while `search_vote` returned HTTP 200 with a first result titled `Register with a GP surgery` (followed by other unrelated records). So the reported **9/9 are HTTP status/endpoint checks only**, not nine correct search answers. Label this `API_PROTOCOL_AND_LAB_INDEX_PASS`; ranking/relevance remain unaccepted. Add separate exact-answer/constraint assertions in subsequent lab regression tests, without changing frozen October scoring.

**History correction:** source/fixture snapshots imported and anchored to original SHA-256s, but **not a complete original Git commit history**. Previous R2-P22–P35 evidence needs further provenance reconciliation where available.

**Replay remains genuinely unrun:** no accepted 120-page index or pinned BGE runtime was accessible to FB2's test environment, hence `REPLAY_NOT_RUN` was correct. Synthetic 8-page results (48/54 engine FTS / 8/54 hybrid nonempty) have no accepted relevance score.

## Newly recovered historical exact paths (from pinned original R3-A2R2 source)

Original `Offline_Evaluate_SQLiteCompat_R3.sh` pins:

```text
C:\Users\justi\Desktop\pulseunity\ChatGPTCode\Pulse_Search_R2P27C_Run_gURzKuV2\live\expanded_live_100_research_index.sqlite
INDEX_SHA256=bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d
```

Original `OnePass.sh`, `provision.py` and README pin the **separate WSL home** provisioning stage:

```text
~/.pulse-search-r3a2-research-v1.provisioning/
  model/PULSE_APPROVED_MODEL.sha256
  model/model.safetensors
  model/PULSE_MODEL_PROVENANCE.json
  model/PULSE_LICENSE_REVIEW_ACCEPTED.txt
  PROVISION_SUCCESS.json
  wheels.sha256
  venv/bin/python
MODEL_MANIFEST_SHA256=3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437
WEIGHT_SHA256=3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad
WEIGHT_BYTES=133466304
```

The successful historical evaluation proved these files existed on its host on **26 October 2026**. They may now be moved/deleted, or FB2 may be using a Windows environment unable to see the WSL user's hidden home. Do not assert present until the exact probe returns PASS.

## Immediately executable recovery (read-only; no external downloads)

1. On a working WSL terminal (the owner previously ran read-only WSL source audit), fetch `fb2/r3-a3d-readonly-artifact-recovery-20261111` into an isolated worktree and execute `tools/read_only_replay_artifact_probe.py`:

```bash
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
python3 -B tools/read_only_replay_artifact_probe.py --root "$D"
```

Do not run this from an arbitrary current directory: invoke the script by its actual path in the new Git worktree. If the original provisioning ran as a different WSL account, supply `--stage /home/pulse/.pulse-search-r3a2-research-v1.provisioning` **only when readable and authorised**. Never use `sudo` to force access.

2. Windows-native FB2 fallback (when WSL unavailable):

```powershell
$root = 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode'
python tools/read_only_replay_artifact_probe.py --root $root
# If Windows can access original WSL file share:
python tools/read_only_replay_artifact_probe.py --root $root --stage '\\wsl.localhost\Ubuntu\home\pulse\.pulse-search-r3a2-research-v1.provisioning'
```

If Windows cannot reach the WSL home, record `MODEL_NOT_VISIBLE_FROM_WINDOWS`, not `MODEL_DELETED`. Probe returns only status, hashes, and SQLite table counts; it does not export document bodies.

3. If **both exact pins PASS**, independently inspect the existing original offline runner and its expected paths before executing; make a copy of the original accepted SQLite file in a private read-only lab only if required by that runner. Preserve checksum before and after, and disable all model networking and pip indexes. Use the original accepted frozen 54 cases with **baseline hybrid vs real BGE**, untruncated top 10, exclusion/edition traces, timestamps and latency, and independent grade fields **blank**. Never rewrite the original index or weights.

4. If index is absent but model present, trace only the named R2P27C lineage and already approved owner backups/archives; reconstruct **only in a separate lab** and only if source data/rights, 120/120/7 corpus identity and SHA match are verified. A recreated different index does not qualify as the October replay.
5. If model is missing but index present, do baseline-only research and report `BGE_REPLAY_HOLD`. Do not initiate unreviewed download, pip install, Python change or model substitution. Document the original locked revision/publisher hashes and await a separate explicit reviewed acquisition gate.
6. If neither exists, continue static test repair, source-history provenance and better lab **answer-relevance assertions**; do not label historic replay complete.

## Required deliverables

- Machine-readable artifact probe result and exact host/scope; do not upload index, weights, wallet/other-project files, credentials, or publisher content.
- Separate `INDEX=[PASS|HOLD]`, `BGE_FILES=[PASS|HOLD]`, `BGE_RUNTIME=[PASS|HOLD]`, `REPLAY_54x2=[PASS|HOLD]`.
- Correctly label API smoke as protocol-only and add tests for expected title/canonical-ID/constraint behaviour.
- Run original POSIX regressions only if WSL is available without stopping Docker; never claim Windows platform-hold tests are behaviourally passed.
- Real baseline/dense top-10 per-probe report and blind reviewer workbook **only if full frozen rerun actually occurs**.
- Git commits, evidence hashes, draft PR (or child PR against existing R3-A3C branch), no merge or production promotion.

**Research-only. No production release.**