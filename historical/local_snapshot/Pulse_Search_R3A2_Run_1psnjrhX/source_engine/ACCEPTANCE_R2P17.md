# R2-P17 acceptance

**Locally tested**: Inherited R2-P16 crawler/index/API controls plus 16 additional source-safe research merging tests passed (229 total). This verifies fixtures and orchestration code only.

**Owner WSL acceptance pending**:

- Original R2-P16 four-page live database found with exactly 112 separate sitemap candidate URLs.
- Previously owner-reviewed R2-P12 `query_results.json` found via exact SHA256 results digest and its `index.sqlite` verified by page fingerprint.
- R2-P12 City Hall `/media-centre/` content explicitly skipped due to distinct R2-P16 City Hall `/events/` policy, with no implicit permission expansion.
- Additional approved, unique-origin R2-P12 pages imported with old metadata/source attribution preserved.
- SQLite `integrity_check` and FTS row counts pass, new report covers 19 research questions, all new top results presented for human review as required.
- Both input database SHA256s remain unchanged; no network calls, no paid search providers, no original DB writes.
- `OWNER_AUDIT_EXIT_CODE=0`; any mismatch HOLD is a correct refusal, not an accepted milestone.
