import sqlite3

con = sqlite3.connect("data/audit.db")
A = "run_20261114_080655_b2f7cc"
B = "run_20261114_080703_44d4ab"

def cols(table):
    return [c[1] for c in con.execute(f"pragma table_info({table})")]

score_cols = cols("scores")
result_cols = cols("results")
print("scores columns: ", score_cols)
print("results columns:", result_cols)

# Layout 1: scores has run_id and case_id directly.
# Layout 2: scores links to results (result_id), and results holds run_id and case_id.
if "run_id" in score_cols and "case_id" in score_cols:
    FROM = "scores s"
    RUN, CASE = "s.run_id", "s.case_id"
elif "result_id" in score_cols:
    FROM = "scores s JOIN results r ON r.id = s.result_id"
    RUN, CASE = "r.run_id", "r.case_id"
else:
    raise SystemExit("Can't link scores to runs. Paste the schema output.")

for run in (A, B):
    print(run)
    for metric, n in con.execute(
        f"SELECT s.metric, COUNT(*) FROM {FROM} WHERE {RUN}=? GROUP BY s.metric", (run,)
    ):
        print("  ", metric, n)

def cases(run):
    return {r[0] for r in con.execute(
        f"SELECT DISTINCT {CASE} FROM {FROM} WHERE {RUN}=?", (run,))}

a, b = cases(A), cases(B)
print("cases scored in A:", len(a), " in B:", len(b))
print("SAME CASES" if a == b else
      "MISMATCH: only in A %s / only in B %s" % (sorted(a - b), sorted(b - a)))