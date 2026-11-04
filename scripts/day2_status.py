import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo/testset.jsonl")
if not PATH.exists():
    sys.exit(f"{PATH} not found. Run from the repo root.")

rows = [json.loads(l) for l in PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
s = lambda v: str(getattr(v, "value", v) or "")


def line(ok, text):
    print(f"  [{'x' if ok else ' '}] {text}")


total = len(rows)
cats = Counter(s(r.get("category")) for r in rows)
origins = Counter(s(r.get("origin")) for r in rows)
behav = Counter(s(r.get("expected_behavior")) for r in rows)

answerable = [r for r in rows if s(r.get("expected_behavior")) == "answer"]
no_source = [r["id"] for r in answerable if not r.get("source_ref") and s(r.get("origin")) != "human"]
non_answer = [r for r in rows if s(r.get("expected_behavior")) in ("refuse", "handoff")]
questions = Counter(s(r.get("question")).strip().lower() for r in rows)
dupes = sum(c - 1 for c in questions.values() if c > 1)
no_diff = sum(1 for r in rows if not r.get("difficulty"))
reviewed = sum(1 for r in rows if r.get("reviewed"))
splits = Counter(s(r.get("split")) for r in rows)
unsplit = sum(1 for r in rows if not r.get("split"))

print(f"\nDay 2 status for {PATH}  ({total} cases)\n")
print("Requirements")
line(total >= 100, f"100+ cases in testset.jsonl (now {total})")
line(len([c for c in cats if c]) >= 6, f"at least 6 categories (now {len([c for c in cats if c])})")
line(not no_source, f"every answerable case has source_ref (missing: {len(no_source)} {no_source[:5]})")
line(bool(non_answer), f"unanswerable cases have expected_behavior refuse/handoff (found {len(non_answer)})")
line(dupes == 0, f"no exact-duplicate questions (duplicates: {dupes})")
line(no_diff == 0, f"difficulty tag on every case (missing: {no_diff})")
line(reviewed >= 30, f"at least 30 cases reviewed (now {reviewed})")
line(unsplit == 0, f"split assigned to every case (unassigned: {unsplit})")

print("\nCategory counts")
for c, n in sorted(cats.items()):
    print(f"  {c or '(none)':20s} {n}")
print("\nOrigin:", dict(origins))
print("Expected behavior:", dict(behav))
print("Split:", dict(splits))

try:
    out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    print("\nGit:", "clean, all committed" if not out else f"{len(out.splitlines())} uncommitted change(s)")
except Exception:
    pass

print("\nAlso run separately: pytest   and   python -m audit.edge_cases --check\n")