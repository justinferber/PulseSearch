#!/usr/bin/env python3
"""R3-A3E experimental constraint layer over the accepted October engine.

NEW code. The accepted engine snapshots (`hybrid_core.py`, `semantic_ranker.py`,
`r3a_eval.py`, `r3a_cases.py`) are imported unmodified and are never rewritten.

Three confirmed defects are repaired *around* the engine, using only its public
`search()` surface:

1. Negative constraints. The original `EXCLUDE` regex has no `other than`
   alternative, so `Find London events in 2025 other than Diwali on the Square`
   parses with `excluded=[]` and the forbidden page is ranked (BGE rank 8).
2. Multi-year intent. `parse()` keeps one scalar year (the last found) and
   `_accept` hard-filters on it, so `2024 and 2025` keeps only 2025.
3. Series purity. `Past editions of London Open House` admits
   `City Hall Open House 2026`, which is a different series.

The layer decomposes the query (strip the exclusion clause, strip years), runs
the original ranker on the residue, optionally queries each requested year, then
enforces exclusion / year-set / subject-phrase constraints over *every* returned
rank and de-duplicates. Nothing is filtered by rank number, and no engine
threshold is relaxed to make a case pass.

Read-only. No network. No index writes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Extended negative-constraint surface. `other than` is the phrase that broke
# `exclude_diwali`; the rest are its ordinary siblings.
EXCLUDE_V2 = re.compile(
    r"\b(?:other\s+than|instead\s+of|excluding|except(?:\s+for)?|without|"
    r"apart\s+from|but\s+not|not\s+including|save\s+for)\b\s*([^?,;]+)",
    re.I,
)
SERIES_HINT = re.compile(r"\b(?:editions?|past|historical|previous|series|years?)\b", re.I)
GENERIC = ("festival", "celebration", "year")


def load_engine(snapshot: Path):
    """Import the original modules from the historical snapshot, unmodified."""
    root = snapshot / "Pulse_Search_R3A2R2_20261026"
    for sub in ("", "accepted_hybrid", "accepted_loader"):
        path = root / sub if sub else root
        if not path.is_dir():
            raise SystemExit("HOLD_MISSING_ENGINE_DIR=" + str(path))
        sys.path.insert(0, str(path))
    import hybrid_core  # noqa: E402

    return hybrid_core


def load_cases():
    """The original engineer-authored case sets: question, kind and expectation."""
    from r3a_cases import CASES
    from r3a2_extra_cases import CASES as EXTRA

    return {cid: (question, kind, expect) for cid, question, kind, expect in list(CASES) + list(EXTRA)}


class Decomposition:
    __slots__ = ("query", "clean_query", "exclusions", "years", "phrase", "series_like")

    def __init__(self, query, clean_query, exclusions, years, phrase, series_like):
        self.query = query
        self.clean_query = clean_query
        self.exclusions = exclusions
        self.years = years
        self.phrase = phrase
        self.series_like = series_like

    def as_dict(self):
        return {
            "query": self.query,
            "clean_query": self.clean_query,
            "exclusions": list(self.exclusions),
            "years": list(self.years),
            "subject_phrase": " ".join(self.phrase),
            "series_like": self.series_like,
        }


def decompose(hc, query: str) -> Decomposition:
    query = query or ""
    exclusions = tuple(m.group(1).strip() for m in EXCLUDE_V2.finditer(query))
    cleaned = EXCLUDE_V2.sub(" ", query)
    # Drop a dangling connective left behind by removing the excluded clause.
    cleaned = re.sub(r"\b(?:other\s+than|instead\s+of|apart\s+from|save\s+for)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;.?")

    years = tuple(dict.fromkeys(hc.YEAR.findall(query)))

    # Longest contiguous run of non-stopword, non-year query tokens. This is the
    # series subject ("london open house"), not a generic word like "events".
    best, run = [], []
    for token in hc.tokens(cleaned):
        if token in hc.STOP or hc.YEAR.fullmatch(token):
            run = []
            continue
        run = run + [token]
        if len(run) > len(best):
            best = list(run)
    phrase = tuple(hc.root(t) for t in best) if len(best) >= 2 else ()

    series_like = bool(SERIES_HINT.search(cleaned)) or len(years) > 1
    return Decomposition(query, cleaned or query, exclusions, years, phrase, series_like)


def _title_tokens(hc, title, url):
    # Rooted exactly like `important()`, so "St Patrick's" and "St Patrick" agree.
    return {hc.root(t) for t in hc.tokens(title or "") + hc.tokens(urlsplit(url).path.replace("-", " "))}


def _year_of(hc, title):
    found = hc.YEAR.findall(title or "")
    return found[-1] if found else None


def _contains_phrase(hc, title, phrase):
    stream = [hc.root(t) for t in hc.tokens(title or "")]
    n = len(phrase)
    return any(tuple(stream[i:i + n]) == phrase for i in range(len(stream) - n + 1))


class ConstrainedSearch:
    """Constraint-enforcing wrapper over one accepted ranker instance."""

    def __init__(self, hc, engine, label):
        self.hc = hc
        self.engine = engine
        self.label = label

    # -- constraint predicates -------------------------------------------------
    def excluded_hits(self, result, decomposition):
        title_tokens = _title_tokens(self.hc, result.get("title"), result["url"])
        hits = []
        for phrase in decomposition.exclusions:
            critical = [t for t in self.hc.important(phrase) if t not in GENERIC]
            if critical and all(t in title_tokens for t in critical):
                hits.append(phrase)
        return hits

    def violations(self, result, decomposition):
        found = []
        if decomposition.exclusions and self.excluded_hits(result, decomposition):
            found.append("EXCLUDED_ENTITY_PRESENT")
        if decomposition.years and _year_of(self.hc, result.get("title")) not in decomposition.years:
            found.append("YEAR_OUTSIDE_REQUESTED_SET")
        if decomposition.phrase and decomposition.series_like and not _contains_phrase(
            self.hc, result.get("title"), decomposition.phrase
        ):
            found.append("SERIES_SUBJECT_MISMATCH")
        return found

    # -- retrieval ------------------------------------------------------------
    def contradictory(self, decomposition):
        """`Eid on the Square 2027 excluding Eid` is a contradiction, not a filter.

        The original engine withholds these instead of inventing alternatives; the
        layer must not launder a withheld contradiction into a positive result.
        """
        if not decomposition.exclusions:
            return False
        clean = {t for t in self.hc.important(decomposition.clean_query) if t not in GENERIC}
        for phrase in decomposition.exclusions:
            critical = [t for t in self.hc.important(phrase) if t not in GENERIC]
            if critical and set(critical).issubset(clean):
                return True
        return False

    def search(self, query, limit=10):
        d = decompose(self.hc, query)
        if self.contradictory(d):
            return {
                "query": query,
                "label": self.label,
                "decomposition": d.as_dict(),
                "status": "WITHHELD_CONTRADICTORY_EXCLUSION",
                "results": [],
                "dropped": [],
                "constraint_compliance": "WITHHELD_CONTRADICTION",
                "candidate_pool": 0,
            }
        depth = max(limit, 10)
        pool = list(self.engine.search(d.clean_query, limit=depth)["results"])

        # Last-resort retrieval for exclusion-only phrasing. `London 2027 public
        # events excluding Eid` strips to a verbless phrase, which the original
        # parser treats as a subject query and answers with nothing. Ask again
        # with an explicit discovery verb, then apply the same constraints; the
        # constraints, not the retry, decide what is returned.
        if not pool and d.exclusions and d.clean_query:
            try:
                pool = list(self.engine.search("show " + d.clean_query, limit=depth)["results"])
            except Exception:  # noqa: BLE001 - never let a fallback hide the empty primary
                pool = []

        # Per-year decomposition: guarantees each requested edition is actually
        # retrieved rather than depending on one merged ranking.
        if len(d.years) > 1:
            subject = " ".join(d.phrase) if d.phrase else d.clean_query
            for year in d.years:
                try:
                    pool.extend(self.engine.search(f"{subject} {year}", limit=depth)["results"])
                except Exception:  # noqa: BLE001 - a failed sub-query must not mask the primary
                    continue

        seen, merged = set(), []
        for result in pool:
            url = result["url"]
            if url in seen:
                continue
            seen.add(url)
            merged.append(result)

        kept, dropped = [], []
        for result in merged:
            bad = self.violations(result, d)
            if bad:
                dropped.append({"url": result["url"], "title": result.get("title"), "violations": bad})
            else:
                kept.append(result)

        return {
            "query": query,
            "label": self.label,
            "decomposition": d.as_dict(),
            "status": "RETRIEVAL_CANDIDATES_UNVERIFIED" if kept else "WITHHELD_NO_GROUNDED_INDEX_RESULT",
            "results": kept[:limit],
            "dropped": dropped,
            "constraint_compliance": "ALL_RETURNED_RANKS_PASS" if kept else "EMPTY_AFTER_CONSTRAINTS",
            "candidate_pool": len(merged),
        }


def read_rows(index: Path):
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows = [
            dict(r)
            for r in db.execute(
                """select p.url,p.title,p.body,p.fetched_at,p.source_id,s.display_mode
                   from pages p join sources s using(source_id)
                   where p.indexed=1 and s.approved=1 and s.enabled=1 order by p.url"""
            )
        ]
    if len(rows) != 120:
        raise SystemExit("HOLD_APPROVED_COUNT_DRIFT=" + str(len(rows)))
    return rows


def verdict(kind, expect, returned):
    from r3a_eval import check_output

    verdict_text, note = check_output(kind, expect, returned)
    return verdict_text, note


def run(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--frozen", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", help="comma-separated probe ids for a focused run")
    ap.add_argument("--dense", action="store_true",
                    help="measure the pinned BGE dense ranker instead of the hybrid baseline")
    ap.add_argument("--model-dir", type=Path, help="pinned BGE stage directory (with --dense)")
    args = ap.parse_args(argv)

    hc = load_engine(args.snapshot)
    rows = read_rows(args.index)
    if args.dense:
        if args.model_dir is None:
            raise SystemExit("HOLD_DENSE_REQUIRES_MODEL_DIR")
        from semantic_ranker import DenseConstrainedIndex
        from r3a_local_model import PinnedSentenceEncoder

        encoder = PinnedSentenceEncoder(args.model_dir)
        base = DenseConstrainedIndex(rows, encoder)
        label, engine_name = "bge_dense_constrained", "BGE_DENSE_PINNED"
    else:
        from hybrid_core import HybridIndex

        base = HybridIndex(rows)
        label, engine_name = "hybrid_constrained", "HYBRID_LEXICAL"
    layer = ConstrainedSearch(hc, base, label)

    cases = load_cases()
    frozen = list(csv.DictReader(args.frozen.open(newline="", encoding="utf-8")))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        frozen = [q for q in frozen if q["probe_id"] in wanted]

    probes, changed = [], []
    for q in frozen:
        question, kind, expect = cases[q["probe_id"]]
        before_raw = base.search(question, limit=10)
        after_raw = layer.search(question, limit=10)
        before, before_note = verdict(kind, expect, before_raw["results"])
        after, after_note = verdict(kind, expect, after_raw["results"])
        entry = {
            "probe_id": q["probe_id"],
            "question": question,
            "expected_kind": kind,
            "expected_value": expect,
            "before": {"verdict": before, "note": before_note, "count": len(before_raw["results"]),
                       "urls": [r["url"] for r in before_raw["results"]]},
            "after": {"verdict": after, "note": after_note, "count": len(after_raw["results"]),
                      "urls": [r["url"] for r in after_raw["results"]]},
            "decomposition": after_raw["decomposition"],
            "constraint_compliance": after_raw["constraint_compliance"],
            "dropped": after_raw["dropped"],
        }
        probes.append(entry)
        if before != after:
            changed.append({"probe_id": q["probe_id"], "before": before, "after": after})

    def tally(key):
        out = {}
        for p in probes:
            v = p[key]["verdict"]
            out[v] = out.get(v, 0) + 1
        return out

    before_tally, after_tally = tally("before"), tally("after")
    newly_fixed = [c["probe_id"] for c in changed
                   if c["before"].startswith("FAIL") and not c["after"].startswith("FAIL")]
    regressions = [c["probe_id"] for c in changed
                   if not c["before"].startswith("FAIL") and c["after"].startswith("FAIL")]
    report = {
        "kind": "R3A3E_CONSTRAINT_LAYER_MEASUREMENT_NOT_ACCEPTED_ENGINE",
        "engine": engine_name,
        "engine_snapshots_modified": False,
        "probe_count": len(probes),
        "before_distribution": before_tally,
        "after_distribution": after_tally,
        "newly_passing": newly_fixed,
        "regressions": regressions,
        "changed": changed,
        "probes": probes,
        "limitations": [
            "Hybrid lexical path only in this file; dense path measured separately.",
            "Engineer-authored expectations are not independent human relevance labels.",
            "Constraint compliance is a rule check, not proof of user-visible quality.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "probe_count": report["probe_count"],
        "before": before_tally,
        "after": after_tally,
        "newly_passing": newly_fixed,
        "regressions": regressions,
        "out": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
