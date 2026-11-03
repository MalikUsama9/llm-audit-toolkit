# src/audit/qa_generator.py
"""Generate grounded Q/A test cases from chunks.

Usage (dry run on 10 chunks):
    python -m audit.qa_generator --limit 10

Override the models without editing this file (PowerShell):
    $env:AUDIT_GENERATOR_MODEL="gemini/gemini-3.1-flash-lite"
    $env:AUDIT_FALLBACK_MODEL="gemini/gemini-3.5-flash-lite"
"""
import argparse
import inspect
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from audit.chunking import Chunk, chunk_dir
from audit.models import TestCase

# Hide the repeated LiteLLM warnings so progress lines stay readable
logging.getLogger("LiteLLM").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# 1. LLM CLIENT (the only part you may need to edit)
# ---------------------------------------------------------------------------
GENERATOR_MODEL = os.environ.get("AUDIT_GENERATOR_MODEL", "gemini/gemini-3.1-flash-lite")
# Used automatically when the main model is busy or out of quota.
# Set to None (or AUDIT_FALLBACK_MODEL="") to turn it off.
FALLBACK_MODEL = os.environ.get("AUDIT_FALLBACK_MODEL", "gemini/gemini-3.5-flash-lite") or None

MIN_GAP_SECONDS = 7        # pause after each real API call (free tier ~10 requests/min)
BUSY_WAIT_SECONDS = 15     # wait before retrying a 503 "high demand" error
QUOTA_WAIT_SECONDS = 65    # wait before retrying a 429 quota error (once)
MAX_BUSY_ATTEMPTS = 3
MAX_CONSECUTIVE_FAILURES = 8

_client = None


class QuotaExceeded(Exception):
    """The API says the quota is used up. Retrying right away will not help."""


def _text(err: Exception) -> str:
    return f"{type(err).__name__} {err}".lower()


def _is_quota(err: Exception) -> bool:
    t = _text(err)
    return "429" in t or "quota" in t or "ratelimit" in t or "rate limit" in t


def _is_busy(err: Exception) -> bool:
    t = _text(err)
    return any(m in t for m in ("503", "unavailable", "high demand", "overloaded",
                                "timeout", "timed out", "temporarily", "ssl", "eof",
                                "connection"))


def _reply_text(resp) -> str:
    """Get the reply text, whatever the response field is called."""
    if isinstance(resp, str):
        return resp
    for attr in ("text", "content", "output", "answer"):
        value = getattr(resp, attr, None)
        if isinstance(value, str):
            return value
    raise RuntimeError(
        f"Could not find the reply text on {type(resp).__name__}. "
        f"Fields available: {[a for a in dir(resp) if not a.startswith('_')]}"
    )


def _complete(model: str, prompt: str, temperature: float) -> str:
    global _client
    if _client is None:
        from audit.llm.client import LLMClient
        _client = LLMClient()

    kwargs = dict(model=model, temperature=temperature, max_tokens=1500)
    # Our own retry loop handles waiting, so the client should try only ONCE.
    # (retries=0 made the client's loop run zero times and crash with
    #  "exceptions must derive from BaseException", so use 1.)
    if "retries" in inspect.signature(_client.complete).parameters:
        kwargs["retries"] = 1
    return _reply_text(_client.complete([{"role": "user", "content": prompt}], **kwargs))


