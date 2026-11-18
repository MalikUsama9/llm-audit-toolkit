import sys
from audit.config import load_config
from audit.judge import judge_with_checks, load_rubric, log_run_settings
from audit.llm.client import LLMClient
from audit.store import Store, Score

CONFIG = "configs/audit.yaml"

# verdict -> score value (summary counts >=1.0 as pass, between 0 and 1 as partial)
VALUE = {
    "correct": 1.0, "appropriate_refusal": 1.0,
    "partially_correct": 0.5, "partial": 0.5,
    "wrong": 0.0, "incorrect": 0.0, "fabricated": 0.0,
    "wrongful_refusal": 0.0, "missed_refusal": 0.0,
    "missed_clarification": 0.0,
}

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit("usage: python judge_run.py RUN_ID [--limit N]")
run_id = args[0]
limit = None
if "--limit" in sys.argv:
    limit = int(sys.argv[sys.argv.index("--limit") + 1])

cfg = load_config(CONFIG)
store = Store(cfg.paths.database)
if store.get_run(run_id) is None:
    sys.exit(f"no run called {run_id}")

client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)
rubrics = {"correctness": load_rubric("correctness"), "refusal": load_rubric("refusal")}
log_run_settings(cfg.judge, rubrics)

cases = {c.id: c for c in store.get_cases()}
results = store.get_results(run_id)
done = {s.case_id for s in store.get_scores(run_id) if s.metric in rubrics}
print(f"{len(results)} answers, {len(done)} already scored")

saved, skipped, unknown, fails = 0, 0, set(), 0
for r in results:
    if r.case_id in done or r.case_id not in cases:
        continue
    if limit is not None and saved >= limit:
        break
    case = cases[r.case_id]
    metric = "correctness" if case.expected_behavior.value == "answer" else "refusal"
    try:
        check, jr = judge_with_checks(
            client, cfg.judge, rubrics[metric], r.case_id,
            f"[Expected behavior: {case.expected_behavior.value}] {case.question}", case.reference_answer or "", case.source_text or "",
            r.answer or "", bot_error=r.error,
        )
        fails = 0
    except Exception as e:
        fails += 1
        print(f"ERROR on {r.case_id}: {e}")
        if fails >= 3:
            print("3 errors in a row (rate limit?). Stopping. Run the same command again to resume.")
            break
        continue
    if jr is None:                       # error / empty answer: reported separately, never scored
        skipped += 1
        continue
    verdict = jr.output.verdict
    if verdict not in VALUE:
        unknown.add(verdict)
        continue
    store.add_score(Score(
        run_id=run_id, case_id=r.case_id, metric=metric, value=VALUE[verdict],
        reasoning=jr.output.reasoning, judge_model=jr.judge_model,
    ))
    saved += 1
    print(f"[{saved}] {r.case_id}: {verdict}")

print(f"\nSaved {saved}, skipped {skipped} (errors/empty).")
if unknown:
    print("UNKNOWN verdicts not saved (add them to VALUE):", unknown)
