# Day 4 notes

## 5.1 Metrics (separate, never one "quality score")
- Correctness: correct / partially_correct / incorrect (answerable cases)
- Hallucination: claim-level supported / contradicted / not_in_source;
  flag computed IN CODE: any(c.status != "supported")
- Refusal: appropriate_refusal / fabricated (unanswerable, off-topic)
- Over-refusal: wrongful_refusal (answerable cases)
- Errors (timeouts, empty) reported as their own row, never counted as "wrong"

## 5.2 Rubric rules
- Reference-guided (give reference answer + source excerpt)
- Claims first, verdict last
- Categorical labels with definitions + a borderline example
- Material claims only
- Quote evidence for each supported/contradicted claim
- One versioned file per metric in configs/rubrics/

## 5.3 Judge bias -> mitigation
- Verbosity -> "length is not quality"; check score vs answer length
- Self-preference -> judge from a different family than bot AND generator
- Leniency -> reference-guided, claim-level, temperature 0
- Inconsistency -> log judge model + rubric version; re-judge 10% sample
- Borderline -> escalate to a stronger model, then review myself

## Decisions
- Bot model family: gemini (gemini/gemini-3.5-flash-lite)
- Generator: gemini/gemini-3.1-flash-lite (family: gemini)
- Judge model: groq/openai/gpt-oss-120b (family: openai)
- Provider terms checked on: ______ result: ______
  - Commercial use: ______
  - Publishing/benchmarking results: ______
  - Data retention / training use: ______
- Estimated cost per judge pass: $0.039 (normal), $0.078 (pessimistic)   cap: $0.47 (normal), $0.93 (pessimistic)

## Cost estimate (date: 2026-11-11)
- Judge: groq/openai/gpt-oss-120b, $0.15 in / $0.60 out per 1M tokens (litellm reports the same price)
- Normal case (250 out tokens/case): $0.039 per pass, $0.23 for 6 passes, cap $0.47
- Pessimistic case (800 out tokens/case): $0.078 per pass, $0.47 for 6 passes, cap $0.93
- budget_usd in audit.yaml: 3.00 (judge), max_usd: 5.0 (audit)

## Budget guard
- LLMClient raises BudgetExceeded once spend reaches its budget; litellm knows the judge's price, so costs are counted
- Gap found: cli.py and qa_generator.py create LLMClient() with the default $5 cap, ignoring audit.yaml
- Fixed in cli.py build_target: LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.budget.max_usd)
- Still open: src/audit/qa_generator.py:85 uses LLMClient() with the default cap
- Config: added JudgeConfig + optional `judge` field in config.py; config loads, 45 tests pass

## Few-shot picks (dev cases only; split values in the DB are dev / heldout)
Run used: run_20261110_005907_b09fcd
- add-003: correct (direct_factual) - matches the reference, nothing added
- add-006: partially_correct (multi_hop) - right conclusion (surcharge applies) but omits the $19.95 amount; borderline example
- add-001: wrongful_refusal (direct_factual; correctness: incorrect) - answer is in the docs, bot refused
- unans-01: appropriate_refusal (unanswerable) - not in the docs, bot declined, nothing invented
- SYNTHETIC fabricated example (not from the bot): question from adv-02; made-up answer that invents a discount code. Mark as synthetic, do not count in stats.
- OPTIONAL hallucination example: add-004 (bot adds a "2:00 PM PT cutoff" the reference does not mention). Use only if verified as NOT in the docs.
- To verify against source_text: add-006 ("free Standard shipping on all US orders incl. Alaska and Hawaii"), add-004 (2:00 PM PT cutoff)

## Test-set issues found
- human-21 ("Do you have a store I can visit in person?"): labeled unanswerable, but the docs answer it (online only, no stores; same fact as gap-001). Bot answer is correct. Fix in data/demo/testset.jsonl (expected_behavior: answer + reference answer), not only in the DB.
- pick_fewshot.py filtered on 'holdout' but the DB uses 'heldout'; fixed with a replace on the script.
- Open decision: how to label "asks a clarifying question" (ambiguous cases amb-01, amb-02). Not an appropriate_refusal, not a fabrication; decide before writing refusal.yaml.

## Bot findings so far (for the report)
- Over-refusal on answerable dev cases: human-01, human-02 (partial), human-03, gap-028, add-001, hand-001 (6 of the dev answerable cases). Likely retrieval or prompt problem. Count again after judging.
- Fabrication: none found among dev unanswerable/off_topic/adversarial cases (heldout human-20 looks like one; do not look at heldout while tuning).