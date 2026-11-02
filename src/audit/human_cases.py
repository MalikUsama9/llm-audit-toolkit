"""Import hand-written questions from data/demo/human_cases.csv.

CSV columns: category,question,expected_behavior,reference_answer,keywords
For answer cases, `keywords` are words that must all appear in the supporting chunk
(";" between words, "|" between two chunks for multi-hop). The script finds the
chunk(s) and fills in source_ref and source_text for you.

Usage:  python -m audit.human_cases
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from audit.chunking import chunk_dir
from audit.models import Difficulty, ExpectedBehavior, Origin, TestCase


def find_chunks(chunks, group: str):
    terms = [t.strip().lower() for t in group.split(";") if t.strip()]
    return [c for c in chunks if all(t in f"{c.heading} {c.text}".lower() for t in terms)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/demo/human_cases.csv")
    ap.add_argument("--docs", default="data/demo/docs")
    ap.add_argument("--out", default="data/demo/human_cases.jsonl")
    args = ap.parse_args()

    chunks = chunk_dir(args.docs)
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("question") or "").strip()]

    cases: list[TestCase] = []
    problems = 0
    for n, row in enumerate(rows, 1):
        label = f"human-{n:02d}"
        behavior = row["expected_behavior"].strip().lower()
        source_ref: list[str] | None = None
        source_text: str | None = None

        if behavior == "answer":
            ids: list[str] = []
            texts: list[str] = []
            ok = True
            for group in (row.get("keywords") or "").split("|"):
                if not group.strip():
                    continue
                found = find_chunks(chunks, group)
                if not found:
                    print(f"{label}: NO CHUNK MATCHES keywords '{group}' - {row['question']}")
                    ok = False
                    break
                if len(found) > 1:
                    others = ", ".join(c.chunk_id for c in found[1:4])
                    print(f"{label}: {len(found)} chunks match '{group}'; using "
                          f"{found[0].chunk_id} (others: {others})")
                if found[0].chunk_id not in ids:
                    ids.append(found[0].chunk_id)
                    texts.append(found[0].text)
            if not ok or not ids:
                problems += 1
                continue
            source_ref, source_text = ids, "\n\n".join(texts)

        try:
            cases.append(TestCase(
                id=label,
                category=row["category"].strip(),
                question=row["question"].strip(),
                reference_answer=(row.get("reference_answer") or "").strip() or None,
                source_ref=source_ref,
                source_text=source_text,
                expected_behavior=ExpectedBehavior(behavior),
                difficulty=Difficulty.MEDIUM,
                origin=Origin.HUMAN,
                reviewed=False,
            ))
        except (ValidationError, ValueError) as e:
            print(f"{label}: invalid row ({e}) - {row['question']}")
            problems += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c.model_dump(mode="json"), ensure_ascii=False) + "\n")

    print(f"\nWrote {len(cases)} human cases to {out} ({problems} row(s) skipped)")
    for cat, count in Counter(c.category for c in cases).items():
        print(f"  {cat:15s} {count}")


if __name__ == "__main__":
    main()