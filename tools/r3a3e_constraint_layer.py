#!/usr/bin/env python3
"""R3-A3E candidate constraint layer over the accepted October engine.

NEW code. The accepted engine snapshots (`hybrid_core.py`, `semantic_ranker.py`,
`r3a_eval.py`, `r3a_cases.py`) are imported unmodified and are never rewritten.

Scope note (owner clarification, 11 November 2026): the negative constraints here
are **query-local negation**. They filter the results of the *one request* that
explicitly asked for a negative. They never touch index content, source
admission, crawler settings, event qualification, permanent blocklists or
category visibility, and no state survives the call. `Diwali events`,
`Pride Berlin events`, `CSD Berlin` and `Stadtfest Berlin` must keep retrieving
their indexed editions; only a query that says `other than Diwali` may omit the
named entity, and only for that query.

Three confirmed defects are repaired *around* the engine, using only its public
`search()` surface:

1. Negative constraints. The original `EXCLUDE` regex has no `other than`
   alternative, so `Find London events in 2025 other than Diwali on the Square`
   parses with `excluded=[]` and the forbidden page is ranked (BGE rank 8).
2. Multi-year intent. `parse()` keeps one scalar year (the last found) and
   `_accept` hard-filters on it, so `2024 and 2025` keeps only 2025.
3. Series purity. `Past editions of London Open House` admits
   `City Hall Open House 2026`, which is a different series.

Review hardening (PR #8):

* The accepted owner index is SHA-256 pinned before *and* after the read, and the
  dense model manifest/weights are pinned, so no run can silently use a
  substitute corpus. Row count is a secondary check, never the gate.
* Coordinated negations (`excluding Diwali and Pride`, `other than A, B and C`)
  are split into separate entities; each is tested on its own.
* Retrieval escalates depth when constraints remove candidates, so a request for
  `limit` results is refilled from deeper ranks instead of returning a short list.
* Per-year sub-queries record `RETRIEVED` / `EMPTY` / `FAILED`; any failure makes
  `retrieval_status = PARTIAL_SUBQUERY_FAILED` and incomplete coverage is never
  reported as complete.

Read-only. No network. No index writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

INDEX_PIN = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
MODEL_MANIFEST_SHA = "3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437"
WEIGHTS_SHA = "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"
WEIGHTS_BYTES = 133466304
CORPUS_MAX_DEPTH = 120

# Extended negative-constraint surface. `other than` is the phrase that broke
# `exclude_diwali`; the rest are its ordinary siblings.
EXCLUDE_V2 = re.compile(
    r"\b(?:other\s+than|instead\s+of|excluding|except(?:\s+for)?|without|"
    r"apart\s+from|but\s+not|not\s+including|save\s+for)\b\s*([^?;]+)",
    re.I,
)
# Coordinated entities inside one negation clause. Split on commas, ampersands
# and the conjunctions, so `excluding Diwali and Pride` is two constraints.
COORD = re.compile(r"\s*(?:,|&|\+|\band\b|\bor\b)\s*", re.I)
TRAILING_SCOPE = re.compile(
    r"\s+\b(?:in|for|from|at|on|during|with|across)\b\s+\d{4}\b.*$", re.I
)
SERIES_HINT = re.compile(r"\b(?:editions?|past|historical|previous|series|years?)\b", re.I)
GENERIC = ("festival", "celebration", "year")


# --------------------------------------------------------------------------- #
# Fail-closed integrity gates
# --------------------------------------------------------------------------- #
def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_pin(path, expected: str, label: str) -> str:
    """Fail closed on a missing file or a hash that is not the pinned value."""
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"HOLD_{label}_ABSENT={path}")
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(f"HOLD_{label}_SHA_MISMATCH=expected:{expected}:actual:{actual}")
    return actual


def verify_model_pin(model_dir) -> dict:
    """Dense mode may not run against an unpinned or substituted BGE stage."""
    model_dir = Path(model_dir)
    manifest = verify_pin(model_dir / "PULSE_APPROVED_MODEL.sha256", MODEL_MANIFEST_SHA,
                          "MODEL_MANIFEST")
    weights = model_dir / "model.safetensors"
    if not weights.is_file():
        raise SystemExit("HOLD_MODEL_WEIGHT_ABSENT=" + str(weights))
    if weights.stat().st_size != WEIGHTS_BYTES:
        raise SystemExit("HOLD_MODEL_WEIGHT_SIZE_MISMATCH=" + str(weights.stat().st_size))
    weight_sha = sha256_file(weights)
    if weight_sha != WEIGHTS_SHA:
        raise SystemExit("HOLD_MODEL_WEIGHT_SHA_MISMATCH=" + weight_sha)
    return {
        "manifest_sha256": manifest,
        "weights_sha256": weight_sha,
        "weights_bytes": WEIGHTS_BYTES,
        "pin_verified": True,
    }


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


# --------------------------------------------------------------------------- #
# Decomposition
# --------------------------------------------------------------------------- #
def split_entities(clause: str):
    """Split one negation clause into the separate entities it names.

    `Diwali and Pride` -> two constraints. `Diwali on the Square` stays whole,
    because a bare conjunction is the only separator. Trailing scope phrases
    such as `in 2025` are dropped: they bound the search, not the entity.
    """
    entities = []
    for part in COORD.split(clause or ""):
        part = TRAILING_SCOPE.sub("", part).strip(" .'\"")
        if not part or len(part) < 3:
            continue
        if re.fullmatch(r"\d{4}", part):
            continue
        entities.append(part)
    return entities


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
            "exclusion_scope": "QUERY_LOCAL_NEGATION",
        }


def decompose(hc, query: str) -> Decomposition:
    query = query or ""
    exclusions = []
    for match in EXCLUDE_V2.finditer(query):
        exclusions.extend(split_entities(match.group(1)))
    exclusions = tuple(dict.fromkeys(exclusions))
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


# --------------------------------------------------------------------------- #
# Constraint-enforcing wrapper
# --------------------------------------------------------------------------- #
METRICS_SCOPE = {
    "exclusion_semantics": "QUERY_LOCAL_NEGATION_ONLY",
    "global_event_suppression": False,
    "persisted_state": False,
    "index_or_source_mutation": False,
    "retrieval_metric": "ENGINE_RANKING_WITH_CONSTRAINTS",
    "relevance_metric": "ENGINEER_AUTHORED_URL_EXPECTATION_NOT_HUMAN_GRADE",
    "human_signed_grades": 0,
}


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

    # -- retrieval ------------------------------------------------------------
    @staticmethod
    def _depths(limit):
        plan = [max(limit, 10)]
        for depth in (50, CORPUS_MAX_DEPTH):
            if depth > plan[-1]:
                plan.append(depth)
        return plan

    def _collect(self, decomposition, depth, merged, diagnostics, year_state):
        """One retrieval pass at `depth`, merged by URL. Never raises."""
        try:
            raw = self.engine.search(decomposition.clean_query, limit=depth)
            pool = list(raw["results"])
            diagnostics.append({"stage": "primary", "query": decomposition.clean_query,
                                "depth": depth, "status": "OK", "returned": len(pool)})
        except Exception as ex:  # noqa: BLE001 - a failure must be recorded, not hidden
            pool = []
            diagnostics.append({"stage": "primary", "query": decomposition.clean_query,
                                "depth": depth, "status": "FAILED",
                                "error": type(ex).__name__ + ": " + str(ex)})

        # Last-resort retrieval for exclusion-only phrasing. `London 2027 public
        # events excluding Eid` strips to a verbless phrase, which the original
        # parser treats as a subject query and answers with nothing. Ask again
        # with an explicit discovery verb, then apply the same constraints; the
        # constraints, not the retry, decide what is returned.
        if not pool and decomposition.exclusions and decomposition.clean_query:
            try:
                pool = list(self.engine.search("show " + decomposition.clean_query, limit=depth)["results"])
                diagnostics.append({"stage": "fallback", "query": "show " + decomposition.clean_query,
                                    "depth": depth, "status": "OK", "returned": len(pool)})
            except Exception as ex:  # noqa: BLE001
                diagnostics.append({"stage": "fallback", "query": "show " + decomposition.clean_query,
                                    "depth": depth, "status": "FAILED",
                                    "error": type(ex).__name__ + ": " + str(ex)})

        for result in pool:
            merged.setdefault(result["url"], result)

        if len(decomposition.years) > 1:
            subject = " ".join(decomposition.phrase) if decomposition.phrase else decomposition.clean_query
            for year in decomposition.years:
                query = f"{subject} {year}"
                try:
                    found = list(self.engine.search(query, limit=depth)["results"])
                    status = "RETRIEVED" if found else "EMPTY"
                    diagnostics.append({"stage": "year", "year": year, "query": query,
                                        "depth": depth, "status": status, "returned": len(found)})
                except Exception as ex:  # noqa: BLE001
                    found, status = [], "FAILED"
                    diagnostics.append({"stage": "year", "year": year, "query": query,
                                        "depth": depth, "status": "FAILED",
                                        "error": type(ex).__name__ + ": " + str(ex)})
                previous = year_state.get(year, {})
                # A failure at any depth is sticky: partial coverage is never
                # upgraded to complete by a later successful shallow retry.
                if previous.get("status") == "FAILED":
                    status = "FAILED"
                year_state[year] = {
                    "status": status,
                    "returned": max(previous.get("returned", 0), len(found)),
                    "depth": depth,
                }
                for result in found:
                    merged.setdefault(result["url"], result)

    def _filter(self, decomposition, merged):
        kept, dropped = [], []
        for result in merged.values():
            bad = self.violations(result, decomposition)
            if bad:
                dropped.append({"url": result["url"], "title": result.get("title"), "violations": bad})
            else:
                kept.append(result)
        return kept, dropped

    def search(self, query, limit=10):
        decomposition = decompose(self.hc, query)
        if self.contradictory(decomposition):
            return {
                "query": query,
                "label": self.label,
                "decomposition": decomposition.as_dict(),
                "status": "WITHHELD_CONTRADICTORY_EXCLUSION",
                "retrieval_status": "WITHHELD",
                "results": [],
                "dropped": [],
                "constraint_compliance": "WITHHELD_CONTRADICTION",
                "candidate_pool": 0,
                "eligible_pool": 0,
                "refilled": False,
                "search_passes": [],
                "year_coverage": {},
                "diagnostics": [],
                "metrics_scope": dict(METRICS_SCOPE),
            }

        merged = {}
        diagnostics = []
        year_state = {}
        passes = []
        kept = []
        for depth in self._depths(limit):
            self._collect(decomposition, depth, merged, diagnostics, year_state)
            kept, dropped = self._filter(decomposition, merged)
            passes.append({"depth": depth, "candidate_pool": len(merged), "eligible": len(kept)})
            if len(kept) >= limit:
                break

        failed = any(d["status"] == "FAILED" for d in diagnostics)
        return {
            "query": query,
            "label": self.label,
            "decomposition": decomposition.as_dict(),
            "status": "RETRIEVAL_CANDIDATES_UNVERIFIED" if kept else "WITHHELD_NO_GROUNDED_INDEX_RESULT",
            "retrieval_status": "PARTIAL_SUBQUERY_FAILED" if failed else "COMPLETE",
            "results": kept[:limit],
            "dropped": dropped,
            "constraint_compliance": "ALL_RETURNED_RANKS_PASS" if kept else "EMPTY_AFTER_CONSTRAINTS",
            "candidate_pool": len(merged),
            "eligible_pool": len(kept),
            "refilled": len(passes) > 1,
            "search_passes": passes,
            "year_coverage": year_state,
            "diagnostics": diagnostics,
            "metrics_scope": dict(METRICS_SCOPE),
        }


def read_rows(index: Path, expected_pin=INDEX_PIN):
    """Read the approved corpus read-only, pinned before and after.

    `expected_pin=None` is for fixtures only: the receipt then records that the
    pin was not enforced, so an unpinned read can never be mistaken for a
    verified one.
    """
    import sqlite3
    from contextlib import closing

    index = Path(index)
    if not index.is_file():
        raise SystemExit("HOLD_OWNER_INDEX_ABSENT=" + str(index))
    before = verify_pin(index, expected_pin, "OWNER_INDEX") if expected_pin else sha256_file(index)
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
    after = sha256_file(index)
    if before != after:
        raise SystemExit(f"HOLD_OWNER_INDEX_CHANGED_DURING_READ=before:{before}:after:{after}")
    if len(rows) != 120:
        raise SystemExit("HOLD_APPROVED_COUNT_DRIFT=" + str(len(rows)))
    return rows, {
        "sha256_before": before,
        "sha256_after": after,
        "pin_enforced": expected_pin is not None,
        "approved_rows": len(rows),
    }


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
    ap.add_argument("--comparison-out", type=Path,
                    help="separate candidate-vs-historical comparison set (never replaces the baseline)")
    ap.add_argument("--only", help="comma-separated probe ids for a focused run")
    ap.add_argument("--dense", action="store_true",
                    help="measure the pinned BGE dense ranker instead of the hybrid baseline")
    ap.add_argument("--model-dir", type=Path, help="pinned BGE stage directory (with --dense)")
    args = ap.parse_args(argv)
    # Fail fast on argument errors before touching the pinned corpus.
    if args.dense and args.model_dir is None:
        raise SystemExit("HOLD_DENSE_REQUIRES_MODEL_DIR")

    hc = load_engine(args.snapshot)
    rows, index_receipt = read_rows(args.index)
    model_receipt = None
    if args.dense:
        model_receipt = verify_model_pin(args.model_dir)
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
            "retrieval_status": after_raw["retrieval_status"],
            "year_coverage": after_raw["year_coverage"],
            "refilled": after_raw["refilled"],
            "search_passes": after_raw["search_passes"],
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
        "index_integrity": index_receipt,
        "model_integrity": model_receipt,
        "exclusion_semantics": "QUERY_LOCAL_NEGATION_ONLY",
        "probe_count": len(probes),
        "before_distribution": before_tally,
        "after_distribution": after_tally,
        "newly_passing": newly_fixed,
        "regressions": regressions,
        # A withheld contradiction is a decision, not a degraded retrieval.
        "partial_retrieval_probes": [p["probe_id"] for p in probes
                                     if p["retrieval_status"] == "PARTIAL_SUBQUERY_FAILED"],
        "metrics_scope": dict(METRICS_SCOPE),
        "changed": changed,
        "probes": probes,
        "limitations": [
            "Engineer-authored URL expectations are not independent human relevance labels.",
            "Constraint compliance is a rule check, not proof of user-visible quality.",
            "No metric in this file may be reported as a relevance score.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.comparison_out:
        comparison = {
            "kind": "R3A3E_CANDIDATE_RANKING_COMPARISON_NOT_HISTORICAL_BASELINE",
            "warning": ("Candidate output for comparison only. The historical grading baseline "
                        "remains docs/evidence/r3a3d_frozen54_replay.json and must not be "
                        "replaced, overwritten or re-scored from this file."),
            "baseline_source": "docs/evidence/r3a3d_frozen54_replay.json",
            "candidate_engine": engine_name,
            "human_signed_grades": 0,
            "probes": [
                {
                    "probe_id": p["probe_id"],
                    "question": p["question"],
                    "historical_baseline_urls": p["before"]["urls"],
                    "candidate_urls": p["after"]["urls"],
                    "constraint_compliance": p["constraint_compliance"],
                    "retrieval_status": p["retrieval_status"],
                }
                for p in probes
            ],
        }
        args.comparison_out.parent.mkdir(parents=True, exist_ok=True)
        args.comparison_out.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")

    print(json.dumps({
        "probe_count": report["probe_count"],
        "before": before_tally,
        "after": after_tally,
        "newly_passing": newly_fixed,
        "regressions": regressions,
        "partial_retrieval_probes": report["partial_retrieval_probes"],
        "index_pin_enforced": index_receipt["pin_enforced"],
        "out": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
