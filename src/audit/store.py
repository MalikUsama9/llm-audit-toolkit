"""SQLite store: runs, cases, results, scores.

One database file holds everything for an audit, so runs can be compared later.
Rows go in and out as the Pydantic models from models.py.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from audit.models import Result, Run, Score, TestCase

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    target_name     TEXT NOT NULL,
    config_snapshot TEXT NOT NULL DEFAULT '{}',   -- JSON
    created_at      TEXT NOT NULL,                -- ISO timestamp
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    id                TEXT PRIMARY KEY,
    category          TEXT NOT NULL,
    question          TEXT NOT NULL,
    reference_answer  TEXT,
    source_ref        TEXT,                       -- JSON list, or NULL
    expected_behavior TEXT NOT NULL,
    difficulty        TEXT NOT NULL,
    source_text       TEXT,
    origin            TEXT NOT NULL DEFAULT 'generated',
    reviewed          INTEGER NOT NULL DEFAULT 0,
    split             TEXT
);

CREATE TABLE IF NOT EXISTS results (
    run_id        TEXT NOT NULL REFERENCES runs(run_id),
    case_id       TEXT NOT NULL REFERENCES cases(id),
    answer        TEXT,
    contexts      TEXT,                           -- JSON list, or NULL
    latency_ms    REAL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    error         TEXT,
    PRIMARY KEY (run_id, case_id)
);

CREATE TABLE IF NOT EXISTS scores (
    run_id      TEXT NOT NULL,
    case_id     TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    reasoning   TEXT,
    judge_model TEXT,
    PRIMARY KEY (run_id, case_id, metric),
    FOREIGN KEY (run_id, case_id) REFERENCES results(run_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_scores_run  ON scores(run_id);
"""

# Columns added to `cases` after the first version of the schema.
# Used to upgrade a database file that was created before they existed.
_NEW_CASE_COLUMNS = {
    "source_text": "TEXT",
    "origin": "TEXT NOT NULL DEFAULT 'generated'",
    "reviewed": "INTEGER NOT NULL DEFAULT 0",
    "split": "TEXT",
}


class Store:
    def __init__(self, db_path: str = "data/audit.db"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        self.lock = threading.Lock()

    def _migrate(self) -> None:
        """Add any missing columns to an older `cases` table."""
        existing = {row["name"] for row in self.db.execute("PRAGMA table_info(cases)")}
        for name, definition in _NEW_CASE_COLUMNS.items():
            if name not in existing:
                self.db.execute(f"ALTER TABLE cases ADD COLUMN {name} {definition}")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ---------- runs ----------
    def add_run(self, run: Run) -> None:
        self._write(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (run.run_id, run.target_name, json.dumps(run.config_snapshot),
             run.created_at.isoformat(), run.notes))

    def get_run(self, run_id: str) -> Run | None:
        row = self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))
        return self._row_to_run(row) if row else None

    def list_runs(self) -> list[Run]:
        return [self._row_to_run(r) for r in
                self._all("SELECT * FROM runs ORDER BY created_at")]

    # ---------- cases ----------
    def add_cases(self, cases: list[TestCase]) -> None:
        """Insert cases; an existing case with the same id is replaced."""
        rows = [
            (c.id, c.category, c.question, c.reference_answer,
             json.dumps(c.source_ref) if c.source_ref is not None else None,
             c.expected_behavior.value, c.difficulty.value,
             c.source_text, c.origin.value, int(c.reviewed),
             c.split.value if c.split is not None else None)
            for c in cases
        ]
        with self.lock:
            self.db.executemany(
                "INSERT OR REPLACE INTO cases "
                "(id, category, question, reference_answer, source_ref, "
                "expected_behavior, difficulty, source_text, origin, reviewed, split) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                rows)
            self.db.commit()

    def get_cases(self, category: str | None = None) -> list[TestCase]:
        if category:
            rows = self._all("SELECT * FROM cases WHERE category=? ORDER BY id", (category,))
        else:
            rows = self._all("SELECT * FROM cases ORDER BY id")
        out = []
        for row in rows:
            d = dict(row)
            d["source_ref"] = self._parse_source_ref(d["source_ref"])
            d["reviewed"] = bool(d["reviewed"])
            out.append(TestCase(**d))
        return out

    # ---------- results ----------
    def add_result(self, r: Result) -> None:
        """Insert a result; re-running the same case in the same run replaces it."""
        self._write(
            "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?)",
            (r.run_id, r.case_id, r.answer,
             json.dumps(r.contexts) if r.contexts is not None else None,
             r.latency_ms, r.input_tokens, r.output_tokens, r.error))

    def get_results(self, run_id: str) -> list[Result]:
        rows = self._all("SELECT * FROM results WHERE run_id=? ORDER BY case_id", (run_id,))
        out = []
        for row in rows:
            d = dict(row)
            d["contexts"] = json.loads(d["contexts"]) if d["contexts"] else None
            out.append(Result(**d))
        return out

    def done_case_ids(self, run_id: str) -> set[str]:
        """Cases already answered without error. Lets the runner resume a run."""
        rows = self._all(
            "SELECT case_id FROM results WHERE run_id=? AND error IS NULL", (run_id,))
        return {r["case_id"] for r in rows}

    # ---------- scores ----------
    def add_score(self, s: Score) -> None:
        """Insert a score; re-scoring the same metric replaces the old one."""
        self._write(
            "INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?)",
            (s.run_id, s.case_id, s.metric, s.value, s.reasoning, s.judge_model))

    def get_scores(self, run_id: str, metric: str | None = None) -> list[Score]:
        if metric:
            rows = self._all(
                "SELECT * FROM scores WHERE run_id=? AND metric=? ORDER BY case_id",
                (run_id, metric))
        else:
            rows = self._all("SELECT * FROM scores WHERE run_id=? ORDER BY case_id, metric",
                             (run_id,))
        return [Score(**dict(r)) for r in rows]

    # ---------- helpers ----------
    def _write(self, sql: str, params: tuple) -> None:
        with self.lock:
            self.db.execute(sql, params)
            self.db.commit()

    def _one(self, sql: str, params: tuple = ()):
        with self.lock:
            return self.db.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()):
        with self.lock:
            return self.db.execute(sql, params).fetchall()

    @staticmethod
    def _parse_source_ref(raw: str | None) -> list[str] | None:
        """Read source_ref back as a list.

        New rows hold a JSON list. Rows saved before this change hold a plain
        string like 'policy.md#1', which becomes a one-item list.
        """
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
        if isinstance(value, list):
            return value
        return [raw]

    @staticmethod
    def _row_to_run(row) -> Run:
        return Run(run_id=row["run_id"], target_name=row["target_name"],
                   config_snapshot=json.loads(row["config_snapshot"]),
                   created_at=datetime.fromisoformat(row["created_at"]),
                   notes=row["notes"])