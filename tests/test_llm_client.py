"""Tests use a fake litellm, so they cost nothing and need no API key."""
from types import SimpleNamespace

import pytest

from audit.llm import client as client_mod
from audit.llm.client import BudgetExceeded, LLMClient

MSGS = [{"role": "user", "content": "Say hi"}]


def fake_response(text="hi"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2))


@pytest.fixture
def llm(tmp_path, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)  # no real waiting
    monkeypatch.setattr(client_mod.litellm, "completion_cost", lambda **kw: 0.001)
    return LLMClient(db_path=str(tmp_path / "t.db"), budget_usd=1.0)


def test_second_identical_call_hits_cache(llm, monkeypatch):
    calls = []
    monkeypatch.setattr(client_mod.litellm, "completion",
                        lambda **kw: calls.append(1) or fake_response())
    a = llm.complete(MSGS, "fake/model")
    b = llm.complete(MSGS, "fake/model")
    assert len(calls) == 1
    assert not a.cached and b.cached and b.cost_usd == 0.0
    assert a.text == b.text == "hi"


def test_use_cache_false_calls_again(llm, monkeypatch):
    calls = []
    monkeypatch.setattr(client_mod.litellm, "completion",
                        lambda **kw: calls.append(1) or fake_response())
    llm.complete(MSGS, "fake/model")
    llm.complete(MSGS, "fake/model", use_cache=False)
    assert len(calls) == 2


def test_retries_then_succeeds(llm, monkeypatch):
    state = {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if state["n"] < 3:
            raise ConnectionError("boom")
        return fake_response("ok")

    monkeypatch.setattr(client_mod.litellm, "completion", flaky)
    assert llm.complete(MSGS, "fake/model").text == "ok"
    assert state["n"] == 3


def test_gives_up_after_retries(llm, monkeypatch):
    def always_fail(**kw):
        raise ConnectionError("down")
    monkeypatch.setattr(client_mod.litellm, "completion", always_fail)
    with pytest.raises(ConnectionError):
        llm.complete(MSGS, "fake/model", retries=2)


def test_tokens_cost_latency_are_logged(llm, monkeypatch):
    monkeypatch.setattr(client_mod.litellm, "completion", lambda **kw: fake_response())
    llm.complete(MSGS, "fake/model")
    row = llm.db.execute(
        "SELECT input_tokens, output_tokens, cost_usd, latency_ms, cached FROM call_log"
    ).fetchone()
    assert row[0] == 5 and row[1] == 2 and row[2] == 0.001
    assert row[3] >= 0 and row[4] == 0


def test_budget_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(client_mod.litellm, "completion_cost", lambda **kw: 0.5)
    monkeypatch.setattr(client_mod.litellm, "completion", lambda **kw: fake_response())
    llm = LLMClient(db_path=str(tmp_path / "b.db"), budget_usd=0.4)
    llm.complete(MSGS, "fake/model")          # spends 0.5, now over budget
    with pytest.raises(BudgetExceeded):
        llm.complete([{"role": "user", "content": "different"}], "fake/model")