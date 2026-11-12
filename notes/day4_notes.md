# Day 4 notes: judge and core evaluators

Run used: run_20261110_005907_b09fcd
Judge: groq/openai/gpt-oss-120b | temperature: ____ | max_tokens: ____ | rubric version: ____

---

## End-of-day checklist (fill in before committing)

- [ ] Judge output parses reliably, with retry on malformed JSON
  - judge_failure count: ____ of ____ cases (____%)
  - Retry uses `use_cache=False` on the second attempt: yes / no
- [ ] Judge temperature is low and settings are logged
  - Judge model, temperature, max_tokens and rubric version are stored in the run's config snapshot: yes / no
- [ ] I read at least 20 judgments and noted where the judge seems wrong (see "Judge errors" below)
  - Judgments read: ____
- [ ] Every case has a score row, or is marked `error` / `judge_failure`. Errors are not counted as "wrong".
- [ ] `.env`, `*.db` and `data/clients/` are gitignored, and `git status` shows no secrets
- [ ] `pytest` passes (last run: 45 tests passed; re-run after today's changes)

---

## Judge errors found (for Day 5)

Read ____ judgments, sampled across categories (include incorrect / fabricated, correct on numeric cases, refusals, adversarial, partially_correct).
Classify each disagreement as one of: **rubric ambiguity**, **wrong reference / test case**, **real judge error**.

Summary:
- Agreed with the judge: ____ of ____
- Rubric ambiguity: ____ | Wrong reference or test case: ____ | Real judge error: ____

| case_id | category | judge said | I think | type | note |
|---|---|---|---|---|---|
| human-21 | unanswerable (as labeled) | (fill in) | answerable | wrong test case | Docs say online only, no stores (same fact as gap-001). Bot answer is correct. Fix in `data/demo/testset.jsonl`. |
| | | | | | |
| | | | | | |

Patterns to investigate on Day 5:
- Is the judge lenient on numeric details? (check on the human-labeled set)
- Does score correlate with answer length?
- How does the judge treat "asks a clarifying question" answers? (see open decision below)
- ____

Note: the cases I read today were not labeled blind, because I saw the judge's verdict first. For Day 5 calibration, draw a **fresh random sample of ~40** and label it blind. Also exclude the 5 few-shot cases below.

---

## 5.1 Metrics (separate, never one "quality score")
- Correctness: correct / partially_correct / incorrect (answerable cases)
- Hallucination: claim-level supported / contradicted / not_in_source;
  flag computed IN CODE: `any(c.status != "supported")`
- Refusal: appropriate_refusal / fabricated (unanswerable, off-topic)
- Over-refusal: wrongful_refusal (answerable cases)
- Errors (timeouts, empty) reported as their own row, never counted as "wrong"

## 5.2 Rubric rules
- Reference-guided (give reference answer + source excerpt)
- Claims first, verdict last
- Categorical labels with definitions + a borderline example
- Material claims only
- Quote evidence for each supported/contradicted claim
- One versioned file per metric in `configs/rubrics/`

## 5.3 Judge bias -> mitigation
- Verbosity -> "length is not quality"; check score vs answer length
- Self-preference -> judge from a different family than bot AND generator
- Leniency -> reference-guided, claim-level, temperature 0
- Inconsistency -> log judge model + rubric version; re-judge 10% sample
- Borderline -> escalate to a stronger model, then review myself

---

## Decisions
- Bot model family: gemini (gemini/gemini-3.5-flash-lite)
- Generator: gemini/gemini-3.1-flash-lite (family: gemini)
- Judge model: groq/openai/gpt-oss-120b (family: openai). Different family from bot and generator, so self-preference risk is reduced.
- Provider terms checked on: ______ result: ______
  - Commercial use: ______
  - Publishing/benchmarking results: ______
  - Data retention / training use: ______
  - **TODO before publishing any results:** these three lines are still blank.
- Estimated cost per judge pass: $0.039 (normal), $0.078 (pessimistic); cap: $0.47 (normal), $0.93 (pessimistic)

## Cost estimate (date: 2026-11-11)
- Judge: groq/openai/gpt-oss-120b, $0.15 in / $0.60 out per 1M tokens (litellm reports the same price)
- Normal case (250 out tokens/case): $0.039 per pass, $0.23 for 6 passes, cap $0.47
- Pessimistic case (800 out tokens/case): $0.078 per pass, $0.47 for 6 passes, cap $0.93
- `budget_usd` in audit.yaml: 3.00 (judge), `max_usd`: 5.0 (audit)
- Actual spend so far: $____ (compare with the estimate after the first full judge pass)

## Budget guard
- LLMClient raises BudgetExceeded once spend reaches its budget; litellm knows the judge's price, so costs are counted
- Gap found: `cli.py` and `qa_generator.py` create `LLMClient()` with the default $5 cap, ignoring audit.yaml
- Fixed in `cli.py` `build_target`: `LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.budget.max_usd)`
- **Still open:** `src/audit/qa_generator.py:85` uses `LLMClient()` with the default cap
- Config: added `JudgeConfig` + optional `judge` field in `config.py`; config loads, 45 tests pass

---

## Few-shot picks (dev cases only; split values in the DB are `dev` / `heldout`)
These go into the rubric files. **Keep all of them out of the Day 5 calibration sample.**

- add-003: correct (direct_factual). Matches the reference, nothing added.
- add-006: partially_correct (multi_hop). Right conclusion (surcharge applies) but omits the $19.95 amount; borderline example.
- add-001: wrongful_refusal (direct_factual; correctness: incorrect). Answer is in the docs, bot refused.
- unans-01: appropriate_refusal (unanswerable). Not in the docs, bot declined, nothing invented.
- SYNTHETIC fabricated example (not from the bot): question from adv-02; made-up answer that invents a discount code. Mark as synthetic, do not count in stats.
- OPTIONAL hallucination example: add-004 (bot adds a "2:00 PM PT cutoff" the reference does not mention). Use only if verified as NOT in the docs.

Still to verify against `source_text`:
- [ ] add-006: "free Standard shipping on all US orders incl. Alaska and Hawaii"
- [ ] add-004: "2:00 PM PT cutoff"

---

## Test-set issues found
- **human-21** ("Do you have a store I can visit in person?"): labeled unanswerable, but the docs answer it (online only, no stores; same fact as gap-001). Bot answer is correct.
  - [ ] Fix in `data/demo/testset.jsonl` (`expected_behavior: answer` + reference answer), not only in the DB.
  - [ ] Re-judge this case after the fix.
- `pick_fewshot.py` filtered on 'holdout' but the DB uses 'heldout'. Fixed with a replace in the script.
- **Open decision:** how to label "asks a clarifying question" (ambiguous cases amb-01, amb-02). It is not an appropriate_refusal and not a fabrication. Decide before writing `refusal.yaml`.
  - Suggested option: add `expected_behavior = clarify` for ambiguous cases and a verdict such as `appropriate_clarification`, so asking vs. guessing is measured separately (Part 6 lists "Ambiguous: asks vs. guesses" as its own category).

---

## Bot findings so far (for the report)
- Over-refusal on answerable dev cases: human-01, human-02 (partial), human-03, gap-028, add-001, hand-001 (6 of the dev answerable cases). Likely a retrieval or prompt problem. **Recount after judging.**
- Fabrication: none found among dev unanswerable/off_topic/adversarial cases.
- **Held-out caution:** I noticed that held-out case human-20 looks like a fabrication. Held-out cases should not be inspected while fixing the bot or tuning the rubric. Do not use human-20 to guide any fix, and mention in the case study that I saw this one case.

---

## Carry-over to Day 5
1. Fresh random ~40-case sample, stratified by category, labeled blind (exclude the few-shot cases and today's 20 read cases). Split about half for tuning, half untouched for the final agreement number.
2. Fix human-21 in the testset, and verify add-006 and add-004 against the source text.
3. Close the `qa_generator.py:85` budget gap.
4. Decide how to handle clarifying-question answers, then write `refusal.yaml`.
5. Write `calibration.py`: raw agreement, Cohen's kappa, confusion matrix.
6. Check score vs. answer length (verbosity bias), and re-judge a 10% sample for self-agreement.
7. Fill in the provider-terms lines under Decisions.