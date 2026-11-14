"""Step 5.7: midpoint checkpoint. Read-only. Usage: python scripts/checkpoint.py [RUN_ID]"""
import sqlite3, sys

con = sqlite3.connect("data/audit.db")
q = lambda sql, *p: con.execute(sql, p).fetchall()
one = lambda sql, *p: con.execute(sql, p).fetchone()[0]
results = []

def check(name, ok, detail):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# pick the run: argument, else the latest run that has scores
run = sys.argv[1] if len(sys.argv) > 1 else None
if run is None:
    r = q("""SELECT r.run_id FROM runs r WHERE EXISTS
             (SELECT 1 FROM scores s WHERE s.run_id=r.run_id)
             ORDER BY r.created_at DESC LIMIT 1""")
    run = r[0][0] if r else None
print("Checkpoint run:", run, "\n")

print("Stage 1: generate questions (cases table)")
total = one("SELECT COUNT(*) FROM cases")
check("cases exist", total > 0, f"{total} cases")
print("   by origin:", q("SELECT origin, COUNT(*) FROM cases GROUP BY origin"))
print("   by split :", q("SELECT split, COUNT(*) FROM cases GROUP BY split"))
# Only "answer" cases need a reference answer; refuse/handoff cases legitimately have none.
bad = one("SELECT COUNT(*) FROM cases WHERE coalesce(trim(question),'')='' OR (expected_behavior='answer' AND coalesce(trim(reference_answer),'')='')")
check("no empty question / missing reference on answer cases", bad == 0, f"{bad} bad rows")
gen = one("SELECT COUNT(*) FROM cases WHERE origin='generated'")
check("generated cases present", gen > 0, f"{gen} generated")
rev = one("SELECT COUNT(*) FROM cases WHERE reviewed=1")
check("some cases reviewed", rev > 0, f"{rev} reviewed")

print("\nStage 2: run tests (runs + results)")
check("runs recorded", one("SELECT COUNT(*) FROM runs") > 0, f"{one('SELECT COUNT(*) FROM runs')} runs")
if run:
    n = one("SELECT COUNT(*) FROM results WHERE run_id=?", run)
    err = one("SELECT COUNT(*) FROM results WHERE run_id=? AND error IS NOT NULL", run)
    empty = one("SELECT COUNT(*) FROM results WHERE run_id=? AND coalesce(trim(answer),'')=''", run)
    ctx = one("SELECT COUNT(*) FROM results WHERE run_id=? AND contexts IS NOT NULL", run)
    check("results stored", n > 0, f"{n} results")
    check("error rate under 5%", n > 0 and err / n < 0.05, f"{err} errors")
    check("empty answers under 5%", n > 0 and empty / n < 0.05, f"{empty} empty")
    print(f"   glass-box contexts stored: {ctx}/{n}")

    print("\nStage 3: evaluate answers (scores + checks)")
    sc = q("SELECT metric, COUNT(*), round(avg(value),3) FROM scores WHERE run_id=? GROUP BY metric", run)
    print("   metric, n, mean:", sc)
    corr = one("SELECT COUNT(*) FROM scores WHERE run_id=? AND metric IN ('correctness','refusal')", run)
    check("correctness/refusal scored", corr > 0, f"{corr} scored")
    check("score coverage at least 90%", n > 0 and corr / n >= 0.9, f"{corr}/{n} cases")
    bad_vals = one("SELECT COUNT(*) FROM scores WHERE run_id=? AND (value IS NULL OR value<0 OR value>1)", run)
    check("score values valid (0 to 1)", bad_vals == 0, f"{bad_vals} invalid")
    chk = one("SELECT COUNT(*) FROM checks WHERE run_id=?", run)
    check("rule checks stored", chk > 0, f"{chk} rows")

    print("\nStage 4: store results (everything linked and queryable)")
    orphan = one("SELECT COUNT(*) FROM results WHERE run_id=? AND case_id NOT IN (SELECT id FROM cases)", run)
    check("no orphan results", orphan == 0, f"{orphan} orphans")
    orphan_s = one("SELECT COUNT(*) FROM scores WHERE run_id=? AND case_id NOT IN (SELECT case_id FROM results WHERE run_id=?)", run, run)
    check("no scores without a result", orphan_s == 0, f"{orphan_s} orphans")

print("\nSteps 5.x so far (extras built since the first draft)")
check("pairwise judgments (5.4/5.5)", one("SELECT COUNT(*) FROM pairwise_judgments") > 0, f"{one('SELECT COUNT(*) FROM pairwise_judgments')} rows")
check("human labels (agreement)", one("SELECT COUNT(*) FROM human_labels") > 0, f"{one('SELECT COUNT(*) FROM human_labels')} rows")
check("retrieval metrics (5.6)", one("SELECT COUNT(*) FROM scores WHERE metric LIKE 'retrieval_%'") > 0, "retrieval_* rows in scores")

print(f"\nSummary: {sum(results)} of {len(results)} checks passed")