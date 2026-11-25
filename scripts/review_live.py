import sys, json, random, sqlite3, logging
from audit.config import load_config
from audit.llm.client import LLMClient
from audit.judge import judge_case, load_rubric, log_run_settings
from audit.checks import run_checks, SKIP_JUDGE_STATUSES

logging.basicConfig(level=logging.WARNING)
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "run_20261110_005907_b09fcd"
N_TOTAL, N_UNANSWERABLE = 24, 6
random.seed(7)

cfg = load_config("configs/audit.yaml")
client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)
rubric = load_rubric("faithfulness", cfg.judge.rubric_dir)
log_run_settings(cfg.judge, {"faithfulness": rubric})

con = sqlite3.connect("data/audit.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT c.*, r.answer AS bot_answer FROM cases c "
    "JOIN results r ON r.case_id = c.id WHERE r.run_id = ?", (RUN_ID,)).fetchall()
assert rows, f"no rows for run {RUN_ID}"

def g(r, k, d=""):
    return r[k] if k in r.keys() and r[k] is not None else d

unans = [r for r in rows if g(r, "expected_behavior", "answer") != "answer"]
ans = [r for r in rows if g(r, "expected_behavior", "answer") == "answer"]
random.shuffle(unans); random.shuffle(ans)
sample = unans[:N_UNANSWERABLE] + ans[:N_TOTAL - min(N_UNANSWERABLE, len(unans))]
random.shuffle(sample)

out = ["# Judgment review\n", f"Run: {RUN_ID}\n\n"]
tot_claims = tot_unver = 0
for i, r in enumerate(sample, 1):
    chk = run_checks(g(r, "bot_answer"))
    res = None
    if chk.status not in SKIP_JUDGE_STATUSES:
        res = judge_case(client, cfg.judge, rubric, r["id"], g(r, "question"),
                         g(r, "reference_answer"), g(r, "source_text"), str(g(r, "bot_answer")))
    out.append(f"## {i}. {r['id']}  (expected: {g(r, 'expected_behavior', '?')}, check: {chk.status})\n\n")
    out.append(f"**Question:** {g(r, 'question')}\n\n")
    out.append(f"**Reference:** {g(r, 'reference_answer') or '(none)'}\n\n")
    out.append(f"**Source:** {str(g(r, 'source_text'))[:800]}\n\n")
    out.append(f"**Bot answer:** {g(r, 'bot_answer')}\n\n")
    out.append("**MY VERDICT (supported / contradicted / not_in_source):** \n\n")
    out.append("<details><summary>Judge output</summary>\n\n")
    if res is None:
        out.append(f"no judge result (check status: {chk.status}, or judge_failure)\n")
    else:
        tot_claims += len(res.output.claims); tot_unver += res.evidence_unverified
        out.append(f"verdict: **{res.output.verdict}** | hallucinated: {res.hallucinated} "
                   f"| unverified quotes: {res.evidence_unverified}\n\n")
        out.append(f"reasoning: {res.output.reasoning}\n\n")
        for c in res.output.claims:
            out.append(f"- [{c.status}] {c.claim} | evidence: {c.evidence}\n")
    out.append("\n</details>\n\n")
    out.append("**Agree?** yes / no\n\n")
    out.append("**If no, cause:** ambiguity / wrong reference / judge error / my mistake\n\n")
    out.append("**Note:** \n\n---\n\n")

out.append(f"## Summary\n\nCases read: {len(sample)}\n\nAgreed: \n\nDisagreed: \n\n"
           f"- Rubric ambiguity: \n- Wrong reference: \n- Judge error: \n- My mistake: \n\n"
           f"Evidence quotes not found in source: {tot_unver} of {tot_claims} claims\n")
open("review.md", "w", encoding="utf-8").write("".join(out))
print(f"wrote review.md with {len(sample)} cases")
