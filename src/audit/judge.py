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
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ValidationError

log = logging.getLogger("audit.judge")

Status = Literal["supported", "contradicted", "not_in_source"]


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


def hallucination_flag(claims: list[Claim]) -> bool:
    """True if ANY claim is not supported (contradicted or not_in_source)."""
    return any(c.status != "supported" for c in claims)


# ---------------------------------------------------------------- helpers
def strip_fences(text: str) -> str:
    """Remove ```json ... ``` fences that models sometimes wrap around JSON."""
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def load_rubric(name: str, rubric_dir: str = "configs/rubrics") -> dict:
    path = Path(rubric_dir) / f"{name}.yaml"
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
def _call_llm(client, cfg, system: str, user: str, use_cache: bool) -> str:
    """
    ADAPT THIS ONE FUNCTION to your LLMClient in src/audit/llm/client.py.
    Change the method name and argument names to match what your client
    accepts. It must return the model's reply as a plain string.
    """
    resp = client.complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        use_cache=use_cache,
    )
    if isinstance(resp, str):
        return resp
    return getattr(resp, "text", None) or getattr(resp, "content", None) or ""


def _parse(raw: str, labels: set) -> JudgeOutput:
    data = json.loads(strip_fences(raw))
    out = JudgeOutput.model_validate(data)
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
            out = _parse(raw, labels)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            log.warning(
                "judge_parse_error case=%s metric=%s attempt=%d error=%s",
                case_id, rubric["name"], attempt, e,
            )
            continue
        # Any other error (for example BudgetExceeded) is NOT caught here,
        # so it stops the run instead of being retried and hidden.
        return JudgeResult(
            output=out,
            hallucinated=hallucination_flag(out.claims),
            judge_model=cfg.model,
            rubric_name=rubric["name"],
            rubric_version=str(rubric.get("version")),
            temperature=cfg.temperature,
        )

    log.error(
        "judge_failure case=%s metric=%s judge_model=%s rubric_version=%s",
        case_id, rubric["name"], cfg.model, rubric.get("version"),
    )
    return None


# ---------------------------------------------------------------- offline test
if __name__ == "__main__":
    # Runs without any API call: python judge.py
    from types import SimpleNamespace

    logging.basicConfig(level=logging.INFO)

    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert hallucination_flag([Claim(claim="x", status="supported")]) is False
    assert hallucination_flag([Claim(claim="x", status="not_in_source")]) is True

    rubric = {
        "name": "faithfulness", "version": "1.0",
        "labels": {k: {"definition": "d", "borderline": "b"}
                   for k in ("supported", "contradicted", "not_in_source")},
        "rules": ["Length is not quality.", "Material claims only."],
    }
    cfg = SimpleNamespace(model="test-model", temperature=0.0, max_tokens=800)

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

    # two failures -> None
    c = FakeClient(["bad", "worse"])
    assert judge_case(c, cfg, rubric, "t2", "q", "ref", "src", "ans") is None

    print("judge.py offline checks passed")