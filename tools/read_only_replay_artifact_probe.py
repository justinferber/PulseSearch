#!/usr/bin/env python3
"""Pulse Search R3-A3D targeted, READ-ONLY historic artifact locator.

No download, index edits, inference, service restart, or filesystem writes.
Run from the original WSL user account when possible; or pass --stage explicitly.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

INDEX_REL = Path("Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite")
INDEX_SHA = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
MODEL_MANIFEST_SHA = "3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437"
WEIGHTS_SHA = "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"
WEIGHTS_BYTES = 133466304
STAGE_NAME = ".pulse-search-r3a2-research-v1.provisioning"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_index(path):
    if not path.is_file():
        return False
    actual = sha(path)
    if actual != INDEX_SHA:
        print("INDEX_HASH_MISMATCH_PATH=" + str(path))
        print("INDEX_OBSERVED_SHA256=" + actual)
        return False
    print("INDEX=PASS_SHA256")
    print("INDEX_PATH=" + str(path))
    try:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            quick_check = con.execute("PRAGMA quick_check").fetchone()[0]
            print("SQLITE_QUICK_CHECK=" + str(quick_check))
            for table in ("pages", "sources"):
                present = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if present:
                    print("SQLITE_COUNT_" + table.upper() + "=" +
                          str(con.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]))
        finally:
            con.close()
    except sqlite3.Error as exc:
        print("INDEX_SQLITE_READONLY_PROBE_ERROR=" + str(exc))
        return False
    if sha(path) != INDEX_SHA:
        print("HOLD_INDEX_MUTATED_DURING_PROBE")
        return False
    return True


def verify_stage(stage):
    model = stage / "model"
    manifest = model / "PULSE_APPROVED_MODEL.sha256"
    success = stage / "PROVISION_SUCCESS.json"
    weight = model / "model.safetensors"
    if not manifest.is_file() or not weight.is_file() or not success.is_file():
        return False
    print("MODEL_STAGE_CANDIDATE=" + str(stage))
    if sha(manifest) != MODEL_MANIFEST_SHA:
        print("HOLD_MODEL_MANIFEST_SHA_MISMATCH")
        return False
    if weight.stat().st_size != WEIGHTS_BYTES or sha(weight) != WEIGHTS_SHA:
        print("HOLD_MODEL_WEIGHT_SHA_OR_SIZE_MISMATCH")
        return False
    try:
        info = json.loads(success.read_text(encoding="utf-8"))
        if info.get("ready") is not True or info.get("model_manifest_sha256") != MODEL_MANIFEST_SHA:
            print("HOLD_PROVISION_SUCCESS_MISMATCH")
            return False
    except (OSError, ValueError):
        print("HOLD_PROVISION_SUCCESS_UNREADABLE")
        return False
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            print("HOLD_MODEL_MANIFEST_FORMAT")
            return False
        expected, relative = parts[0], parts[1].lstrip("*").strip()
        rel = Path(relative)
        candidate = model / rel
        if rel.is_absolute() or ".." in rel.parts or not candidate.is_file() or candidate.is_symlink():
            print("HOLD_MODEL_MANIFEST_PATH_OR_FILE=" + relative)
            return False
        if sha(candidate) != expected:
            print("HOLD_MODEL_SUBFILE_HASH=" + relative)
            return False
        count += 1
    print("MODEL=PASS_PINNED_FILES_NO_INFERENCE")
    print("MODEL_PATH=" + str(model))
    print("MODEL_FILES_VERIFIED=" + str(count))
    venvpy = stage / "venv" / "bin" / "python"
    print("MODEL_VENV=" + ("PRESENT_NOT_EXECUTED" if venvpy.is_file() else "ABSENT_OR_NON_POSIX"))
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path, help="ChatGPTCode directory")
    p.add_argument("--stage", type=Path, help="Optional original .provisioning directory")
    args = p.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        p.error("project root not found; no search performed")
    print("PULSE_SEARCH_REPLAY_ARTIFACT_RECOVERY_READ_ONLY=YES")
    print("INDEX_EXPECTED_RELATIVE=" + str(INDEX_REL))
    print("MODEL_STAGE_EXPECTED_NAME=" + STAGE_NAME)
    ok_index = verify_index(root / INDEX_REL)
    if not ok_index:
        print("INDEX=NOT_VERIFIED_AT_HISTORIC_PATH")
        # Only Pulse_Search dirs, not unrelated projects or browser profiles.
        count = 0
        for folder in root.glob("Pulse_Search_*"):
            if not folder.is_dir():
                continue
            for path in folder.rglob("*research_index*.sqlite"):
                count += 1
                if count > 60:
                    print("INDEX_ALTERNATE_SEARCH_CAPPED=60")
                    break
                if path.is_file() and not path.is_symlink() and verify_index(path):
                    ok_index = True
                    break
            if ok_index or count > 60:
                break
    stages = []
    if args.stage:
        stages.append(args.stage.resolve())
    stages.extend([Path.home() / STAGE_NAME, Path("/home/pulse") / STAGE_NAME])
    seen = set()
    ok_model = False
    for stage in stages:
        key = str(stage)
        if key in seen:
            continue
        seen.add(key)
        if verify_stage(stage):
            ok_model = True
            break
    if not ok_model:
        print("MODEL=NOT_VERIFIED_AT_HISTORIC_STAGE")
    print("INDEX_STATUS=" + ("PASS" if ok_index else "HOLD"))
    print("MODEL_STATUS=" + ("PASS_FILES_ONLY" if ok_model else "HOLD"))
    if ok_index and ok_model:
        print("RESULT=ARTIFACTS_FOUND_NOT_REPLAYED")
        return 0
    print("RESULT=HOLD_MISSING_HISTORICAL_ARTIFACTS")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print("HOLD_ARTIFACT_PROBE_ERROR=" + str(exc), file=sys.stderr)
        sys.exit(2)
