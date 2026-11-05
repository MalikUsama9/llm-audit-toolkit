"""The Target interface: the one thing the audit knows about a bot.

A target receives ONLY the question. It never sees the reference answer or the
expected behavior, so the bot can't cheat (the leak rule).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class TargetResponse(BaseModel):
    answer: str | None = None
    contexts: list[str] | None = None     # retrieved chunks, if the bot is RAG
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None              # set when the call failed


class Target(ABC):
    name: str = "target"

    @abstractmethod
    def answer(self, question: str) -> TargetResponse:
        """Ask the bot one question and return what it said."""