from audit.compare import _build_cell

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
