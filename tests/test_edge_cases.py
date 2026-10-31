from audit.edge_cases import build_cases


def test_edge_case_counts():
    cases = build_cases()
    counts = {}
    for c in cases:
        counts[c.category] = counts.get(c.category, 0) + 1
    assert counts == {"unanswerable": 15, "off_topic": 10, "adversarial": 10, "ambiguous": 8}
    assert len({c.id for c in cases}) == len(cases)