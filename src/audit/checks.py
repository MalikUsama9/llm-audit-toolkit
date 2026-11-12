"""Deterministic checks that run BEFORE the LLM judge."""
import re
from dataclasses import dataclass

REFUSAL_PATTERNS = [
    # "I can't / cannot / am unable to ... answer/help/provide/assist"
    r"\bi (?:can(?:no|')t|can not|cannot|am unable to)\b.{0,40}\b(?:answer|help|provide|assist|find)",
    # "I'm unable to" / "I'm not able to"
    r"\bi(?:'m| am) (?:not able|unable) to\b",
    # "I don't know" / "I don't have that information / the details / enough context"
    r"\bi (?:don't|do not) know\b",
    r"\bi (?:don't|do not) have\b.{0,30}?\b(?:information|info|details|data|context)\b",
    # "not mentioned in the context"
    r"\bnot (?:mentioned|specified|found|available) in (?:the |my )?(?:provided )?(?:context|documents?)",
    r"\bnot (?:in|within) my (?:context|knowledge)\b",
    r"\bno (?:relevant )?information (?:is )?(?:available|provided|found)",
    r"\bi'?m sorry,? but\b",
    r"\bunable to (?:find|answer)\b",
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

# Statuses that mean "do not send to the judge as a normal answer"
SKIP_JUDGE_STATUSES = {"empty", "error"}


@dataclass
class CheckResult:
    status: str          # "ok" | "empty" | "error" | "refusal" | "partial"
    has_citation: bool
    detail: str = ""


def _normalize(text: str) -> str:
    """Turn curly quotes into straight ones so patterns like "don't" always match."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def is_empty(answer) -> bool:
    return answer is None or not str(answer).strip()


def is_error(answer: str) -> bool:
    return any(re.search(p, answer, re.I) for p in ERROR_PATTERNS)


def is_refusal(answer: str) -> bool:
    return any(re.search(p, answer, re.I | re.S) for p in REFUSAL_PATTERNS)


def has_citation(answer: str) -> bool:
    return any(re.search(p, answer, re.I) for p in CITATION_PATTERNS)


def run_checks(answer, bot_error=None) -> CheckResult:
    """Order matters: error/empty first, then refusal/partial."""
    if bot_error:
        return CheckResult("error", False, f"bot raised: {bot_error}")
    if is_empty(answer):
        return CheckResult("empty", False, "empty answer")
    answer = _normalize(str(answer))
    if is_error(answer) and len(answer) < 300:   # short + error words = likely an error message
        return CheckResult("error", False, "looks like an error message")
    cite = has_citation(answer)
    if is_refusal(answer):
        if cite:
            # Real, cited answer that declines only part of the question
            return CheckResult("partial", cite, "cited answer, then declined part")
        return CheckResult("refusal", cite, "matched refusal pattern")
    return CheckResult("ok", cite)