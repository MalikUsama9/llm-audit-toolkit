import sqlite3

import pytest

from audit.models import Result, Run, Score, TestCase
from audit.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "audit.db"))
    s.add_run(Run(run_id="r1", target_name="my_bot", config_snapshot={"model": "x"}))
    s.add_cases([
        TestCase(id="q1", category="factual", question="Refund window?",
                 reference_answer="30 days", source_ref="policy.md#1"),
        TestCase(id="q2", category="off_topic", question="Who won the match?",
                 expected_behavior="refuse"),
    ])
    return s


def test_four_tables_exist(store):
    names = {r[0] for r in store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "cases", "results", "scores"} <= names


def test_run_roundtrip(store):
    run = store.get_run("r1")
    assert run.target_name == "my_bot" and run.config_snapshot == {"model": "x"}
    assert len(store.list_runs()) == 1
    assert store.get_run("nope") is None


def test_cases_roundtrip_and_filter(store):
    assert [c.id for c in store.get_cases()] == ["q1", "q2"]
    assert [c.id for c in store.get_cases(category="off_topic")] == ["q2"]
    assert store.get_cases()[1].expected_behavior == "refuse"


def test_result_roundtrip_with_contexts(store):
    store.add_result(Result(run_id="r1", case_id="q1", answer="30 days",
                            contexts=["chunk a", "chunk b"], latency_ms=120.0,
                            input_tokens=10, output_tokens=4))
    r = store.get_results("r1")[0]
    assert r.contexts == ["chunk a", "chunk b"] and r.output_tokens == 4


def test_rerun_replaces_result(store):
    store.add_result(Result(run_id="r1", case_id="q1", error="timeout"))
    assert store.done_case_ids("r1") == set()           # errored case is not "done"
    store.add_result(Result(run_id="r1", case_id="q1", answer="30 days"))
    assert len(store.get_results("r1")) == 1
    assert store.done_case_ids("r1") == {"q1"}


def test_scores_roundtrip_and_replace(store):
    store.add_result(Result(run_id="r1", case_id="q1", answer="30 days"))
    store.add_score(Score(run_id="r1", case_id="q1", metric="correctness", value=0.5))
    store.add_score(Score(run_id="r1", case_id="q1", metric="correctness", value=1.0,
                          reasoning="matches", judge_model="gemini"))
    scores = store.get_scores("r1")
    assert len(scores) == 1 and scores[0].value == 1.0
    assert store.get_scores("r1", metric="faithfulness") == []


def test_foreign_keys_enforced(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.add_result(Result(run_id="missing_run", case_id="q1", answer="x"))
    with pytest.raises(sqlite3.IntegrityError):
        store.add_score(Score(run_id="r1", case_id="q1", metric="m", value=1.0))