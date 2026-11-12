"""
judge.py  ->  put this in src/audit/judge.py

An LLM judge that scores one bot answer against one rubric.

Design rules (from the assignment):
  - The schema puts `claims` BEFORE `verdict` so the judge checks facts first.
  - One retry with use_cache=False. If it still fails, return None and log
    "judge_failure".
  - Temperature is 0 (or near it). Judge model, rubric version and settings
    are logged on every run.
  - The hallucination flag is computed HERE from the claim statuses. The judge
    never decides it.
  - Deterministic checks run BEFORE the judge. Empty and error answers skip the
    judge and are reported with their own status, never scored as "wrong".
"""
import inspect
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ValidationError

from .checks import CheckResult, SKIP_JUDGE_STATUSES, run_checks

log = logging.getLogger("audit.judge")

Status = Literal["supported", "contradicted", "not_in_source"]

_WARNED_NO_CACHE_BYPASS = False


# ---------------------------------------------------------------- schema
class Claim(BaseModel):
    claim: str
    status: Status
    evidence: str = ""


class JudgeOutput(BaseModel):
    # Field order matters: claims first, reasoning next, verdict LAST.
    claims: list[Claim]
    reasoning: str
    verdict: str


@dataclass
class JudgeResult:
    output: JudgeOutput
    hallucinated: bool              # derived in code, never from the judge
    judge_model: str
    rubric_name: str
    rubric_version: str
    temperature: float
    evidence_unverified: int = 0    # claims whose evidence quote was not found


def hallucination_flag(claims: list[Claim]) -> bool:
    """True if ANY claim is not supported (contradicted or not_in_source)."""
    return any(c.status != "supported" for c in claims)


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def count_unverified_evidence(claims: list[Claim], source: str, reference: str) -> int:
    """
    Count claims whose evidence quote cannot be found in the source/reference.
    "not_in_source" claims are skipped (they legitimately have no evidence).
    A supported/contradicted claim with empty evidence also counts as unverified.
    """
    haystack = _norm(f"{source or ''}\n{reference or ''}")
    n = 0
    for c in claims:
        if c.status == "not_in_source":
            continue
        ev = _norm(c.evidence)
        if not ev or ev not in haystack:
            n += 1
    return n


# ---------------------------------------------------------------- helpers
def strip_fences(text: str) -> str:
    """Remove ```json fences and any text around the JSON object."""
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            t = t[start:end + 1]
    return t


def load_rubric(name: str, rubric_dir: str = "configs/rubrics") -> dict:
    path = Path(rubric_dir) / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Rubric file not found: {path.resolve()}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- prompts
def build_system_prompt(rubric: dict) -> str:
    lines = [
        f"You are a strict evaluator. Metric: {rubric['name']}.",
        f"Applies to: {rubric.get('applies_to', 'all cases')}.",
        "",
        "RULES",
    ]
    lines += [f"- {r}" for r in rubric.get("rules", [])]

    lines += ["", "LABELS"]
    for label, body in rubric["labels"].items():
        lines.append(f"- {label}: {body['definition']}")
        lines.append(f"  Borderline: {body['borderline']}")

    lines += [
        "",
        "OUTPUT FORMAT",
        "Reply with ONLY one JSON object and nothing else (no markdown fences).",
        'Keys in this order: "claims", "reasoning", "verdict".',
        '"claims" is a list of {"claim": str, "status": '
        '"supported"|"contradicted"|"not_in_source", "evidence": str}.',
        "A claim is a factual statement about the world. Do NOT list refusals "
        "(for example 'I don't have that information'), apologies, greetings or "
        "offers of help as claims.",
        '"evidence" must be a VERBATIM quote copied from the source excerpt '
        "or reference answer (empty string for not_in_source).",
        f'"verdict" must be exactly one of: {sorted(rubric["labels"])}.',
        "List and check the claims BEFORE you decide the verdict.",
    ]

    shots = rubric.get("few_shot") or []
    if shots:
        lines += ["", "EXAMPLES"]
        for s in shots:
            lines.append(
                "Input:\n"
                f"Question: {s.get('question', '')}\n"
                f"Reference answer: {s.get('reference', '')}\n"
                f"Source excerpt: {s.get('source', '')}\n"
                f"Bot answer: {s.get('bot_answer', '')}"
            )
            example = {
                "claims": s.get("claims", []),
                "reasoning": s.get("reasoning", ""),
                "verdict": s.get("verdict", ""),
            }
            lines.append("Output:\n" + json.dumps(example, ensure_ascii=False))
            lines.append("")
    return "\n".join(lines)


