import asyncio
from types import SimpleNamespace

from audit.runner import run_audit
from audit.store import Store
from audit.targets.base import Target, TargetResponse


class FakeTarget(Target):
    name = "fake"

    def __init__(self):
        self.calls = {}

    def answer(self, question):
        n = self.calls[question] = self.calls.get(question, 0) + 1
        if question == "boom":
            raise RuntimeError("bad")
        if question == "empty":
            return TargetResponse(answer="   ")
        if question == "flaky" and n < 2:
            return TargetResponse(error="rate limit")
        return TargetResponse(answer="fine")


def test_runner_handles_failures_and_resumes():
    store = Store(":memory:")
    store.db.execute("PRAGMA foreign_keys = OFF")    # test uses fake cases, not stored ones
    cases = [SimpleNamespace(id=q, question=q) for q in ("ok", "boom", "empty", "flaky")]
    target = FakeTarget()

    summary = asyncio.run(run_audit(store, target, cases, run_id="r1",
                                    max_retries=2, base_delay=0.01))
    res = {r.case_id: r for r in store.get_results("r1")}

    assert res["ok"].error is None
    assert res["flaky"].error is None                # succeeded on the 2nd try
    assert res["boom"].error.startswith("error")
    assert res["empty"].error == "empty_answer"
    assert summary["attempted"] == 4

    asyncio.run(run_audit(store, target, cases, run_id="r1",
                          max_retries=0, base_delay=0.01))
    assert target.calls["ok"] == 1                   # not asked again
    assert target.calls["flaky"] == 2                # not asked again