# R3-A2R2 — Python wheel compatibility and interpreter-selection correction (26 October 2026)

**Owner-side R3-A2R1 result:** source SHA, exact source chain and preflight passed; 20 tests passed; provisioning stopped *before downloads* with `HOLD_PYTHON_311_OR_312_REQUIRED_FOR_PINNED_CPU_WHEEL`. The guard was too restrictive: official upstream PyTorch CPU 2.6.0 publishes Linux x86-64 wheels for CPython **3.10, 3.11, 3.12 and 3.13**. The pinned Sentence Transformers and Transformers packages declare compatible Python ranges. R3-A2R2 permits only these versions, checks pip and actual isolated venv creation before any network acquisition, and selects an already-installed compatible interpreter without changing the owner WSL system default.

If no compatible interpreter with `pip` and `venv` is installed, the release safely prints `HOLD_NO_PYTHON_310_TO_313_WITH_PIP_AND_VENV` and stops **without downloading the model or altering the system**. It does not install Ubuntu packages, change Python alternatives, add a PPA, or silently upgrade dependencies. An owner-specified path is supported via `PULSE_R3A2_PYTHON=/path/to/python3.12`, but is validated with the same policy.

**All existing model revision, weight SHA, Python dependency versions and publisher wheel-SHA verification remain unchanged.** The R3-A2R1 accepted source chain is bit-for-bit retained except for the `OnePass.sh` interpreter selection and the allowed interpreter version check in `provision.py`. The existing source index, crawler, API, deployment HOLD and 54-question comparison are unchanged. No model/dependency downloads or pretrained-model results have been run in the assistant's container.

Publisher references verified 26 Oct 2026:
- https://download.pytorch.org/whl/cpu/torch/ (torch 2.6.0+cpu cp310/cp311/cp312/cp313 linux_x86_64)
- https://pypi.org/project/sentence-transformers/5.1.2/ (Python >=3.9)
- https://pypi.org/project/transformers/4.57.1/ (Python >=3.9)

---

# R3-A2R1 — Preflight import-path correction (26 October 2026)

The original R3-A2 package stopped **before provisioning** with `ModuleNotFoundError: No module named 'r3a_cases'`. `r3a_cases.py`, `r3a_eval.py` and `r3a_local_model.py` are shipped under `accepted_loader/`; `hybrid_core.py` is shipped under `accepted_hybrid/`. The initial `OnePass.sh` set these paths for unit tests and offline evaluation, but omitted them on the preflight invocation.

**Correction:** an exact-package import probe and the preflight invocation now both use an explicit, isolated `PYTHONPATH` covering the pinned local helper folders. A three-test R1 regression suite checks the failure mode and verifies fail-closed index SHA protection. No model pins, downloads, accepted source files, original index, crawler or API were changed. This replacement ZIP uses the folder `Pulse_Search_R3A2R1_20261026`; do not re-run the old R3-A2 launcher. Model acquisition has still NOT been performed in the assistant environment; it will begin only after the corrected owner-side checks pass.

---

# Pulse Search R3-A2 — owner-authorised genuine local BGE trial

**Research only. No original crawler/index/API writes and no production integration.**

This is a two-phase, auditable experiment. The *one-time online acquisition phase* downloads only an exact-revision copy of BAAI/bge-small-en-v1.5, CPU-only PyTorch and pinned top-level Python packages. It checks the upstream weight SHA256, computes and locks SHA256 for every model file, checks every resolved Python wheel against the publisher-hosted PyPI/PyTorch SHA256, and installs only from the locked local wheelhouse. The separate inference phase disables Hugging Face networking and pip indexes. It compares actual 384-dimensional BGE sentence embeddings against the accepted R2-P35 hybrid ranker on the same immutable owner SQLite dataset.

**Model weights and packages are not inside the ZIP.** This assistant's container could verify public repository data but could not directly download the binary from Hugging Face. Therefore the authorised, reproducible model/download process runs on the owner's WSL host with public network access; if it fails, no embedding result is claimed.

Model declared licence: MIT (publisher's Hugging Face model card). Owner explicitly approved local research setup on 26 October 2026. Model revision locked to signed last commit prefix `5c38ec7`, with exact 40-character commit verified at acquisition. Publisher weight SHA256 locked: `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad` and size 133466304 bytes. Uses `model.safetensors`, not pickle weights or remote execution. **Top-level dependency versions are fixed in code; wheel hashes of all transitive dependencies are verified against upstream publisher records, then frozen locally before installation, not pre-distributed hashes.** That distinction is part of the supply-chain evidence. No install/activation until all provenance and hash gates pass. This is not a licence audit of the full Python dependency tree.

The isolated environment is created under `~/.pulse-search-r3a2-research-v1.provisioning` (not the Windows project folder), while owner reports are written to a new `ChatGPTCode/Pulse_Search_R3A2_Run_*/shadow/` directory. A partial provisioning HOLD stays in the staging directory for owner inspection; no automatic destructive reset. A successful provisioning run is reusable offline without more downloads.

## Owner acceptance gates

- Original 120-page index exact SHA256 and 7 approved-source checks, read-only SQLite connection.
- Accepted R3-A1 source and R2-P35 hybrid release pinned and unpacked without mutation.
- Model repository hash pinned to official commit, MIT declaration checked, safetensors SHA256 verified.
- CPU PyTorch wheel required (`torch==2.6.0+cpu`), isolated local wheelhouse, all wheels SHA256 locked and installed offline.
- Original R3-A1 and R2-P35 tests retained; separate R3-A2 tests verify hard constraints and no fact generation.
- 30 earlier R3-A1 cases and 24 newly frozen cases scored by both rankers side by side.
- Separate retrieval and abstention verdicts; factual answers **remain unverified (0)**; no calibrated confidence.
- User-independent relevance labelling, robust unseen benchmarks and source usage permissions required before deployment.

## Environments and limits

Requires WSL Python 3.10, 3.11, 3.12 or 3.13 with pip and venv, `python3 -m venv` support, internet access for the *acquisition only*, disk space for downloaded model plus CPU PyTorch/dependencies, and CPU inference. If a dependency pin is unavailable or incompatible, **HOLD**: do not silently choose another version. Retain publisher rights: do not redistribute indexed source body text, model binaries or Python wheelhouse without an additional review. All results are metadata-only, with source links.

OnePass runs acquisition then offline evaluation. For repeat runs after provisioning, run `Offline_Evaluate.sh` directly. Both stop on failure. Never treat a successful exit as approval to deploy the model, fact answerer or new search API.
