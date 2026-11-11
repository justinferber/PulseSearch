"""Content hashing, shingling and near-duplicate comparison."""

from __future__ import annotations

import hashlib
import re

WORD_RE = re.compile(r"[a-z0-9]+")
SHINGLE_SIZE = 5
MASK63 = (1 << 63) - 1  # SQLite INTEGER is signed 64-bit
MAX_SHINGLES = 400


def normalize_text(text: str) -> str:
    return " ".join(WORD_RE.findall((text or "").lower()))


def content_hash(title: str, text: str) -> str:
    return hashlib.sha256((normalize_text(title) + "\n" + normalize_text(text)).encode()).hexdigest()


def shingles(text: str, size: int = SHINGLE_SIZE, cap: int = MAX_SHINGLES) -> list[int]:
    words = WORD_RE.findall((text or "").lower())
    if len(words) < size:
        if not words:
            return []
        digest = hashlib.blake2b(" ".join(words).encode(), digest_size=8).digest()
        return [int.from_bytes(digest, "big") & MASK63]
    hashes: list[int] = []
    for i in range(len(words) - size + 1):
        chunk = " ".join(words[i:i + size]).encode()
        hashes.append(int.from_bytes(hashlib.blake2b(chunk, digest_size=8).digest(), "big") & MASK63)
        if len(hashes) >= cap:
            break
    return sorted(set(hashes))


def jaccard(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    return overlap / (len(a) + len(b) - overlap)


def boilerplate_ratio(text: str, boilerplate: str) -> float:
    """Share of the page's words that also appear in a known template."""
    page = set(normalize_text(text).split())
    if not page:
        return 1.0
    template = set(normalize_text(boilerplate).split())
    return len(page & template) / len(page)


def is_acceptable_text(text: str, min_chars: int) -> tuple[bool, str]:
    stripped = (text or "").strip()
    if len(stripped) < min_chars:
        return False, "thin_content"
    if len(stripped.split()) < 20:
        return False, "too_few_words"
    letters = sum(ch.isalpha() for ch in stripped)
    if letters / max(1, len(stripped)) < 0.45:
        return False, "low_text_signal"
    return True, "ok"


def snippet_from(text: str, limit: int = 320) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:limit]
