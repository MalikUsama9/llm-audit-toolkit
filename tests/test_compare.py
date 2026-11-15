from audit.compare import _build_cell, caveat_notes


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