import csv, sqlite3

con = sqlite3.connect("data/audit.db")
with open("data/demo/disagreements.csv", encoding="utf-8") as f:
    dis = list(csv.DictReader(f))

for d in dis:
    r = con.execute("""SELECT c.question, c.reference_answer, r.answer, s.reasoning
        FROM cases c
        JOIN results r ON r.case_id = c.id AND r.run_id = ?
        LEFT JOIN scores s ON s.run_id = r.run_id AND s.case_id = r.case_id
        WHERE c.id = ?""", (d["run"], d["case"])).fetchone()
    print("=" * 90)
    print(d["case"], "| you:", d["h_label"], "| judge:", d["j_verdict"], "| type:", d["beh"])
    print("YOUR NOTE:", d["note"])
    if r:
        for name, val in zip(["QUESTION", "REFERENCE", "BOT ANSWER", "JUDGE REASONING"], r):
            print(f"{name}: {val}")
    else:
        print("(no row found)")