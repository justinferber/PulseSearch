"""Three-candidate source register: proposal state, never permission.

The owner selected three candidates (City Hall, London Parade, the Lord
Mayor's Show). Selection is not admission: every candidate here is a record
for review with `approved=false` and `index_allowed=false` until a written
owner decision says otherwise. The console renders this register so an
unreviewed host is never presented as crawled or indexed.
"""

from __future__ import annotations

import json
from pathlib import Path

# The four auditable states a candidate can be in. They are deliberately
# separate: "robots reviewed" is not "rights cleared", and neither is
# "owner approved".
CANDIDATE_STATES = ("candidate", "robots_reviewed", "rights_hold", "owner_approved")


def load_registry(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ValueError("source register must contain a 'sources' array")
    for source in data["sources"]:
        state = source.get("state", "candidate")
        if state not in CANDIDATE_STATES:
            raise ValueError(f"unknown candidate state {state!r}")
        if source.get("approved") or source.get("index_allowed"):
            # A register file can describe an approval, but only a written
            # owner decision may set one; refuse a register that presumes it.
            if not source.get("owner_authorisation"):
                raise ValueError(
                    f"{source.get('source_id')}: approved without an owner authorisation reference")
    return data


def candidate_rows(register: dict, staged_sources: dict | None = None) -> list[dict]:
    """Merge the proposal register with what an offline run actually staged."""
    staged_sources = staged_sources or {}
    rows: list[dict] = []
    for source in register.get("sources", []):
        source_id = source.get("source_id", "")
        staged = staged_sources.get(source.get("simulation_source_id") or source_id, {})
        rows.append({
            "source_id": source_id,
            "host": source.get("host", ""),
            "origin": source.get("origin", ""),
            "role": source.get("role", ""),
            "state": source.get("state", "candidate"),
            "approved": bool(source.get("approved")),
            "index_allowed": bool(source.get("index_allowed")),
            "rights_status": source.get("rights_status", "NOT_ASSESSED"),
            "allowed_paths": source.get("allowed_paths", []),
            "proposed_seeds": source.get("proposed_seeds", []),
            "owner_authorisation": source.get("owner_authorisation"),
            "owner_attestation": source.get("owner_attestation"),
            "organiser_approval_status": source.get("organiser_approval_status"),
            "reviewed_paths": source.get("reviewed_paths", []),
            "pilot_plan": source.get("pilot_plan"),
            "robots_status": source.get("robots", {}).get("status"),
            "terms_url": source.get("terms_url"),
            "contact": source.get("contact"),
            "pending": source.get("pending", []),
            # Offline simulation figures. They never make a real host crawled.
            "staged_documents": staged.get("documents", 0),
            "categories": staged.get("categories", {}),
            "categories_covered": staged.get("categories_covered", 0),
            "discovered_links": staged.get("discovered_links", 0),
            "deepest_depth": staged.get("deepest_depth", 0),
            "duplicates": staged.get("duplicates", 0),
            "novelty": staged.get("novelty"),
            "simulation_source_id": source.get("simulation_source_id"),
        })
    return rows


def register_block(register: dict | None, staged_sources: dict | None = None) -> dict:
    if not register:
        return {"status": "NOT_PROVIDED", "candidates": []}
    rows = candidate_rows(register, staged_sources)
    return {
        "status": register.get("status", "PROPOSAL_ONLY_NOT_ADMITTED"),
        "owner_decision": register.get("owner_decision", ""),
        "owner_scope_not_authorisation": register.get("owner_scope_not_authorisation", ""),
        "real_sources_admitted": sum(1 for row in rows if row["approved"] and row["state"] == "owner_approved"),
        "candidates": rows,
    }
