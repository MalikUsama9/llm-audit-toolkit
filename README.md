# llm-audit-toolkit

LLM evaluation and monitoring toolkit for auditing AI chatbots.

## Status
Work in progress. Built day by day.

- [x] Day 1: project setup, Pydantic models, provider-agnostic LLM client (retries, caching, cost logging), SQLite store, demo RAG bot
- [x] Day 2: test-set generator (chunking, grounded Q/A generation, edge cases, 120-case reviewed testset)
- [x] Day 3: targets and runner
- [x] Day 4: LLM judge and core evaluators (deterministic checks, rubrics)
- [x] Day 5: judge calibration (human agreement, kappa, position and verbosity bias tests), retrieval evaluators, midpoint checkpoint
- [ ] Day 6: regression comparison and cost/latency
- [ ] Day 7: dashboard
- [ ] Day 8: PDF audit report
- [ ] Day 9: case study, fixes, re-audit
- [ ] Day 10: packaging and demo

## Schedule check
Schedule check: on track. No cuts made. Judge calibration complete.

## Setup
1. `python -m venv .venv` and activate it
2. `pip install -e .`
3. Copy `.env.example` to `.env` and add your API key