def build_user_prompt(question: str, reference: str, source: str, answer: str) -> str:
    return (
        f"Question: {question}\n"
        f"Reference answer: {reference or '(none: unanswerable case)'}\n"
        f"Source excerpt: {source or '(none)'}\n"
        f"Bot answer: {answer}\n\n"
        "Return the JSON object now."
    )


# ---------------------------------------------------------------- LLM call
def _extract_text(resp) -> str:
    """Turn whatever the client returns into a plain string."""
    if isinstance(resp, str):
        return resp
    for attr in ("text", "content"):
        val = getattr(resp, attr, None)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, list):  # list of content blocks
            parts = []
            for b in val:
                if isinstance(b, dict):
                    parts.append(b.get("text") or "")
                else:
                    parts.append(getattr(b, "text", "") or "")
            joined = "".join(parts)
            if joined:
                return joined
    return ""


def _supports_use_cache(client) -> bool:
    params = inspect.signature(client.complete).parameters
    return "use_cache" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def _call_llm(client, cfg, system: str, user: str, use_cache: bool) -> str:
    """
    Calls client.complete(messages, model, temperature, max_tokens[, use_cache]).
    `use_cache` is only sent if the client accepts it. Returns the reply text.
    """
    global _WARNED_NO_CACHE_BYPASS
    kwargs = dict(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    if _supports_use_cache(client):
        kwargs["use_cache"] = use_cache
    elif not use_cache and not _WARNED_NO_CACHE_BYPASS:
        _WARNED_NO_CACHE_BYPASS = True
        log.warning(
            "judge_retry_cannot_bypass_cache: client.complete() has no "
            "use_cache argument, so the retry may replay the same cached reply"
        )
    return _extract_text(client.complete(**kwargs))


def _parse(raw: str, labels: set) -> JudgeOutput:
    data = json.loads(strip_fences(raw))
    out = JudgeOutput.model_validate(data)
    out.verdict = out.verdict.strip()
    if out.verdict not in labels:
        raise ValueError(f"verdict {out.verdict!r} not in {sorted(labels)}")
    return out


# ---------------------------------------------------------------- main API
def log_run_settings(cfg, rubrics: dict) -> None:
    """Call once at the start of every run."""
    versions = {name: r.get("version") for name, r in rubrics.items()}
    log.info(
        "judge_run judge_model=%s temperature=%s max_tokens=%s rubric_versions=%s",
        cfg.model, cfg.temperature, cfg.max_tokens, versions,
    )


def judge_case(
    client,
    cfg,
    rubric: dict,
    case_id: str,
    question: str,
    reference: str,
    source: str,
    answer: str,
) -> Optional[JudgeResult]:
    """Score one case. Returns None if the judge output could not be used."""
    system = build_system_prompt(rubric)
    user = build_user_prompt(question, reference, source, answer)
    labels = set(rubric["labels"])

    # Attempt 1 uses the cache. The single retry bypasses it.
    for attempt, use_cache in enumerate((True, False), start=1):
        raw = ""
        try:
            raw = _call_llm(client, cfg, system, user, use_cache)
            if not raw.strip():
                log.warning(
                    "judge_empty_reply case=%s metric=%s attempt=%d "
                    "(model may have used all max_tokens on reasoning; "
                    "consider raising judge.max_tokens)",
                    case_id, rubric["name"], attempt,
                )
            out = _parse(raw, labels)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            log.warning(
                "judge_parse_error case=%s metric=%s attempt=%d error=%s raw=%r",
                case_id, rubric["name"], attempt, e, str(raw)[:200],
            )
            continue
        # Any other error (BudgetExceeded, TypeError from a wrong argument,
        # network failure after the client's own retries) is NOT caught here,
        # so it stops the run instead of being retried and hidden.
        return JudgeResult(
            output=out,
            hallucinated=hallucination_flag(out.claims),
            judge_model=cfg.model,
            rubric_name=rubric["name"],
            rubric_version=str(rubric.get("version")),
            temperature=cfg.temperature,
            evidence_unverified=count_unverified_evidence(out.claims, source, reference),
        )

    log.error(
        "judge_failure case=%s metric=%s judge_model=%s rubric_version=%s",
        case_id, rubric["name"], cfg.model, rubric.get("version"),
    )
    return None


def judge_with_checks(
    client,
    cfg,
    rubric: dict,
    case_id: str,
    question: str,
    reference: str,
    source: str,
    answer: str,
    bot_error: Optional[str] = None,
) -> tuple[CheckResult, Optional[JudgeResult]]:
    """
    Run the deterministic checks first, then the judge only if the answer is usable.

    Returns (check, judge_result):
      - empty / error answers -> (check, None). The judge is NOT called, and the
        caller should store the check status as its own row, not as a score of 0.
      - everything else (ok, refusal, partial) -> (check, JudgeResult or None).
        judge_result is None only when the judge itself failed ("judge_failure").
    """
    check = run_checks(answer, bot_error=bot_error)
    if check.status in SKIP_JUDGE_STATUSES:
        log.info(
            "judge_skipped case=%s metric=%s check_status=%s detail=%s",
            case_id, rubric["name"], check.status, check.detail,
        )
        return check, None

    result = judge_case(
        client, cfg, rubric, case_id, question, reference, source, str(answer),
    )
    return check, result


# ---------------------------------------------------------------- offline test
if __name__ == "__main__":
    # Runs without any API call: python -m src.audit.judge
    from types import SimpleNamespace

    logging.basicConfig(level=logging.INFO)

    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('Here you go: {"a": 1} hope it helps') == '{"a": 1}'
    assert hallucination_flag([Claim(claim="x", status="supported")]) is False
    assert hallucination_flag([Claim(claim="x", status="not_in_source")]) is True

    # evidence verification
    cl = [Claim(claim="a", status="supported", evidence="Paris is the capital"),
          Claim(claim="b", status="supported", evidence="made up quote"),
          Claim(claim="c", status="not_in_source", evidence="")]
    assert count_unverified_evidence(cl, "Paris is the capital of France.", "") == 1

    # client reply shapes
    assert _extract_text("plain") == "plain"
    assert _extract_text(SimpleNamespace(content=[SimpleNamespace(text="blk")])) == "blk"
    assert _extract_text({"x": 1}) == ""

    rubric = {
        "name": "faithfulness", "version": "1.0",
        "labels": {k: {"definition": "d", "borderline": "b"}
                   for k in ("supported", "contradicted", "not_in_source")},
        "rules": ["Length is not quality.", "Material claims only."],
    }
    cfg = SimpleNamespace(model="test-model", temperature=0.0, max_tokens=800)

    # refusal rule is in the prompt
    assert "Do NOT list refusals" in build_system_prompt(rubric)

    class FakeClient:
        def __init__(self, replies): self.replies, self.calls = list(replies), []
        def complete(self, **kw):
            self.calls.append(kw["use_cache"]); return self.replies.pop(0)

    good = ('```json\n{"claims":[{"claim":"c","status":"not_in_source","evidence":""}],'
            '"reasoning":"r","verdict":"not_in_source"}\n```')

    # bad JSON first, good JSON on retry -> retry must use use_cache=False
    c = FakeClient(["not json", good])
    r = judge_case(c, cfg, rubric, "t1", "q", "ref", "src", "ans")
    assert r is not None and r.hallucinated is True and c.calls == [True, False]
    assert r.evidence_unverified == 0

    # two failures -> None
    c = FakeClient(["bad", "worse"])
    assert judge_case(c, cfg, rubric, "t2", "q", "ref", "src", "ans") is None

    # empty reply -> logged, retried, then judge_failure
    c = FakeClient(["", ""])
    assert judge_case(c, cfg, rubric, "t2b", "q", "ref", "src", "ans") is None

    # empty answer -> judge is NOT called, status reported as "empty"
    c = FakeClient([])
    chk, res = judge_with_checks(c, cfg, rubric, "t3", "q", "ref", "src", "")
    assert chk.status == "empty" and res is None and c.calls == []

    # bot error -> judge is NOT called, status reported as "error"
    c = FakeClient([])
    chk, res = judge_with_checks(c, cfg, rubric, "t4", "q", "ref", "src", "x", bot_error="timeout")
    assert chk.status == "error" and res is None and c.calls == []

    # normal answer -> judge IS called
    c = FakeClient([good])
    chk, res = judge_with_checks(c, cfg, rubric, "t5", "q", "ref", "src", "Paris [1].")
    assert chk.status == "ok" and res is not None and len(c.calls) == 1

    # client with NO use_cache argument
    class NoCacheClient:
        def __init__(self, replies): self.replies, self.n = list(replies), 0
        def complete(self, messages, model, temperature, max_tokens, retries=4):
            self.n += 1
            return SimpleNamespace(text=self.replies.pop(0))

    c = NoCacheClient([good])
    r = judge_case(c, cfg, rubric, "t6", "q", "ref", "src", "ans")
    assert r is not None and c.n == 1

    # a wrong-argument bug must NOT be hidden as judge_failure
    class BrokenClient:
        def complete(self, prompt):
            return "x"

    try:
        judge_case(BrokenClient(), cfg, rubric, "t7", "q", "ref", "src", "ans")
        raise SystemExit("expected TypeError")
    except TypeError:
        pass

    print("judge.py offline checks passed")