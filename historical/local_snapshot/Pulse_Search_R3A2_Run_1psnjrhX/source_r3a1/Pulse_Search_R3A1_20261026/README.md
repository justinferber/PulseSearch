# Pulse Search R3-A1 — Honest accuracy gate

A **new major-release track**, not another R2 alias update. Uses unchanged R2-P35 hybrid search source as input. No new ranker deployed.

## Why

The owner R2-P35 completed successfully: 376 tests, 86/86 previously familiar retrieval cases, 11/14 new sealed checks, **0 verified factual answers**. Some exclusion/multi-year conditions were overly permissive. R3-A1 changes the evaluation criteria, not the search algorithm, and exposes errors rather than patching the known questions.

## Default run

`bash OnePass.sh` from WSL after extraction into ChatGPTCode. It exact-SHA verifies the accepted R2-P35 archive, report, source, and immutable 120-page index; reruns all original 376 regression methods plus 15 new quality/model security tests; executes 30 fixed adversarial checks against the read-only owner index and writes JSON/HTML/human-review CSV to a fresh `Pulse_Search_R3A1_Run_*/shadow` folder. No network, model download, paid API, database writes or source body exports. Nonzero failures in the **diagnostic** do not make the launcher fail; report them clearly.

## Optional local model is *not installed or approved*

Only with explicit owner approval, model licensing confirmed, SHA-256 pins for ALL files, and offline dependency installation: set `PULSE_R3_OWNER_APPROVED_MODEL_DIR=/absolute/path/to/approved/local/model` before running OnePass. Required inside that directory:
- `PULSE_LICENSE_REVIEW_ACCEPTED.txt` containing `APPROVED` and licensing/revision details.
- `PULSE_APPROVED_MODEL.sha256` listing each model file with SHA-256 and two spaces before the relative path; do not list the approval or manifest files.
- A complete, standard SentenceTransformer model directory and a locally installed compatible sentence-transformers library.

This loader refuses symlinks, unpinned model files, missing licence approval and file mismatches. Uses `local_files_only=True`, offline hub flags and `trust_remote_code=False`. **The owner must explicitly stage the model; this ZIP doesn't download or permit one automatically.** Optional real model performance must be compared with the default mode and separately independently graded.

## Interpretation

A pass on an authored URL challenge does not mean 100% factual answer accuracy. The CSV is for independent relevance review. `FINAL_EXIT_CODE=0` only means the diagnostic ran and all integrity/regression tests passed; it is **not** deployment approval.
