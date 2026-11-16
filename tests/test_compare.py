import json
import sqlite3

from audit.compare import (
    _build_cell, _percentile, caveat_notes, compare_runs, config_diff, run_stats,
)


# ---------------------------------------------------------------- cell maths
def test_fixed_and_broken_detected():
    pairs = [("c1", 0, 1), ("c2", 1, 0), ("c3", 1, 1), ("c4", 0, 0)]
    cell = _build_cell("correctness", "ALL", pairs)
    assert cell.fixed == ["c1"] and cell.broken == ["c2"]
    assert cell.delta == 0.0 and cell.n == 4


def test_small_sample_flagged():
    cell = _build_cell("correctness", "facts", [("c1", 0, 1)] * 5)
    assert "too small" in cell.caveat


def test_no_change_gives_zero_delta():
    pairs = [("c1", 1, 1), ("c2", 0, 0), ("c3", 1, 1)]
    cell = _build_cell("correctness", "ALL", pairs)
    assert cell.delta == 0 and cell.fixed == [] and cell.broken == []


def test_caveat_notes_small_sample():
    pairs = [(f"c{i}", i % 2, 1) for i in range(10)]
    cell = _build_cell("correctness", "ALL", pairs)
    small = _build_cell("correctness", "facts", pairs[:5])
    notes = caveat_notes({"cells": [cell, small]})
    assert any("n = 10" in n for n in notes)
    assert any("Indicative only" in n and "facts" in n for n in notes)


# ---------------------------------------------------------------- run stats
def test_percentile_basic():
    assert _percentile([10, 20, 30, 40], 50) == 25
    assert _percentile([], 95) is None
    assert _percentile([7], 95) == 7


def test_run_stats_counts_errors_separately():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE results (run_id, case_id, answer, latency_ms, input_tokens, output_tokens, error)")
    db.executemany("INSERT INTO results VALUES (?,?,?,?,?,?,?)", [
        ("r1", "c1", "hi", 100, 10, 5, None),
        ("r1", "c2", "hi", 300, 10, 5, None),
        ("r1", "c3", "", 0, 10, 0, "timeout"),
    ])
    s = run_stats(db, "r1")
    assert s["n"] == 3 and s["errors"] == 1 and s["n_ok"] == 2
    assert s["p50"] == 200          # errors excluded from latency
    assert s["in_tok"] == 30


# ---------------------------------------------------------------- end to end
def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE runs (run_id, config_snapshot);
    CREATE TABLE cases (id, category);
    CREATE TABLE results (run_id, case_id, answer, latency_ms, input_tokens, output_tokens, error);
    CREATE TABLE scores (run_id, case_id, metric, value, reasoning);
    """)
    db.executemany("INSERT INTO runs VALUES (?,?)", [
        ("A", json.dumps({"prompt_version": "v1", "temperature": 0.0})),
        ("B", json.dumps({"prompt_version": "v2", "temperature": 0.0})),
    ])
    # case, category, A value, B value, B error
    data = [
        ("c1", "facts", 0, 1, None),        # fixed
        ("c2", "facts", 1, 0, None),        # broken
        ("c3", "facts", 1, 1, None),        # stable right
        ("c4", "numbers", 0, 0, None),      # stable wrong
        ("c5", "numbers", 1, 1, "timeout"), # errored in B: excluded, not counted as wrong
    ]
    for cid, cat, va, vb, err in data:
        db.execute("INSERT INTO cases VALUES (?,?)", (cid, cat))
        db.execute("INSERT INTO results VALUES ('A',?,'ans',100,10,5,NULL)", (cid,))
        db.execute("INSERT INTO results VALUES ('B',?,?,100,10,5,?)", (cid, "" if err else "ans", err))
        db.execute("INSERT INTO scores VALUES ('A',?, 'correctness', ?, 'r')", (cid, va))
        db.execute("INSERT INTO scores VALUES ('B',?, 'correctness', ?, 'r')", (cid, vb))
    # a case that exists only in A
    db.execute("INSERT INTO cases VALUES ('c6','facts')")
    db.execute("INSERT INTO results VALUES ('A','c6','ans',100,10,5,NULL)")
    db.execute("INSERT INTO scores VALUES ('A','c6','correctness',1,'r')")
    return db


def test_compare_runs_flip_lists():
    res = compare_runs(make_db(), "A", "B")
    overall = next(c for c in res["cells"] if c.metric == "correctness" and c.category == "ALL")
    assert overall.fixed == ["c1"]
    assert overall.broken == ["c2"]
    assert overall.n == 4                      # c5 (error) and c6 (unpaired) are not counted


def test_errors_are_reported_separately_not_as_wrong():
    res = compare_runs(make_db(), "A", "B")
    assert res["errors"]["correctness"]["b"] == 1
    overall = next(c for c in res["cells"] if c.category == "ALL")
    assert "c5" not in overall.fixed + overall.broken


def test_unpaired_cases_are_counted():
    res = compare_runs(make_db(), "A", "B")
    assert res["unpaired"]["only_in_a"] == 1


def test_per_category_rows_exist():
    res = compare_runs(make_db(), "A", "B")
    cats = {c.category for c in res["cells"]}
    assert {"ALL", "facts", "numbers"} <= cats


def test_same_run_has_zero_delta_and_no_flips():
    res = compare_runs(make_db(), "A", "A")
    for c in res["cells"]:
        assert c.delta == 0 and c.fixed == [] and c.broken == []


def test_result_is_the_same_every_time():
    """Same two runs must give the same CIs and the same case order."""
    first = compare_runs(make_db(), "A", "B")["cells"]
    second = compare_runs(make_db(), "A", "B")["cells"]
    assert [(c.category, c.delta_ci, c.fixed, c.broken) for c in first] == \
           [(c.category, c.delta_ci, c.fixed, c.broken) for c in second]


# ---------------------------------------------------------------- config diff
def test_config_diff_reports_only_changes():
    diff = config_diff(make_db(), "A", "B")
    assert len(diff) == 1 and "prompt_version" in diff[0]