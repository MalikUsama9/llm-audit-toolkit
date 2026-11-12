from src.audit.checks import run_checks, SKIP_JUDGE_STATUSES


def test_empty():
    assert run_checks("").status == "empty"
    assert run_checks(None).status == "empty"
    assert run_checks("   ").status == "empty"


def test_bot_error():
    assert run_checks("anything", bot_error="timeout").status == "error"


def test_error_text():
    assert run_checks("Error: rate limit exceeded").status == "error"


def test_refusal():
    assert run_checks("I'm sorry, but I cannot answer that.").status == "refusal"
    assert run_checks("This is not mentioned in the provided context.").status == "refusal"


def test_refusal_real_bot_wording():
    assert run_checks("I don't have that information. Please contact support.").status == "refusal"


def test_refusal_curly_apostrophe():
    assert run_checks("I don\u2019t have that information.").status == "refusal"


def test_partial_answer():
    r = run_checks("Returns take 14 days [1]. I don't have that information about exchanges.")
    assert r.status == "partial"
    assert r.has_citation is True


def test_normal_answer():
    r = run_checks("The refund window is 30 days [1].")
    assert r.status == "ok" and r.has_citation


def test_false_positive_guard():
    # long normal answer containing error-like words must not be flagged as an error
    long = "The system retries after a connection refused message when the disk is full. " * 10
    assert len(long) > 300
    assert run_checks(long).status == "ok"


def test_skip_judge_statuses():
    assert {"empty", "error"} <= SKIP_JUDGE_STATUSES
    assert "refusal" not in SKIP_JUDGE_STATUSES