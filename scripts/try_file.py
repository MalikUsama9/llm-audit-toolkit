"""Round-trip test: export questions -> 'client' fills answers -> read back."""
import csv
from pathlib import Path

from audit.targets.file_target import FileTarget, export_questions

out = Path("data/demo/roundtrip")
questions_csv = out / "questions.csv"
answers_csv = out / "answers.csv"

# 1) export a small file
pairs = [
    ("c001", "How many days do I have to return an item?"),
    ("c002", "What is the cutoff time for overnight shipping?"),
    ("c003", "What is the CEO's favourite colour?"),
    ("c004", "Question the client forgets to answer"),
]
n = export_questions(pairs, questions_csv)
print(f"1) exported {n} questions to {questions_csv}")

# 2) pretend to be the client's team: fill in the answer column
with questions_csv.open(newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
rows[0]["answer"] = "30 days from delivery."
rows[0]["contexts"] = "Returns - 30 days ||| Returns - exceptions"
rows[1]["answer"] = "Before 12:00 noon PT."          # no contexts -> black-box
rows[2]["answer"] = "I don't have that information."
# rows[3] left blank on purpose
with answers_csv.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["case_id", "question", "answer", "contexts"])
    w.writeheader()
    w.writerows(rows)
print(f"2) client file written to {answers_csv}")

# 3) read it back, matched by case id
target = FileTarget.from_csv(answers_csv)
print("3) read back:")
for case_id, _ in pairs:
    print("  ", case_id, target.answer_for(case_id))

print("4) by question text:", target.answer("What is the cutoff time for overnight shipping?"))
print("5) unknown case id: ", target.answer_for("c999"))
print("6) not answered yet:", target.missing_case_ids())
print(target.config_snapshot())