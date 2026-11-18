"""My simple RAG bot: the first target to audit.

How it works:
  1. Split the demo documents into chunks (one chunk per "## section").
  2. Find the chunks most similar to the question (BM25 keyword search, no extra libraries).
  3. Ask the LLM to answer using ONLY those chunks.

This is deliberately simple ("v1"). Its flaws are what the audit will find.
Keep SYSTEM_PROMPT and BotConfig unchanged between runs you want to compare;
BotConfig.snapshot() is saved with every run so results stay reproducible.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "docs"

PROMPT_VERSION = "day9"
SYSTEM_PROMPT = (
    "You are the customer support assistant for Tidewell Home, an online shop.\n"
    "Answer the customer's question using ONLY the information in the CONTEXT.\n"
    "If the CONTEXT does not contain the answer, say you don't have that information "
    "and suggest contacting support at support@tidewellhome.example.\n"
    "Do not answer questions that are unrelated to Tidewell Home.\n"
    "Be friendly. Answer in at most 2 short sentences, then ask if there is anything else you can help with.\n"
    "If the question does not say which product, policy or situation it is about, "
    "ask one short clarifying question instead of answering.\n"
)


# ---------------------------------------------------------------- config
@dataclass
class BotConfig:
    model: str = "gemini/gemini-3.8-flash"
    top_k: int = 4                  # chunks given to the LLM
    temperature: float = 0.0
    max_tokens: int = 1500          # generous: some models "think" before answering
    prompt_version: str = PROMPT_VERSION
    docs_dir: str = str(DEFAULT_DOCS_DIR)
    max_chunk_chars: int = 1200

    def snapshot(self) -> dict:
        """Everything needed to reproduce a run. Store this in Run.config_snapshot."""
        d = asdict(self)
        d["system_prompt"] = SYSTEM_PROMPT
        d["retriever"] = "bm25"
        return d


# ---------------------------------------------------------------- chunking
@dataclass
class Chunk:
    source: str   # e.g. "03_returns_and_refunds.md#Return window"  (use as TestCase.source_ref)
    text: str


def _split_long(body: str, limit: int) -> list[str]:
    """Split an over-long section on blank lines, keeping pieces under `limit` chars."""
    pieces, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        if current and len(current) + len(para) + 2 > limit:
            pieces.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        pieces.append(current.strip())
    return pieces


def load_chunks(docs_dir: str | Path, max_chunk_chars: int = 1200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
        # parts = [preamble, heading1, body1, heading2, body2, ...]
        for heading, body in zip(parts[1::2], parts[2::2]):
            body = body.strip()
            if not body:
                continue
            for piece in _split_long(body, max_chunk_chars):
                chunks.append(Chunk(
                    source=f"{path.name}#{heading.strip()}",
                    text=f"{title} - {heading.strip()}\n{piece}"))
    return chunks


# ---------------------------------------------------------------- retrieval (BM25)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from",
    "how", "i", "if", "in", "is", "it", "my", "of", "on", "or", "the", "to", "we", "what",
    "when", "which", "with", "you", "your", "me", "get", "there", "that", "this", "will",
}


def _stem(w: str) -> str:
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        # the section heading is repeated once so it counts a bit more
        self.docs = [tokenize(c.text + " " + c.source.split("#", 1)[-1]) for c in chunks]
        self.tf = [Counter(d) for d in self.docs]
        self.avg_len = (sum(len(d) for d in self.docs) / len(self.docs)) if self.docs else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self.tf):
            length = len(self.docs[i])
            score = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    score += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            if score > 0:
                scored.append((self.chunks[i], score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


# ---------------------------------------------------------------- the bot
@dataclass
class BotAnswer:
    answer: str
    contexts: list[str] = field(default_factory=list)   # retrieved chunk texts
    sources: list[str] = field(default_factory=list)    # their source refs
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class RagBot:
    def __init__(self, config: BotConfig | None = None, llm=None):
        self.config = config or BotConfig()
        if llm is None:
            from audit.llm.client import LLMClient  # imported here so tests can skip it
            llm = LLMClient()
        self.llm = llm
        self.chunks = load_chunks(self.config.docs_dir, self.config.max_chunk_chars)
        self.index = BM25Index(self.chunks)

    def build_messages(self, question: str) -> tuple[list[dict], list[Chunk]]:
        hits = [c for c, _ in self.index.search(question, self.config.top_k)]
        if hits:
            context = "\n\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(hits))
        else:
            context = "(no relevant information found)"
        user = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user}]
        return messages, hits

    def answer(self, question: str) -> BotAnswer:
        messages, hits = self.build_messages(question)
        start = time.perf_counter()
        resp = self.llm.complete(messages, model=self.config.model,
                                 temperature=self.config.temperature,
                                 max_tokens=self.config.max_tokens)
        total_ms = (time.perf_counter() - start) * 1000
        return BotAnswer(
            answer=resp.text.strip(),
            contexts=[c.text for c in hits],
            sources=[c.source for c in hits],
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms if not resp.cached else total_ms,
        )