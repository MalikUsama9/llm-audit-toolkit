import sqlite3, math
from statistics import mean

con = sqlite3.connect("data/audit.db")


def pearson(x, y):
    if len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


# ---- A. pointwise scores vs length ----
rows = con.execute("""
    SELECT s.value, length(r.answer) FROM scores s
    JOIN results r ON r.run_id = s.run_id AND r.case_id = s.case_id
    WHERE s.metric = 'correctness' AND r.answer IS NOT NULL
""").fetchall()
print(f"A. Pointwise correctness vs answer length (n={len(rows)})")
if rows:
    r = pearson([v for v, _ in rows], [l for _, l in rows])
    print("   Pearson r =", None if r is None else round(r, 3))
    for val in sorted({v for v, _ in rows}):
        ls = [l for v, l in rows if v == val]
        print(f"   score {val}: n={len(ls)}, mean length={mean(ls):.0f} chars")

# ---- B. pairwise verdicts vs length ----
lens = {(rid, cid): len(ans or "")
        for rid, cid, ans in con.execute("SELECT run_id, case_id, answer FROM results")}
groups = {}
for a, b, cid, w in con.execute(
        "SELECT run_a, run_b, case_id, run_winner FROM pairwise_judgments"):
    groups.setdefault((a, b, cid), []).append(w)

buckets = {"<1.2x": [0, 0, 0], "1.2-1.5x": [0, 0, 0], "1.5-2x": [0, 0, 0], ">2x": [0, 0, 0]}
for (a, b, cid), ws in groups.items():
    if len(ws) != 2 or ws[0] != ws[1]:
        continue  # keep only order-consistent verdicts
    la, lb = lens.get((a, cid), 0), lens.get((b, cid), 0)
    if min(la, lb) == 0 or la == lb:
        continue
    ratio = max(la, lb) / min(la, lb)
    key = "<1.2x" if ratio < 1.2 else "1.2-1.5x" if ratio < 1.5 else "1.5-2x" if ratio < 2 else ">2x"
    longer = a if la > lb else b
    w = ws[0]
    idx = 2 if w not in (a, b) else (0 if w == longer else 1)  # 0=longer won, 1=shorter won, 2=tie
    buckets[key][idx] += 1

print("\nB. Pairwise (consistent verdicts only), by length ratio of the two answers")
print(f"   {'ratio':10} {'longer won':>11} {'shorter won':>12} {'tie':>5}")
for k, (lw, sw, t) in buckets.items():
    print(f"   {k:10} {lw:>11} {sw:>12} {t:>5}")
print("\nNote: longer answers can legitimately be more correct. The padding test (Step 2) is the real check.")