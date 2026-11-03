# src/audit/review.py
"""Review generated test cases one at a time.

Usage:
    python -m audit.review --category multi_hop     (review one category)
    python -m audit.review                          (review all unreviewed generated cases)

Keys: a = accept   e = edit   r = reject (removed, saved to rejected_cases.jsonl)
      s = skip for now   q = quit (progress is already saved)
"""
import argparse
import json
import os
import textwrap
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def wrap(text: str) -> str:
    return "\n".join(textwrap.fill(p, 90, initial_indent="  ", subsequent_indent="  ")
                     for p in str(text).splitlines() if p.strip()) or "  (empty)"


def show(r: dict, n: int, total: int) -> None:
    print("\n" + "=" * 94)
    print(f"[{n}/{total}]  {r['id']}   category: {r['category']}   difficulty: {r.get('difficulty')}")
    print("=" * 94)
    print("QUESTION:\n" + wrap(r["question"]))
    print("\nREFERENCE ANSWER:\n" + wrap(r.get("reference_answer", "")))
    print("\nSOURCE (" + ", ".join(r.get("source_ref") or []) + "):")
    print(wrap(r.get("source_text", "")))
    if r["category"] == "multi_hop":
        print("\nCHECK: does the answer need BOTH excerpts? If one is enough, reject it.")
    else:
        print("\nCHECK: is every fact in the reference answer stated in the source?")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/demo/testset.jsonl")
    ap.add_argument("--rejected", default="data/demo/rejected_cases.jsonl")
    ap.add_argument("--category", default=None)
    args = ap.parse_args()

    path, rej_path = Path(args.file), Path(args.rejected)
    rows = load(path)
    todo = [r["id"] for r in rows
        if r.get("origin") == "generated" and not r.get("reviewed")
        and r.get("expected_behavior") == "answer"
        and (not args.category or r["category"] == args.category)]
    total = len(todo)
    print(f"{total} case(s) to review. Keys: a=accept  e=edit  r=reject  s=skip  q=quit")
    stats = {"accepted": 0, "edited": 0, "rejected": 0, "skipped": 0}

    try:
        for n, cid in enumerate(todo, 1):
            idx = next(i for i, r in enumerate(rows) if r["id"] == cid)
            r = rows[idx]
            show(r, n, total)
            while True:
                k = input("\n[a]ccept  [e]dit  [r]eject  [s]kip  [q]uit > ").strip().lower()
                if k in ("a", "e", "r", "s", "q"):
                    break
            if k == "q":
                break
            if k == "s":
                stats["skipped"] += 1
                continue
            if k == "r":
                with rej_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                rows.pop(idx)
                stats["rejected"] += 1
            else:
                if k == "e":
                    q = input("New question (Enter keeps current): ").strip()
                    a = input("New reference answer (Enter keeps current): ").strip()
                    if q:
                        r["question"] = q
                    if a:
                        r["reference_answer"] = a
                    stats["edited"] += 1
                else:
                    stats["accepted"] += 1
                r["reviewed"] = True
            save(path, rows)           # saved after every decision
    except KeyboardInterrupt:
        print("\nStopped. Progress is saved.")

    left = sum(1 for r in rows if r.get("origin") == "generated" and not r.get("reviewed")
        and r.get("expected_behavior") == "answer")
    print(f"\nThis session: {stats}")
    print(f"Generated cases still unreviewed: {left}   |   Total cases in file: {len(rows)}")


if __name__ == "__main__":
    main()