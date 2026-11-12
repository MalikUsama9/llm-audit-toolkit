import json
from types import SimpleNamespace

from src.audit.judge import judge_case, judge_with_checks

CFG = SimpleNamespace(model="test-model", temperature=0.0, max_tokens=800)
RUBRIC = {
    "name": "faithfulness",
    "version": "1.0",
    "labels": {k: {"definition": "d", "borderline": "b"}
               for k in ("supported", "contradicted", "not_in_source")},
    "rules": [],
}


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, **kw):
        self.calls += 1
        return self.replies.pop(0)


def reply(verdict, claim_status=None):
    claims = [] if claim_status is None else [
        {"claim": "c", "status": claim_status, "evidence": "e"}]
    return json.dumps({"claims": claims, "reasoning": "r", "verdict": verdict})


def run(client, answer, bot_error=None):
    return judge_with_checks(client, CFG, RUBRIC, "t", "Q?", "ref", "src",
                             answer, bot_error=bot_error)


# ---- known correct / known wrong / refusal
def test_correct_answer():
    c = FakeClient([reply("supported", "supported")])
    check, res = run(c, "Returns are accepted within 30 days [1].")
    assert check.status == "ok"
    assert res.output.verdict == "supported"
    assert res.hallucinated is False


def test_wrong_answer():
    c = FakeClient([reply("contradicted", "contradicted")])
    check, res = run(c, "Returns are accepted within 90 days [1].")
    assert res.output.verdict == "contradicted"
    assert res.hallucinated is True


def test_refusal_is_flagged_and_not_a_hallucination():
    c = FakeClient([reply("supported")])          # no claims made
    check, res = run(c, "I don't have that information. Please contact support.")
    assert check.status == "refusal"
    assert res.hallucinated is False


# ---- deliberately broken answers
def test_empty_answer_skips_judge():
    for bad in ("", "   ", None):
        c = FakeClient([])
        check, res = run(c, bad)
        assert check.status == "empty" and res is None and c.calls == 0


def test_bot_error_skips_judge():
    c = FakeClient([])
    check, res = run(c, "x", bot_error="timeout")
    assert check.status == "error" and res is None and c.calls == 0


def test_error_text_skips_judge():
    c = FakeClient([])
    check, res = run(c, "Error: request timed out")
    assert check.status == "error" and res is None and c.calls == 0


# ---- broken judge output
def test_garbage_judge_output_returns_none_after_one_retry():
    c = FakeClient(["not json", "still not json"])
    _, res = run(c, "Paris [1].")
    assert res is None and c.calls == 2


def test_invalid_verdict_label_rejected():
    c = FakeClient([reply("maybe", "supported"), reply("maybe", "supported")])
    _, res = run(c, "Paris [1].")
    assert res is None


def test_missing_keys_rejected():
    bad = json.dumps({"verdict": "supported"})
    c = FakeClient([bad, bad])
    _, res = run(c, "Paris [1].")
    assert res is None


def test_fenced_json_is_accepted():
    c = FakeClient(["```json\n" + reply("supported", "supported") + "\n```"])
    _, res = run(c, "Paris [1].")
    assert res is not None and res.output.verdict == "supported"


def test_one_bad_reply_then_good_reply_recovers():
    c = FakeClient(["oops", reply("supported", "supported")])
    _, res = run(c, "Paris [1].")
    assert res is not None and c.calls == 2