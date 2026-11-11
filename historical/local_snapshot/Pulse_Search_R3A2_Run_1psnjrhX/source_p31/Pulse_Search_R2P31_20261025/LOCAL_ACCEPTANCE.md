# R2-P31 local verification summary

- 120-page owner database **not uploaded and not available locally**. Local preview reconstructs 118 known indexed URL/title records from owner reports; **not** full content or live search.
- Iteration 1: 36 historical queries (including 8 R2-P30 missing-recall cases) recovered expected metadata retrieval for 7/8; Council Tax property/home query initially missed because `property` and `home` were incorrectly treated as mandatory title tokens. Context-aware normalization corrected the miss.
- Iteration 2: 20 extra search phrasing probes: 16/20 initially met their URL/type expectations; four missed because `need`, `intro`, `registration`, `application` were used as unmatched subject anchors. Generic vocabulary aliases and intent-stopword fixes brought the 20/20 proxy retrieval expectations to pass.
- Current local proxy outcomes: prior 12/12 baseline shadow first results retained, 8/8 named-edition expected URLs #1, 6/6 paraphrases expected URL #1, 5/5 broad-discovery groups produce appropriate title/year/category candidates, 5/5 negative controls withhold, and 20/20 extra language probes meet metadata URL/type tests. **56 checks, not 56 factual answers**.
- Prior full engine regression suite: 285 passed. Prior R2-P29 suite: 20 passed. New R2-P31 unit classes: 10 passed (with 56 subcases).
- No network requests, no paid search APIs, no indexing, no production integration.
- **Owner acceptance pending** on the real unchanged 120-page index (SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`).
- No claim of near-100% factual accuracy, independent holdout performance, live availability verification, exact event scheduling or publisher reuse licences. Need new blind questions and additional source domains.
