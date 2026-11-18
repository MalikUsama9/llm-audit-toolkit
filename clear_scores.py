import sqlite3, sys
c = sqlite3.connect("data/audit.db")
for run in sys.argv[1:]:
    n = c.execute("DELETE FROM scores WHERE run_id=? AND metric IN ('correctness','refusal')", (run,)).rowcount
    print(run, "deleted", n)
c.commit()