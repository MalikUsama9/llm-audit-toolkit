import json
import sqlite3

import pytest

from audit.compare import (
    _build_cell, _percentile, caveat_notes, compare_runs, config_diff, run_stats,
)
from audit.reporting.stats import (
    flip_counts, paired_bootstrap_delta, paired_flip_test,
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


# ================================================================
# Day 10 step 4: bootstrap + flip test, adapted to this repo's API
#   paired_bootstrap_delta(before, after) -> (low, high)
#   paired_flip_test(fixed, broken)       -> p-value
#   flip_counts(a_by_id, b_by_id)         -> (fixed, broken)
# ================================================================
BEFORE = [0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0]
AFTER = [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0]   # improves 3 cases, regresses none


def _counts(before, after):
    """Turn two 0/1 lists into (fixed, broken) via the real flip_counts."""
    a = {f"c{i}": bool(v) for i, v in enumerate(before)}
    b = {f"c{i}": bool(v) for i, v in enumerate(after)}
    return flip_counts(a, b)


# ---------- paired bootstrap ----------
def test_cell_observed_delta_and_interval_contain_it():
    pairs = [(f"c{i}", x, y) for i, (x, y) in enumerate(zip(BEFORE, AFTER))]
    cell = _build_cell("correctness", "ALL", pairs)
    assert cell.delta == pytest.approx(sum(AFTER) / 12 - sum(BEFORE) / 12)   # 0.25
    lo, hi = cell.delta_ci
    assert lo <= cell.delta <= hi


def test_bootstrap_interval_not_zero_width():
    lo, hi = paired_bootstrap_delta(BEFORE, AFTER)
    assert hi > lo                          # the roadmap's key requirement


def test_bootstrap_reproducible():
    assert paired_bootstrap_delta(BEFORE, AFTER) == paired_bootstrap_delta(BEFORE, AFTER)


def test_bootstrap_identical_runs_contain_zero():
    lo, hi = paired_bootstrap_delta(BEFORE, BEFORE)
    assert lo <= 0 <= hi                    # zero-width is legit here


def test_bootstrap_is_actually_paired():
    # Opposite per-item changes cancel: the mean delta is 0, so the CI must straddle 0.
    a = [1, 0, 1, 0, 1, 0]
    b = [0, 1, 0, 1, 0, 1]
    lo, hi = paired_bootstrap_delta(a, b)
    assert lo < 0 < hi
    assert _counts(a, b) == (3, 3)


# ---------- flip test ----------
def test_flip_all_improved_known_p():
    # 5 pairs, all fixed, none broken: exact two-sided p = 2 / 2**5 = 0.0625
    fixed, broken = _counts([0] * 5, [1] * 5)
    assert (fixed, broken) == (5, 0)
    assert paired_flip_test(fixed, broken) == pytest.approx(0.0625)


def test_flip_no_difference_gives_p_one():
    fixed, broken = _counts(BEFORE, BEFORE)
    assert (fixed, broken) == (0, 0)
    assert paired_flip_test(fixed, broken) == pytest.approx(1.0)


def test_flip_symmetric():
    fwd = paired_flip_test(*_counts(BEFORE, AFTER))     # (3, 0)
    back = paired_flip_test(*_counts(AFTER, BEFORE))    # (0, 3)
    assert fwd == pytest.approx(back)


def test_flip_noisy_example_not_significant():
    before = [1, 0, 1, 0, 1, 0, 1, 0]
    after = [1, 1, 1, 0, 0, 0, 1, 0]        # one fixed, one broken: net 0
    fixed, broken = _counts(before, after)
    assert (fixed, broken) == (1, 1)
    assert paired_flip_test(fixed, broken) > 0.5