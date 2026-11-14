# scripts/run_judge_on_labels.py
import sqlite3
from audit.config import load_config
from audit.judge import judge_with_checks, load_rubric, log_run_settings
from audit.llm.client import LLMClient
from audit.models import Score
from audit.store import Store

CONFIG = "configs/audit.yaml"
VALUE = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0,
         "appropriate_refusal": 1.0, "wrongful_refusal": 0.0, "fabricated": 0.0,
         "missed_clarification": 0.5}

cfg = load_config(CONFIG)
store = Store(cfg.paths.database)
client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)
rubrics = {"correctness": load_rubric("correctness"), "refusal": load_rubric("refusal")}
log_run_settings(cfg.judge, rubrics)

con = sqlite3.connect(cfg.paths.database)
rows = con.execute("""
    SELECT h.run_id, h.case_id, c.question, c.reference_answer, c.source_text,
           c.expected_behavior, r.answer, r.error
    FROM human_labels h
    JOIN cases c   ON c.id = h.case_id
    JOIN results r ON r.run_id = h.run_id AND r.case_id = h.case_id
    ORDER BY h.run_id, h.case_id""").fetchall()
print(f"{len(rows)} labeled results to judge")

done = skipped = failed = 0
for run_id, case_id, q, ref, src, behavior, answer, err in rows:
    metric = "correctness" if behavior == "answer" else "refusal"
    already = con.execute("SELECT 1 FROM scores WHERE run_id=? AND case_id=? AND metric=?",
                          (run_id, case_id, metric)).fetchone()
    if already:
        continue
    try:
        chk, res = judge_with_checks(client, cfg.judge, rubrics[metric], case_id,
                                     f"[Expected behavior: {behavior}] {q or ''}", ref or "", src or "", answer or "", bot_error=err)
    except Exception as e:
        print(f"  FAILED {run_id}/{case_id}: {e}")
        failed += 1
        continue
    if res is None:
        print(f"  skipped {case_id}: check={chk.status}")
        skipped += 1
        continue
    verdict = res.output.verdict
    store.add_score(Score(run_id=run_id, case_id=case_id, metric=metric,
                          value=VALUE.get(verdict, 0.0),
                          reasoning=f"[{verdict}] {res.output.reasoning}",
                          judge_model=res.judge_model))
    done += 1
    print(f"  {case_id:10} {metric:12} -> {verdict}")

print(f"\njudged={done} skipped={skipped} failed={failed}")