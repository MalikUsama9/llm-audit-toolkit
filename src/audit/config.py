"""Load and validate the audit settings (a YAML file).

Typos in the YAML are rejected on purpose (extra="forbid"), so a misspelled key
fails loudly instead of being silently ignored.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetConfig(_Strict):
    name: str
    type: Literal["python", "http", "file"] = "python"
    entrypoint: str | None = None   # python: path to the bot file
    model: str | None = None        # model the bot uses (recorded for the report)
    # http target
    url: str | None = None
    headers: dict[str, str] | None = None
    payload_template: dict | None = None
    answer_path: str | None = None
    contexts_path: str | None = None
    timeout_s: float | None = None
    # file target
    answers_file: str | None = None  # CSV the client filled in


class ModelsConfig(_Strict):
    generator: str                  # writes the test questions
    judge: str                      # scores the bot's answers

    @field_validator("generator", "judge")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model name must not be empty")
        return v.strip()


class JudgeConfig(_Strict):
    """Settings for the judge that scores the bot's answers."""
    model: str                                   # e.g. groq/openai/gpt-oss-120b
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=800, ge=1)
    rubric_dir: str = "configs/rubrics"
    budget_usd: float = Field(default=3.0, gt=0)  # spending cap for judging

    @field_validator("model")
    @classmethod
    def model_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("judge model name must not be empty")
        return v.strip()


class BudgetConfig(_Strict):
    max_usd: float = Field(gt=0, description="hard spending cap for one audit")
    timeout_s: float = Field(default=180.0, gt=0)
    max_concurrency: int = Field(default=4, ge=1, le=64)


class PathsConfig(_Strict):
    docs_dir: str = "data/demo/docs"
    testset: str = "data/demo/testset.jsonl"
    database: str = "data/audit.db"
    llm_cache: str = "data/llm_cache.db"


class TestsetConfig(_Strict):
    __test__ = False  # not a pytest class
    holdout_fraction: float = Field(default=0.3, ge=0.0, le=0.5)
    categories: dict[str, int]

    @field_validator("categories")
    @classmethod
    def counts_positive(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("at least one category is required")
        bad = [k for k, n in v.items() if n < 1]
        if bad:
            raise ValueError(f"category counts must be at least 1: {bad}")
        return v

    @property
    def total(self) -> int:
        return sum(self.categories.values())


class AuditConfig(_Strict):
    target: TargetConfig
    models: ModelsConfig
    judge: JudgeConfig | None = None
    budget: BudgetConfig
    paths: PathsConfig = PathsConfig()
    testset: TestsetConfig

    def warnings(self) -> list[str]:
        """Things that are allowed but weaken the audit. Show them in the report."""
        out = []
        provider = lambda m: m.split("/", 1)[0] if m else None  # noqa: E731
        if self.target.model and provider(self.models.judge) == provider(self.target.model):
            out.append("Judge and target bot use the same provider; "
                       "scores may be biased toward the bot's own style.")
        if self.models.generator == self.models.judge:
            out.append("Test generator and judge are the same model; note this in the limitations.")
        if self.judge and self.judge.model != self.models.judge:
            out.append(f"judge.model ({self.judge.model}) differs from models.judge "
                       f"({self.models.judge}); keep them identical.")
        return out


def load_config(path: str | Path) -> AuditConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"{p} is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{p} is empty or not a YAML mapping")
    return AuditConfig.model_validate(data)