# llm-audit-toolkit

LLM evaluation and monitoring toolkit for auditing AI chatbots.

## Status
Work in progress. Built day by day.

- [x] Day 1: project setup, Pydantic models, provider-agnostic LLM client (retries, caching, cost logging), SQLite store, demo RAG bot
- [ ] Day 2: test-set generator
- [ ] Day 3: runner and judge
- [ ] Day 4: deterministic checks

## Setup
1. `python -m venv .venv` and activate it
2. `pip install -e .`
3. Copy `.env.example` to `.env` and add your API key