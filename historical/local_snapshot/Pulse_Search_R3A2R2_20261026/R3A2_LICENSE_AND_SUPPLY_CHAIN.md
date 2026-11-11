# R3-A2 licence and supply-chain evidence — 26 October 2026

**Approved purpose:** one-time owner-approved research-only provisioning and local inference on a copy of source metadata. This is not permission to deploy a model-backed API, redistribute weights or package third-party dependencies with products. Preserve accepted Pulse Search R2-P21 engine, R2-P27C owner index and R2-P35 research code unchanged.

## Model identity / declared licence

- Publisher: Beijing Academy of Artificial Intelligence (BAAI), model [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5).
- The publisher repository and model card declare licence `mit` (MIT). The model card states commercial use is allowed under MIT terms, but R3-A2 approval is narrower: local research only. Review the current publisher licence and retain notices before any later distribution.
- Signed repository commit on the official Hugging Face history: `5c38ec7` (22 February 2024). The acquisition code fetches the full 40-character SHA from the official API and refuses a different prefix. Every model component is then fetched by that exact full revision, not by mutable `main`.
- Format: safetensors exclusively (`model.safetensors`); no PyTorch pickle model file and `trust_remote_code=False`.
- Publisher-uploaded weight file **SHA256**: `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad` and **exact 133,466,304 bytes**, verified before execution. Source: [official file details](https://huggingface.co/BAAI/bge-small-en-v1.5/blob/main/model.safetensors).
- All other model files are obtained from the exact revision and SHA256 locked immediately; a validated complete `PULSE_APPROVED_MODEL.sha256` is required before use. Because this assistant cannot download binary weights from its own runtime, those hashes are recorded and verified by the user-authorised WSL acquisition.
- Attribution, provenance and scope are recorded locally in `PULSE_MODEL_PROVENANCE.json` and `PULSE_LICENSE_REVIEW_ACCEPTED.txt`; the latter does **not** authorise production deployment.

## Python dependency security

Exact **requested** versions: `sentence-transformers==5.1.2`, `transformers==4.57.1`, `huggingface-hub==0.35.3`, and `torch==2.6.0+cpu`. The complete transitive wheel versions are resolved in one pass for the owner's WSL platform, matched to the SHA256 published in **PyPI release JSON** or the official **PyTorch CPU simple index**, then locked in `requirements-locked.txt`, `wheels.sha256` and `packages-audit.json` **before** installation. The isolated venv then installs exclusively from the locked local wheelhouse, `--no-index`, `--require-hashes`, `--no-deps`, followed by `pip check`. A version/sha upstream mismatch is a mandatory HOLD.

This is **on-acquisition publisher-verified locking**, not a cross-platform pre-computed wheel lock or a complete third-party dependency licence audit. It avoids pretending that a wheel SHA for the owner's unknown Python ABI has already been verified here. Any later distribution or production use requires an inventory of dependency licences, vulnerability scanning and a separate production review.

## Research restrictions

All evaluation runs set offline Hugging Face and pip modes, with isolated private venv and no crawler, API, Stripe, UNA or source-data writes. Model embeddings and comparisons are local-only; no publisher body text is exported. Dense similarity is not a confidence probability, no factual answers are certified, and hard year, geography, exclusion and source-rights constraints must be separately enforced.

## Verification interpretation

A successful owner exit means actual BGE weights loaded locally and a research comparison ran with unchanged original DB, **not** 100% correctness, independent human relevance validation, calibrated abstention or deployment permission.
