import sqlite3
c = sqlite3.connect("data/audit.db")
rows = c.execute("""
    SELECT origin, expected_behavior,
           sum(coalesce(trim(question),'')=''),
           sum(coalesce(trim(reference_answer),'')=''),
           count(*)
    FROM cases
    WHERE coalesce(trim(question),'')='' OR coalesce(trim(reference_answer),'')=''
    GROUP BY 1, 2""").fetchall()
print("origin, expected_behavior, empty_question, empty_reference, rows")
for r in rows:
    print(r)