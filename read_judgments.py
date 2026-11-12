import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from audit.config import load_config
from audit.judge import judge_with_checks, load_rubric, log_run_settings
from audit.llm.client import LLMClient
from audit.store import Store

CONFIG = "configs/audit.yaml"
OUT_JSONL = Path("data/demo/judgments_dev.jsonl")
OUT_MD = Path("judgments_to_read.md")
SAMPLE_SIZE = 24

cfg = load_config(CONFIG)

# which run to judge: pass a run id, or use the newest run
con = sqlite3.connect(cfg.paths.database)
if len(sys.argv) > 1:
    run_id = sys.argv[1]
else:
    run_id = con.execute(
        "select run_id from runs order by created_at desc limit 1"
    ).fetchone()[0]
print("Judging run:", run_id)

store = Store(cfg.paths.database)
client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)

rubrics = {"correctness": load_rubric("correctness"), "refusal": load_rubric("refusal")}
log_run_settings(cfg.judge, rubrics)

cases = {c.id: c for c in store.get_cases()}
results = {r.case_id: r for r in store.get_results(run_id)}

# resume support: skip cases already judged
OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
done = set()
if OUT_JSONL.exists():
    for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["run_id"] == run_id:
            done.add(row["case_id"])

dev_ids = [cid for cid, c in cases.items()
           if c.split is not None and c.split.value == "dev" and cid in results]
print(f"{len(dev_ids)} dev cases with answers, {len(done)} already judged")

with open(OUT_JSONL, "a", encoding="utf-8") as f:
    for i, cid in enumerate(dev_ids, 1):
        if cid in done:
            continue
        case, res = cases[cid], results[cid]
        rubric_name = "correctness" if case.expected_behavior.value == "answer" else "refusal"
        check, jr = judge_with_checks(
            client, cfg.judge, rubrics[rubric_name], cid,
            case.question, case.reference_answer or "", case.source_text or "",
            res.answer or "", bot_error=res.error,
        )
        row = {
            "run_id": run_id, "case_id": cid, "category": case.category,
            "expected_behavior": case.expected_behavior.value,
            "rubric": rubric_name, "question": case.question,
            "reference": case.reference_answer, "answer": res.answer,
            "check_status": check.status,
            "verdict": jr.output.verdict if jr else None,
            "reasoning": jr.output.reasoning if jr else None,
            "hallucinated": jr.hallucinated if jr else None,
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        print(f"[{i}/{len(dev_ids)}] {cid}: {row['verdict'] or check.status}")

# build the reading file: a mix of verdict types
rows = [json.loads(l) for l in OUT_JSONL.read_text(encoding="utf-8").splitlines()]
rows = [r for r in rows if r["run_id"] == run_id and r["verdict"]]
groups = defaultdict(list)
for r in rows:
    groups[r["verdict"]].append(r)

picked, i = [], 0
while len(picked) < SAMPLE_SIZE and any(groups.values()):
    for v in list(groups):
        if groups[v] and len(picked) < SAMPLE_SIZE:
            picked.append(groups[v].pop(0))

with open(OUT_MD, "w", encoding="utf-8") as m:
    m.write(f"# Judgments to read (run {run_id})\n\n")
    for n, r in enumerate(picked, 1):
        m.write(f"## {n}. {r['case_id']} | {r['category']} | expected: {r['expected_behavior']}\n\n")
        m.write(f"**Question:** {r['question']}\n\n")
        m.write(f"**Reference:** {r['reference']}\n\n")
        m.write(f"**Bot answer:** {r['answer']}\n\n")
        m.write(f"**JUDGE VERDICT:** {r['verdict']}  (rubric: {r['rubric']})\n\n")
        m.write(f"**Judge reasoning:** {r['reasoning']}\n\n")
        m.write("**MY VERDICT:** \n\n**AGREE?:** \n\n")
        m.write("**CAUSE (rubric / reference / judge):** \n\n---\n\n")
print(f"Wrote {len(picked)} cases to {OUT_MD}")