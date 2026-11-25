# Secrets scan

- Date: 2026-11-25
- Tool: gitleaks 8.30.1
- History scan (all branches, 105 commits): 0 findings
- Working tree scan: 3 findings, all in the untracked local `.env` (expected, never committed). Other hits were third-party packages inside `.venv` (false positives, not part of the repo)
- `.env` history check: never committed
- Manual search for key prefixes in history (`AIza`, `gsk_`): no keys. One match was a scrubber regex in `scripts/make_demo_db.py`, not a key
- Tracked .db files: demo database only (`data/demo/demo.db`), fictional Tidewell data, no key strings
- Keys rotated / history rewritten: none needed
