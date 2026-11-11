from audit.checks import run_checks

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

def test_normal_answer():
    r = run_checks("The refund window is 30 days [1].")
    assert r.status == "ok" and r.has_citation

def test_false_positive_guard():
    # a normal answer that merely contains the word "error" must not be flagged
    long = "The system logs an error when the disk is full, and then it retries. " * 10
    assert run_checks(long).status == "ok"