#!/usr/bin/env python3
"""Safely stage ORIGINAL Pulse Search Python/Markdown source as historical snapshots.

Defaults to read-only dry-run. --apply copies verified files into the independent
PulseSearch *working tree*; it never changes the owner originals, invokes the
crawler, fetches networks, starts services, or performs Git commits/pushes.
The pinned inventory is docs/evidence_inventory.json in the existing Git repo.

Usage:
  python3 tools/stage_historical_source.py --root /mnt/c/.../ChatGPTCode --repo /path/to/PulseSearch
  python3 tools/stage_historical_source.py --root /mnt/c/.../ChatGPTCode --repo /path/to/PulseSearch --apply

Inspect the copied code manually for confidentiality/licensing before git add/commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

EXPECTED_BRANCH = "fb2/r3-a3c-frozen54-replay-and-history-20261111"
SNAPSHOT_PREFIX = "historical/local_snapshot"
SOURCE_PREFIXES = (
    "Pulse_Search_R3A2_Run_1psnjrhX/source_engine/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_p29/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_p31/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_p32/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_p33/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_p34/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_r2p35/",
    "Pulse_Search_R3A2_Run_1psnjrhX/source_r3a1/",
    "Pulse_Search_R3A2R2_20261026/",
)
ALLOWED_SUFFIXES = {".py", ".md"}
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 15_000_000
SENSITIVE = (
    re.compile(rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
)


def fatal(message: str) -> None:
    raise ValueError(message)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)

    root, repo = args.root.resolve(), args.repo.resolve()
    if not root.is_dir() or not repo.is_dir():
        fatal("source root or PulseSearch worktree directory absent")
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        fatal("target must be top-level PulseSearch Git worktree")
    branch = git(repo, "branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        fatal(f"expected isolated branch {EXPECTED_BRANCH}, actual {branch!r}")
    if args.apply and git(repo, "status", "--porcelain"):
        fatal("worktree is not clean; review existing changes before --apply")

    inventory_file = repo / "docs" / "evidence_inventory.json"
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    candidates = [
        (rel, record)
        for rel, record in inventory["files"].items()
        if rel.startswith(SOURCE_PREFIXES)
        and Path(rel).suffix.lower() in ALLOWED_SUFFIXES
        and record.get("publish") is True
    ]
    if not candidates:
        fatal("no eligible source in pinned evidence inventory")

    files = []
    payloads = []
    sizes = 0
    families = Counter()
    for rel, record in sorted(candidates):
        src = root / rel
        if not src.is_file() or src.is_symlink():
            fatal(f"missing or linked source: {rel}")
        if not src.resolve().is_relative_to(root):
            fatal(f"source escapes declared root: {rel}")
        raw = src.read_bytes()
        sizes += len(raw)
        if len(raw) > MAX_FILE_BYTES or sizes > MAX_TOTAL_BYTES:
            fatal(f"file/total cap exceeded: {rel}")
        digest = sha256(raw)
        if digest != record["sha256"] or len(raw) != record["bytes"]:
            fatal(f"pinned hash/size mismatch: {rel}")
        if any(pattern.search(raw) for pattern in SENSITIVE):
            fatal(f"potential credential material: {rel}")
        destination = (repo / SNAPSHOT_PREFIX / rel)
        if destination.exists() and (
            not destination.is_file() or sha256(destination.read_bytes()) != digest
        ):
            fatal(f"destination already differs from pinned source: {destination}")
        families[rel.split("/")[1]] += 1
        files.append({"source_relative_path": rel,
                      "git_relative_path": f"{SNAPSHOT_PREFIX}/{rel}",
                      "sha256": digest, "bytes": len(raw)})
        payloads.append((destination, raw))
    manifest = {
        "kind": "PulseSearch historical snapshot import; NOT original Git ancestry",
        "source": "owner Windows ChatGPTCode folder (read-only)",
        "pinned_evidence": "docs/evidence_inventory.json @ recovery commit 608cfd679b564f69af81d0f80229c2375f37ef7e",
        "file_count": len(files),
        "total_bytes": sizes,
        "files": files,
    }
    manifest_dest = repo / "historical" / "SOURCE_IMPORT_MANIFEST_20261111.json"
    manifest_data = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    if manifest_dest.exists() and manifest_dest.read_bytes() != manifest_data:
        fatal("manifest already exists but differs; no overwrite")

    print(f"STATUS=VERIFIED MODE={'APPLY' if args.apply else 'DRY_RUN'}")
    print(f"COUNT={len(files)} BYTES={sizes}")
    for family, n in sorted(families.items()):
        print(f"FAMILY {family}: {n}")
    print(f"TARGET={SNAPSHOT_PREFIX}")
    print("NOTE: historical snapshots, not proof of API operation or independent grading")
    if args.apply:
        for destination, raw in payloads:
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(raw)
        manifest_dest.parent.mkdir(parents=True, exist_ok=True)
        if not manifest_dest.exists():
            with manifest_dest.open("xb") as handle:
                handle.write(manifest_data)
        print("STAGED_IN_WORKTREE=YES")
        print("NEXT=review confidentiality/licences; git diff --no-index or inspect files; then git add/commit")
    else:
        print("STAGED_IN_WORKTREE=NO (use --apply after review)")
    print("ORIGINAL_SOURCE_MODIFIED=NO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        sys.exit(2)
