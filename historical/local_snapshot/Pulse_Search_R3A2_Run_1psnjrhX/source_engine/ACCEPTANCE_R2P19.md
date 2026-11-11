# Pulse Search R2-P19 acceptance

Local capability acceptance requires pinned source manifest and all inherited plus new tests PASS. Owner acceptance requires SHA-256 matches for the exact R2-P17 report (`170cc1618efac807ea47a294a1066aaa0ae1eaa632610f67438c368166633e7c`), original R2-P17 SQLite (`7a12e77fc5867fa27428023c30858f33488c5343c0e4a59a2d5455a721ef02ed`), and R2-P18 owner human review (`832ffd9fee092245155054c038bac93ca272b14a6402d67fb57b47b3a2fb94ca`).

The experimental results must retain 13 directly answering and two partly answering first results, suppress the one previously irrelevant current-stock match, and avoid counting any of the 12 novel questions as human-verified. Existing DB/report SHA checks must remain unchanged. Network and paid search call counters must remain zero.

HOLD is required if owner report/index not found, any SHA/permissions/review mismatch, incomplete review, regression of previously useful top-1 results, output already exists, database alteration, or unsuccessful tests.

This is an internal evidence-gathering milestone. Production API changes and public-commercial use are separately gated and are **not approved** by these results.
