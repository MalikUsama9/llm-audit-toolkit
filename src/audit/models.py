"""Core data models for the audit toolkit.

Everything else (runner, evaluators, store, reports) depends on these,
so keep field names stable. Add new optional fields rather than renaming.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ExpectedBehavior(str, Enum):
    ANSWER = "answer"    # bot should answer from the docs
    REFUSE = "refuse"    # out of scope / unsafe: bot should decline
    HANDOFF = "handoff"  # bot should pass to a human


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TestCase(BaseModel):
    __test__ = False  # stops pytest from trying to collect this class

    id: str
    category: str                       # e.g. "factual", "off_topic", "adversarial"
    question: str
    reference_answer: str | None = None  # None for refuse/handoff cases
    source_ref: str | None = None        # doc name + chunk/page the answer comes from
    expected_behavior: ExpectedBehavior = ExpectedBehavior.ANSWER
    difficulty: Difficulty = Difficulty.MEDIUM

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def answerable_needs_source(self) -> "TestCase":
        # Roadmap rule: every answerable case has a source reference
        if self.expected_behavior == ExpectedBehavior.ANSWER and not self.source_ref:
            raise ValueError(f"case {self.id}: answerable cases need a source_ref")
        return self


class Result(BaseModel):
    run_id: str
    case_id: str
    answer: str | None = None
    contexts: list[str] | None = None   # only in glass-box mode
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None            # set when the call failed


class Score(BaseModel):
    run_id: str
    case_id: str
    metric: str                          # e.g. "correctness", "faithfulness", "refusal"
    value: float                         # 0-1 or 1-5, depending on the metric
    reasoning: str | None = None
    judge_model: str | None = None       # None for deterministic metrics


class Run(BaseModel):
    run_id: str
    target_name: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str | None = None