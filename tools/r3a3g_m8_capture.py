"""Capture the M8 specific-page manifest through the reviewed fetcher.

Only title and meta description are retained. Each source must be explicitly
approved and carry a public-metadata/short-snippet rights class. A failed or
robots-denied source stays in the evidence as a failure, not as a silent pass.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.safe_fetch import Fetcher  # noqa: E402
from tools.r3a3g_capture_real_sources import capture  # noqa: E402

CONFIG = ROOT / "config/m8_sources.json"
OUT = ROOT / "docs/evidence/r3a3g_m8_source_snapshot.json"


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    fetcher = Fetcher(CrawlConfig(min_interval_s=3.0, timeout_s=20.0,
                                  max_bytes=600_000, max_redirects=3))
    pages = []
    for source in config["sources"]:
        record = capture(source, fetcher)
        pages.append({**source, **record})
        print(f"{record['status']:>3} {source['id']:<26} {record.get('title', '')[:64]}")
    payload = {
        "kind": "R3A3G_M8_SOURCE_SNAPSHOT",
        "schema": "pulse-search-m8-source-snapshot/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "CONTROLLED_SPECIFIC_PAGE_METADATA",
        "not_a_crawler_admission": True,
        "source_manifest": "config/m8_sources.json",
        "controls": {
            "ssrf_private_ip_guard": "pulse_search_crawler_r3a3f.netguard",
            "robots": "RFC9309-style, fail closed",
            "redirects": "same registrable domain, per-hop re-check",
            "pacing_s": 3.0,
            "rights": "public_metadata_and_short_snippet",
            "owner_approval_required": True,
        },
        "pages": pages,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
