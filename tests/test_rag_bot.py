"""Tests for the demo bot. A fake LLM is used, so no API key and no cost."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "my_rag_bot"))

import pytest

from rag_bot import (DEFAULT_DOCS_DIR, SYSTEM_PROMPT, BM25Index, BotConfig, RagBot,
                     load_chunks)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, messages, model, temperature=0.0, max_tokens=700, **kw):
        self.calls.append({"messages": messages, "model": model,
                           "temperature": temperature, "max_tokens": max_tokens})
        return SimpleNamespace(text="  fake answer  ", input_tokens=11, output_tokens=3,
                               cost_usd=0.0002, latency_ms=50.0, cached=False)


@pytest.fixture(scope="module")
def chunks():
    return load_chunks(DEFAULT_DOCS_DIR)


def test_demo_docs_exist_and_are_big_enough():
    files = sorted(Path(DEFAULT_DOCS_DIR).glob("*.md"))
    words = sum(len(f.read_text(encoding="utf-8").split()) for f in files)
    assert len(files) >= 14 and words >= 6000


def test_chunks_have_source_refs(chunks):
    assert len(chunks) > 100
    for c in chunks:
        assert ".md#" in c.source and c.source.split("#", 1)[1].strip()
        assert len(c.text) <= 1300


@pytest.mark.parametrize("question, expected_file", [
    ("How many days do I have to return an item?", "03_returns_and_refunds.md"),
    ("What is the cutoff time for overnight shipping?", "02_shipping_policy.md"),
    ("What temperature is the dutch oven oven safe to?", "07_kitchen_products.md"),
    ("How much does the Tidewell Club cost?", "06_tidewell_club_and_gift_cards.md"),
    ("How long is the warranty on the enamel?", "10_warranty.md"),
    ("What are your phone support hours?", "11_support_and_contact.md"),
])
def test_retrieval_finds_the_right_document(chunks, question, expected_file):
    hits = BM25Index(chunks).search(question, k=4)
    assert expected_file in [c.source.split("#")[0] for c, _ in hits]


def test_bot_prompt_contains_context_and_question():
    llm = FakeLLM()
    bot = RagBot(BotConfig(), llm=llm)
    out = bot.answer("What is the return window?")
    sent = llm.calls[0]["messages"]
    assert sent[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "QUESTION: What is the return window?" in sent[1]["content"]
    assert "30 days" in sent[1]["content"]
    assert out.answer == "fake answer"           # stripped
    assert out.input_tokens == 11 and out.output_tokens == 3
    assert out.contexts and len(out.contexts) == len(out.sources) <= 4


def test_no_match_still_calls_llm_with_empty_context():
    llm = FakeLLM()
    out = RagBot(BotConfig(), llm=llm).answer("zzzqqq xxyyzz")
    assert out.contexts == []
    assert "(no relevant information found)" in llm.calls[0]["messages"][1]["content"]


def test_snapshot_is_json_and_reproducible():
    snap = BotConfig().snapshot()
    assert json.loads(json.dumps(snap)) == snap
    assert snap["prompt_version"] == "v1" and snap["system_prompt"] == SYSTEM_PROMPT
    assert snap["top_k"] == 4 and snap["retriever"] == "bm25"
