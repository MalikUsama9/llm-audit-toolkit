from pathlib import Path

import pytest
from pydantic import ValidationError

from audit.config import load_config

EXAMPLE = Path(__file__).resolve().parents[1] / "configs" / "audit.example.yaml"


def write(tmp_path, text):
    p = tmp_path / "c.yaml"
    p.write_text(text, encoding="utf-8")
    return p


BASE = """
target: {name: bot}
models: {generator: a/x, judge: b/y}
budget: {max_usd: 2}
testset: {categories: {factual: 5}}
"""


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert cfg.target.name == "my_rag_bot"
    assert cfg.testset.total == 120
    assert cfg.budget.max_usd == 5.0
    assert cfg.paths.database == "data/audit.db"


def test_defaults_are_filled(tmp_path):
    cfg = load_config(write(tmp_path, BASE))
    assert cfg.budget.timeout_s == 180 and cfg.testset.holdout_fraction == 0.3
    assert cfg.paths.testset.endswith("testset.jsonl")


def test_typo_in_key_is_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_config(write(tmp_path, BASE.replace("max_usd", "max_usdd")))


def test_bad_values_are_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_config(write(tmp_path, BASE.replace("max_usd: 2", "max_usd: 0")))
    with pytest.raises(ValidationError):
        load_config(write(tmp_path, BASE.replace("factual: 5", "factual: 0")))
    with pytest.raises(ValidationError):
        load_config(write(tmp_path, BASE.replace(
            "{categories", "{holdout_fraction: 0.9, categories")))


def test_missing_and_broken_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
    with pytest.raises(ValueError):
        load_config(write(tmp_path, ""))
    with pytest.raises(ValueError):
        load_config(write(tmp_path, "a: [unclosed"))


def test_same_provider_warning():
    cfg = load_config(EXAMPLE)
    assert any("same provider" in w for w in cfg.warnings())