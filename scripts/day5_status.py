"""Day 5 status check (steps 5.1 to 5.9). Read-only, no LLM calls."""
import sqlite3, os, math, glob
from collections import Counter

DB = "data/audit.db"
con = sqlite3.connect(DB)
one = lambda sql, *p: con.execute(sql, p).fetchone()[0]
rows_ = lambda sql, *p: con.execute(sql, p).fetchall()
res = []

def check(step, name, status, detail):
    res.append(status)
    print(f"  [{status}] {step} {name}: {detail}")

H2V = {"correct": 1.0, "partially_correct": 0.5, "partial": 0.5, "incorrect": 0.0,
       "wrong": 0.0, "hallucinated": 0.0, "fabricated": 0.0,
       "appropriate_refusal": 1.0, "wrongful_refusal": 0.0, "missed_clarification": 0.5}
ALLOWED = {"correct", "partially_correct", "wrong", "hallucinated"}

print("DAY 5 STATUS CHECK\n")

# ---- 5.1 hand labels
n = one("SELECT COUNT(*) FROM human_labels")
labels = Counter(l for (l,) in rows_("SELECT label FROM human_labels"))
odd = {k: v for k, v in labels.items() if k not in ALLOWED}
check("5.1", "about 40 hand labels", "PASS" if n >= 40 else "FAIL", f"{n} labels {dict(labels)}")
check("5.1", "labels use the 4 categories", "PASS" if not odd else "WARN", f"unexpected labels: {odd}" if odd else "all valid")

# ---- 5.2 / 5.8 agreement
pairs = []
for lab, val in rows_("""SELECT h.label, s.value FROM human_labels h
        JOIN scores s ON s.run_id=h.run_id AND s.case_id=h.case_id
        AND s.metric IN ('correctness','refusal')"""):
    hv = H2V.get((lab or "").lower())
    if hv is not None:
        pairs.append((hv, float(val)))
if pairs:
    agree = sum(a == b for a, b in pairs) / len(pairs)
    hu, ju = [a for a, _ in pairs], [b for _, b in pairs]
    pe = sum((hu.count(c) / len(pairs)) * (ju.count(c) / len(pairs)) for c in (0.0, 0.5, 1.0))
    kappa = None if pe == 1 else (agree - pe) / (1 - pe)
    check("5.2", "agreement calculated", "PASS", f"{agree:.1%} on {len(pairs)} cases, kappa={kappa:.3f}" if kappa is not None else f"{agree:.1%}")
    check("5.8", "agreement known and acceptable", "PASS" if agree >= 0.80 else "WARN",
          "80% or higher" if agree >= 0.80 else "under 80%, review the rubric")
else:
    check("5.2", "agreement calculated", "FAIL", "no labeled cases have a judge score, run run_judge_on_labels.py")
    check("5.8", "agreement known", "FAIL", "see 5.2")

# ---- 5.3 rubric iteration (partly manual)
try:
    from audit.judge import load_rubric
    txt = str(load_rubric("correctness"))
    check("5.3", "rubric loads", "PASS" if len(txt) > 200 else "WARN", f"{len(txt)} characters")
    check("5.3", "rubric tells judge to ignore length", "PASS" if "length" in txt.lower() or "verbos" in txt.lower() else "WARN",
          "mentioned" if "length" in txt.lower() or "verbos" in txt.lower() else "add the sentence from step 5.5 (also confirm your 5.3 rubric edits are saved)")
except Exception as e:
    check("5.3", "rubric loads", "WARN", f"could not load ({e}); verify manually")

# ---- 5.4 position bias
pj = one("SELECT COUNT(*) FROM pairwise_judgments")
check("5.4", "pairwise judgments stored", "PASS" if pj >= 40 else "FAIL", f"{pj} rows")
groups = {}
for a, b, c, w in rows_("SELECT run_a, run_b, case_id, run_winner FROM pairwise_judgments"):
    groups.setdefault((a, b, c), []).append(w)
