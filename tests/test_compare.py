import sqlite3

from audit.compare import _build_cell, _percentile, caveat_notes, run_stats


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