def _call_model(model: str, prompt: str, temperature: float) -> str:
    """Call one model, with pacing and sensible waits for busy/quota errors."""
    quota_retried = False
    for attempt in range(1, MAX_BUSY_ATTEMPTS + 1):
        started = time.time()
        try:
            reply = _complete(model, prompt, temperature)
            if time.time() - started > 1.0:      # a real API call, not a cache hit
                time.sleep(MIN_GAP_SECONDS)
            return reply
        except Exception as e:
            if _is_quota(e):
                if quota_retried:
                    raise QuotaExceeded(str(e)[:200]) from e
                quota_retried = True
                print(f"  quota/rate limit hit; waiting {QUOTA_WAIT_SECONDS}s, then one retry")
                time.sleep(QUOTA_WAIT_SECONDS)
            elif _is_busy(e) and attempt < MAX_BUSY_ATTEMPTS:
                wait = BUSY_WAIT_SECONDS * 2 ** (attempt - 1)
                print(f"  server busy ({type(e).__name__}); waiting {wait}s "
                      f"(attempt {attempt}/{MAX_BUSY_ATTEMPTS})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("model did not answer after retries")


def call_llm(prompt: str, temperature: float = 0.0) -> str:
    """Send `prompt` to the generator model; use the fallback model if it is unavailable."""
    try:
        return _call_model(GENERATOR_MODEL, prompt, temperature)
    except Exception as e:
        if FALLBACK_MODEL and (isinstance(e, QuotaExceeded) or _is_busy(e)):
            print(f"  switching to fallback model {FALLBACK_MODEL}")
            return _call_model(FALLBACK_MODEL, prompt, temperature)
        raise


# ---------------------------------------------------------------------------
# 2. Schemas
# ---------------------------------------------------------------------------
class GenItem(BaseModel):
    question: str
    reference_answer: str
    category: Literal["direct_factual", "numeric_policy", "multi_intent"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class GenBatch(BaseModel):
    items: list[GenItem]


# ---------------------------------------------------------------------------
# 3. Prompt
# ---------------------------------------------------------------------------
PROMPT = """You write test questions for a customer-support chatbot.

Using ONLY the excerpt below, write {k} questions that a real customer might ask.
Rules:
- Each question must be fully answerable from the excerpt alone.
- The reference_answer must use only facts stated in the excerpt. Do not add
  outside knowledge, and do not guess.
- Write questions the way a customer would, not by copying the excerpt's wording.
- Mix these categories where the excerpt allows:
  direct_factual (one plain fact),
  numeric_policy (asks about a specific number, date, price, limit or exception),
  multi_intent (two short questions in one message).
- If the excerpt has no numbers or exceptions, do not invent a numeric_policy question.
- Keep reference answers short (1-3 sentences) and complete.

Return ONLY JSON, with no preamble and no code fences:
{{"items": [{{"question": "...", "reference_answer": "...", "category": "direct_factual", "difficulty": "easy"}}]}}

Excerpt (id: {chunk_id}):
{text}
"""


def _parse(raw: str) -> GenBatch:
    """Parse the model reply. Tolerates code fences or a sentence before/after the JSON."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return GenBatch.model_validate(json.loads(cleaned))


def generate_for_chunk(chunk: Chunk, k: int = 3, retries: int = 2) -> list[dict]:
    prompt = PROMPT.format(k=k, chunk_id=chunk.chunk_id, text=chunk.text)
    last_err = None
    for attempt in range(retries + 1):
        try:
            # Raise the temperature a little on each retry so the cached
            # reply from the previous attempt is not returned again.
            raw = call_llm(prompt, temperature=0.3 * attempt)
            batch = _parse(raw)
            return [
                {
                    "category": it.category,
                    "question": it.question.strip(),
                    "reference_answer": it.reference_answer.strip(),
                    "difficulty": it.difficulty,
                    "expected_behavior": "answer",
                    "source_ref": [chunk.chunk_id],
                    "source_text": chunk.text,
                    "origin": "generated",
                    "reviewed": False,
                }
                for it in batch.items
            ]
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
    print(f"  skipped {chunk.chunk_id}: {last_err}")
    return []


# ---------------------------------------------------------------------------
# 4. Dry run / full run
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="data/demo/docs")
    ap.add_argument("--out", default="data/demo/draft_generated.jsonl")
    ap.add_argument("--limit", type=int, default=10, help="number of chunks (0 = all)")
    ap.add_argument("--k", type=int, default=3, help="questions per chunk")
    args = ap.parse_args()

    print(f"Generator model: {GENERATOR_MODEL}")
    print(f"Fallback model:  {FALLBACK_MODEL or 'off'}\n")

    chunks = chunk_dir(args.docs)
    if args.limit:
        chunks = chunks[: args.limit]

    rows: list[dict] = []
    failed: list[str] = []
    in_a_row = 0
    quota_stop = False
    try:
        for i, ch in enumerate(chunks, 1):
            print(f"[{i}/{len(chunks)}] {ch.chunk_id}")
            try:
                new_rows = generate_for_chunk(ch, k=args.k)
                in_a_row = 0
            except QuotaExceeded as e:
                print(f"  QUOTA EXCEEDED: {e}")
                failed.extend(c.chunk_id for c in chunks[i - 1:])
                quota_stop = True
                break
            except Exception as e:  # one bad chunk should not lose the whole run
                print(f"  FAILED {ch.chunk_id}: {type(e).__name__}: {str(e)[:200]}")
                failed.append(ch.chunk_id)
                in_a_row += 1
                if in_a_row >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\nStopping: {MAX_CONSECUTIVE_FAILURES} chunks failed in a row.")
                    break
                continue
            rows.extend(new_rows)
    except KeyboardInterrupt:
        print("\nStopped by you (Ctrl+C). Saving what was generated so far.")
        failed.extend(c.chunk_id for c in chunks[len(rows) // max(args.k, 1):]
                      if c.chunk_id not in failed)

    # Drop duplicate questions (same text, ignoring case and spacing)
    seen: set[str] = set()
    unique: list[dict] = []
    for r in rows:
        key = " ".join(r["question"].lower().split())
        if key not in seen:
            seen.add(key)
            unique.append(r)
    if len(unique) < len(rows):
        print(f"\nRemoved {len(rows) - len(unique)} duplicate questions")

    for n, r in enumerate(unique, 1):
        r["id"] = f"gen-{n:03d}"

    # Check every row against the real TestCase model before saving
    valid: list[dict] = []
    for r in unique:
        try:
            TestCase(**r)
            valid.append(r)
        except ValidationError as e:
            print(f"  invalid case {r['id']} dropped: {e.errors()[0]['msg']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in valid:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(valid)} draft cases to {out}")

    if quota_stop:
        print("\nThe API quota is used up on both models. Wait (per-minute limits clear in a "
              "minute, daily limits reset the next day), or change the model names, "
              "then run the same command again.")
    if failed:
        print(f"\n{len(failed)} chunk(s) not finished. Run the same command again later; "
              f"finished chunks are cached and will be skipped quickly:")
        for cid in failed:
            print(f"  - {cid}")


if __name__ == "__main__":
    main()