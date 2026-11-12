import pytest
from pydantic import ValidationError

from audit.models import Run, Score, TestCase, Result

    
def test_valid_answerable_case():
    c = TestCase(id="q1", category="factual", question="What is the refund window?",
                 reference_answer="30 days", source_ref="refund_policy.md#2")
    assert c.expected_behavior == "answer"
    assert c.difficulty == "medium"


def test_answerable_case_requires_source():
    with pytest.raises(ValidationError):
        TestCase(id="q2", category="factual", question="Hi?", reference_answer="x")


def test_refuse_case_needs_no_source():
    c = TestCase(id="q3", category="off_topic", question="Who won the cricket match?",
                 expected_behavior="refuse")
    assert c.source_ref is None


def test_bad_behavior_rejected():
    with pytest.raises(ValidationError):
        TestCase(id="q4", category="x", question="?", expected_behavior="maybe")


def test_json_roundtrip():
    c = TestCase(id="q5", category="factual", question="Q?", reference_answer="A",
                 source_ref="doc#1")
    assert TestCase.model_validate_json(c.model_dump_json()) == c


def test_result_score_run_defaults():
    r = Result(run_id="r1", case_id="q1", answer="30 days", latency_ms=420.5)
    s = Score(run_id="r1", case_id="q1", metric="correctness", value=1.0)
    run = Run(run_id="r1", target_name="my_rag_bot")
    assert r.error is None and s.judge_model is None
    assert run.created_at is not None