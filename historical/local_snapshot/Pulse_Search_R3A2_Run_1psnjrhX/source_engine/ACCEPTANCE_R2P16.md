# R2-P16 Acceptance Gates

1. Outer ZIP and inner ZIP checksum pinned; every bundled source file SHA-256 verified before execution.
2. All 192 inherited tests remain passing; 21 R2-P16 tests (including year-control guard) pass locally.
3. Owner source DB must be the same reviewed City Hall research DB with **112 staged URLs**, one previously indexed London NYE 2026 page and matching source identity/policy. All three new exact URLs must already be in its sitemap candidates.
4. Dry-run opens source read-only, creates a separate usable SQLite backup, produces six query results, zero internet requests, zero changes to original DB and no paid-provider calls.
5. A live run requires explicit `PULSE_SEARCH_RUN_LIVE=1` and `PULSE_SEARCH_APPROVE_THREE_EVENT_PAGES=YES` in that invocation. It fetches at most 3 pre-reviewed event URLs via the existing native crawler, with depth 0, polite rate limit, source/robots/noindex enforcement; no general crawl.
6. Successful live coverage acceptance requires at least one **new** page indexed in the clone and searchable; partial outcomes reported precisely. The target is three, not promised.
7. No production API change or commercial-use approval; search results are ungraded until human assessment.
8. Owner WSL real-world results are required before claiming live milestone acceptance.
