"""Deterministic checks that run BEFORE the LLM judge."""
import re
from dataclasses import dataclass

REFUSAL_PATTERNS = [
    r"\bi (can(?:no|')t|cannot|am unable to|'m unable to)\b.{0,40}\b(answer|help|provide|assist)",
    r"\bi (don't|do not) (know|have (enough )?(information|context))",
    r"\b(not (mentioned|specified|found|available) in (the )?(provided )?(context|documents?))",
    r"\bno (relevant )?information (is )?(available|provided|found)",
    r"\bi'?m sorry,? but\b",
    r"\bunable to (find|answer)\b",
]

ERROR_PATTERNS = [
    r"^\s*(error|exception|traceback)\b",
    r"\b(rate limit|timed? ?out|connection (error|refused)|internal server error)\b",
    r"\b(api key|authentication) (error|failed|invalid)\b",
]

CITATION_PATTERNS = [
    r"\[\d+\]",                # [1]
    r"\(source:[^)]+\)",       # (source: doc.pdf)
    r"\bsource[s]?:",          # Source: ...
]


@dataclass
class CheckResult:
    status: str          # "ok" | "empty" | "error" | "refusal"
    has_citation: bool
    detail: str = ""


def is_empty(answer) -> bool:
    return answer is None or not str(answer).strip()


def is_error(answer: str) -> bool:
    return any(re.search(p, answer, re.I) for p in ERROR_PATTERNS)


def is_refusal(answer: str) -> bool:
    return any(re.search(p, answer, re.I | re.S) for p in REFUSAL_PATTERNS)


def has_citation(answer: str) -> bool:
    return any(re.search(p, answer, re.I) for p in CITATION_PATTERNS)


def run_checks(answer, bot_error=None) -> CheckResult:
    """Order matters: error/empty first, then refusal."""
    if bot_error:
        return CheckResult("error", False, f"bot raised: {bot_error}")
    if is_empty(answer):
        return CheckResult("empty", False, "empty answer")
    answer = str(answer)
    if is_error(answer) and len(answer) < 300:   # short + error words = likely an error message
        return CheckResult("error", False, "looks like an error message")
    cite = has_citation(answer)
    if is_refusal(answer):
        return CheckResult("refusal", cite, "matched refusal pattern")
    return CheckResult("ok", cite)