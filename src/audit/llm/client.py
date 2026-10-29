"""Provider-agnostic LLM client.

Every LLM call in the project goes through LLMClient.complete().
It handles: timeout, retries, caching, cost/token/latency logging, budget cap.
Swapping the model is just a different `model` string (e.g. "gemini/gemini-2.5-flash").
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import litellm
from dotenv import load_dotenv

load_dotenv()  # reads GEMINI_API_KEY / OPENAI_API_KEY from your .env file

# Errors where retrying cannot help (bad key, bad request, unknown model)
NO_RETRY = tuple(
    getattr(litellm, name)
    for name in ("AuthenticationError", "BadRequestError", "NotFoundError")
    if hasattr(litellm, name)
)


class BudgetExceeded(RuntimeError):
    """Raised when total spend passes the budget cap."""


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cached: bool = False


class LLMClient:
    def __init__(self, db_path: str = "data/llm_cache.db", budget_usd: float = 5.0,
                 timeout_s: float = 180.0):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS call_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP,
            model TEXT, input_tokens INTEGER, output_tokens INTEGER,
            cost_usd REAL, latency_ms REAL, cached INTEGER, error TEXT)""")
        self.db.commit()
        self.lock = threading.Lock()
        self.budget = budget_usd
        self.timeout_s = timeout_s
        self.spent = 0.0  # spend in this session (cache hits cost nothing)

    # ---------- public API ----------
    def complete(self, messages: list[dict], model: str, temperature: float = 0.0,
                 max_tokens: int = 700, retries: int = 4,
                 use_cache: bool = True) -> LLMResponse:
        key = self._key(messages, model, temperature, max_tokens)

        if use_cache:
            hit = self._cache_get(key)
            if hit:
                hit.cached = True
                self._log(hit.model, hit.input_tokens, hit.output_tokens, 0.0,
                          hit.latency_ms, cached=True)
                return LLMResponse(**{**asdict(hit), "cost_usd": 0.0})

        if self.spent >= self.budget:
            raise BudgetExceeded(f"spent ${self.spent:.4f} of ${self.budget:.2f}")

        resp, latency_ms = self._call_with_retries(
            messages, model, temperature, max_tokens, retries)

        try:
            cost = litellm.completion_cost(completion_response=resp) or 0.0
        except Exception:
            cost = 0.0  # unknown price: log 0, don't crash

        usage = resp.usage
        out = LLMResponse(
            text=resp.choices[0].message.content or "",
            model=model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
        with self.lock:
            self.spent += cost
        self._cache_put(key, out)
        self._log(model, out.input_tokens, out.output_tokens, cost, latency_ms, cached=False)
        return out

    async def acomplete(self, *args, **kwargs) -> LLMResponse:
        """Async wrapper, so the runner can make many calls concurrently."""
        return await asyncio.to_thread(self.complete, *args, **kwargs)

    def total_logged_cost(self) -> float:
        with self.lock:
            row = self.db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM call_log").fetchone()
        return row[0]

    # ---------- internals ----------
    def _call_with_retries(self, messages, model, temperature, max_tokens, retries):
        last_err = None
        for attempt in range(retries):
            start = time.perf_counter()
            try:
                resp = litellm.completion(
                    model=model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, timeout=self.timeout_s)
                return resp, (time.perf_counter() - start) * 1000
            except NO_RETRY as e:
                self._log(model, 0, 0, 0.0, 0.0, cached=False, error=repr(e))
                raise
            except Exception as e:
                last_err = e
                self._log(model, 0, 0, 0.0, (time.perf_counter() - start) * 1000,
                          cached=False, error=repr(e))
                if attempt < retries - 1:
                    time.sleep(min(5 * 3 ** attempt, 60))  # 5s, 15s, 45s...
        raise last_err

    @staticmethod
    def _key(messages, model, temperature, max_tokens) -> str:
        raw = json.dumps([messages, model, temperature, max_tokens], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_get(self, key) -> LLMResponse | None:
        with self.lock:
            row = self.db.execute("SELECT v FROM cache WHERE k=?", (key,)).fetchone()
        return LLMResponse(**json.loads(row[0])) if row else None

    def _cache_put(self, key, out: LLMResponse) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)",
                            (key, json.dumps(asdict(out))))
            self.db.commit()

    def _log(self, model, in_tok, out_tok, cost, latency_ms, cached, error=None) -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO call_log (model, input_tokens, output_tokens, cost_usd,"
                " latency_ms, cached, error) VALUES (?,?,?,?,?,?,?)",
                (model, in_tok, out_tok, cost, latency_ms, int(cached), error))
            self.db.commit()