both = [ws for ws in groups.values() if len(ws) == 2]
if both:
    flip = sum(ws[0] != ws[1] for ws in both) / len(both)
    check("5.4", "both orders judged, flip rate known", "PASS" if flip <= 0.20 else "WARN", f"{len(both)} cases, {flip:.1%} flipped")
else:
    check("5.4", "both orders judged", "FAIL", "no case judged in both orders")
check("5.4", "consistent verdicts file saved", "PASS" if os.path.exists("data/demo/pairwise_consistent.csv") else "FAIL", "data/demo/pairwise_consistent.csv")

# ---- 5.5 verbosity
padded = [r for (r,) in rows_("SELECT run_id FROM runs WHERE run_id LIKE 'run_padded_%'")]
if padded:
    p = padded[-1]
    g = {}
    for a, c, w in rows_("SELECT run_a, case_id, run_winner FROM pairwise_judgments WHERE run_b=?", p):
        g.setdefault(c, []).append(w)
    cons = [ws[0] for ws in g.values() if len(ws) == 2 and ws[0] == ws[1]]
    pw = sum(1 for w in cons if w == p)
    rate = pw / len(cons) if cons else None
    if rate is None:
        check("5.5", "padding test judged", "FAIL", f"no judgments for {p}")
    else:
        check("5.5", "padding test: padded answer wins <= 10%", "PASS" if rate <= 0.10 else "FAIL", f"{rate:.1%} of {len(cons)} consistent verdicts")
else:
    check("5.5", "padding test run exists", "FAIL", "run make_padded_run.py")
check("5.5", "verbosity_check script present", "PASS" if os.path.exists("scripts/verbosity_check.py") else "WARN", "scripts/verbosity_check.py")

# ---- 5.6 retrieval
rh = one("SELECT COUNT(*) FROM scores WHERE metric='retrieval_hit'")
check("5.6", "retrieval metrics stored", "PASS" if rh > 0 else "FAIL", f"{rh} retrieval_hit rows" if rh else "run retrieval_eval.py RUN_ID --save")

# ---- 5.7 end-to-end
latest = rows_("""SELECT r.run_id FROM runs r WHERE EXISTS (SELECT 1 FROM scores s WHERE s.run_id=r.run_id AND s.metric IN ('correctness','refusal'))
                  AND EXISTS (SELECT 1 FROM checks c WHERE c.run_id=r.run_id) ORDER BY r.created_at DESC LIMIT 1""")
if latest:
    r = latest[0][0]
    nres = one("SELECT COUNT(*) FROM results WHERE run_id=?", r)
    nsc = one("SELECT COUNT(*) FROM scores WHERE run_id=? AND metric IN ('correctness','refusal')", r)
    nerr = one("SELECT COUNT(*) FROM results WHERE run_id=? AND error IS NOT NULL", r)
    ok = nres > 0 and nsc / nres >= 0.9 and nerr == 0
    check("5.7", "one run has results + scores + checks", "PASS" if ok else "WARN", f"{r}: {nres} results, {nsc} scored, {nerr} errors")
else:
    check("5.7", "one run has results + scores + checks", "FAIL", "run audit.cli run, audit.cli check, scripts/judge_run.py")
orph = one("SELECT COUNT(*) FROM results WHERE case_id NOT IN (SELECT id FROM cases)")
check("5.7", "no orphan results", "PASS" if orph == 0 else "FAIL", f"{orph} orphans")

# ---- 5.9 backup
bk = "data/audit_backup_phase5.db"
check("5.9", "backup saved", "PASS" if os.path.exists(bk) else "FAIL", bk)

print(f"\nSUMMARY: {res.count('PASS')} PASS, {res.count('WARN')} WARN, {res.count('FAIL')} FAIL")
print("DAY 5 COMPLETE" if res.count("FAIL") == 0 else "DAY 5 NOT COMPLETE: fix the FAIL lines above")