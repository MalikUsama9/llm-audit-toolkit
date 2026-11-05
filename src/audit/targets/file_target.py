"""FileTarget: for clients who can't give us API access.

The round trip:
  1. export_questions(cases, "questions.csv")   -> we send the client this file
  2. the client's team fills in the `answer` column (and `contexts` if they can)
  3. FileTarget.from_csv("answers.csv")         -> the audit reads the answers back

Rows are matched by case_id. The CSV never contains reference answers or
expected behavior, only the question, so nothing leaks to the client.

CSV columns:  case_id, question, answer, contexts
`contexts` is optional. Several contexts go in one cell separated by " ||| ".
If it is empty, the answer is treated as black-box (contexts=None).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from audit.targets.base import Target, TargetResponse

COLUMNS = ["case_id", "question", "answer", "contexts"]
CONTEXT_SEP = " ||| "


def cases_to_pairs(cases: Iterable) -> list[tuple[str, str]]:
    """Turn TestCase objects (or dicts) into (case_id, question) pairs."""
    pairs = []
    for c in cases:
        if isinstance(c, dict):
            pairs.append((str(c["id"]), c["question"]))
        else:
            pairs.append((str(c.id), c.question))
    return pairs


def export_questions(pairs: Iterable[tuple[str, str]], path: str | Path) -> int:
    """Write the CSV we send to the client. Returns the number of rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # utf-8-sig so Excel opens accents and symbols correctly
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for case_id, question in pairs:
            writer.writerow([case_id, question, "", ""])
            count += 1
    return count


class FileTarget(Target):
    def __init__(self, rows: dict[str, dict], name: str = "file_bot", source: str = ""):
        self.rows = rows                       # case_id -> {"question", "answer", "contexts"}
        self.name = name
        self.source = source
        # lets answer(question) work too, for runners that only pass the question
        self._by_question = {}
        for case_id, row in rows.items():
            self._by_question.setdefault(row["question"].strip(), case_id)

    @classmethod
    def from_csv(cls, path: str | Path, name: str = "file_bot") -> "FileTarget":
        path = Path(path)
        rows: dict[str, dict] = {}
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = {"case_id", "question", "answer"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path} is missing columns: {sorted(missing)}")
            for r in reader:
                case_id = (r.get("case_id") or "").strip()
                if not case_id:
                    continue
                rows[case_id] = {
                    "question": (r.get("question") or "").strip(),
                    "answer": (r.get("answer") or "").strip(),
                    "contexts": (r.get("contexts") or "").strip(),
                }
        return cls(rows, name=name, source=str(path))

    def answer_for(self, case_id: str) -> TargetResponse:
        """Look an answer up by case id (the main way to use this target)."""
        row = self.rows.get(str(case_id))
        if row is None:
            return TargetResponse(error=f"case_id '{case_id}' not found in {self.source}")
        if not row["answer"]:
            return TargetResponse(error=f"no answer filled in for case_id '{case_id}'")
        contexts = [c.strip() for c in row["contexts"].split(CONTEXT_SEP) if c.strip()]
        return TargetResponse(answer=row["answer"], contexts=contexts or None)

    def answer(self, question: str) -> TargetResponse:
        """Same lookup, but by question text, for runners that pass only the question."""
        case_id = self._by_question.get(question.strip())
        if case_id is None:
            return TargetResponse(error="question not found in the answers file")
        return self.answer_for(case_id)

    def missing_case_ids(self) -> list[str]:
        """Case ids the client hasn't answered yet. Check this before running the audit."""
        return [cid for cid, row in self.rows.items() if not row["answer"]]

    def config_snapshot(self) -> dict:
        return {"type": "file", "source": self.source, "cases": len(self.rows)}