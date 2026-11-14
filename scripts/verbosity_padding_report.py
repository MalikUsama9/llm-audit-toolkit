import sqlite3, sys

orig, padded = sys.argv[1], sys.argv[2]
c = sqlite3.connect("data/audit.db")
by = {}
for cid, w in c.execute("SELECT case_id, run_winner FROM pairwise_judgments WHERE run_a=? AND run_b=?",
                        (orig, padded)):
    by.setdefault(cid, []).append(w)

consistent = [ws[0] for ws in by.values() if len(ws) == 2 and ws[0] == ws[1]]
flipped = sum(1 for ws in by.values() if len(ws) == 2 and ws[0] != ws[1])
orig_wins = sum(1 for w in consistent if w == orig)
pad_wins = sum(1 for w in consistent if w == padded)
ties = len(consistent) - orig_wins - pad_wins
n = len(consistent)

print(f"Cases judged in both orders: {len(by)}  (consistent: {n}, flipped: {flipped})")
print(f"Original won: {orig_wins} | Padded (longer) won: {pad_wins} | Tie: {ties}")
if n:
    rate = pad_wins / n
    print(f"Verbosity bias rate (padded wins / consistent) = {rate:.1%}")
    print("PASS: length alone did not win" if rate <= 0.10 else "FAIL: judge rewards fluff, add controls and rerun")