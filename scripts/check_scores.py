import sqlite3
con = sqlite3.connect("data/audit.db")
A = "run_20261114_080655_b2f7cc"
B = "run_20261114_080703_44d4ab"
for run in (A, B):
    print(run)
    for metric, n in con.execute(
        "SELECT metric, COUNT(*) FROM scores WHERE run_id=? GROUP BY metric", (run,)
    ):
        print("  ", metric, n)
def cases(run):
    return {r[0] for r in con.execute("SELECT DISTINCT case_id FROM scores WHERE run_id=?", (run,))}
a, b = cases(A), cases(B)
print("cases scored in A:", len(a), " in B:", len(b))
print("SAME CASES" if a == b else "MISMATCH: only in A %s / only in B %s" % (sorted(a - b), sorted(b - a)))
