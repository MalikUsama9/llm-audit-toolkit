"""Runner: asks the target every test question and saves each result as it finishes."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from datetime import datetime

from audit.models import Result, Run
from audit.store import Store
from audit.targets.base import Target, TargetResponse

# Failure categories. They go in Result.error, so a scorer can skip them
# instead of counting them as wrong answers.
EMPTY = "empty_answer"
TIMEOUT = "timeout"
ERROR = "error"


async def _ask_once(target: Target, question: str, timeout_s: float) -> TargetResponse:
    start = time.perf_counter()
    # target.answer is a normal (blocking) function, so run it in a worker thread
    resp = await asyncio.wait_for(asyncio.to_thread(target.answer, question),
                                  timeout=timeout_s)
    if resp.latency_ms is None:
        resp.latency_ms = (time.perf_counter() - start) * 1000
    return resp


async def _ask_with_retries(target: Target, question: str, timeout_s: float,
                            max_retries: int, base_delay: float) -> TargetResponse:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = await _ask_once(target, question, timeout_s)
            if resp.error is None:
                return resp
            last_error = f"{ERROR}: {resp.error}"
        except asyncio.TimeoutError:
            last_error = f"{TIMEOUT}: no answer within {timeout_s}s"
        except Exception as e:                       # one bad case must not kill the run
            last_error = f"{ERROR}: {type(e).__name__}: {e}"
        if attempt < max_retries:
            await asyncio.sleep(base_delay * 2 ** attempt)   # 1s, 2s, 4s, ...
    return TargetResponse(error=last_error)


async def _run_case(sem: asyncio.Semaphore, store: Store, target: Target,
                    run_id: str, case, timeout_s: float,
                    max_retries: int, base_delay: float) -> None:
    async with sem:                                  # at most N cases in flight
        # Leak rule: the target gets ONLY the question.
        resp = await _ask_with_retries(target, case.question, timeout_s,
                                       max_retries, base_delay)

    error = resp.error
    if error is None and not (resp.answer or "").strip():
        error = EMPTY                                # empty is its own category

    store.add_result(Result(                         # saved immediately
        run_id=run_id, case_id=case.id, answer=resp.answer,
        contexts=resp.contexts, latency_ms=resp.latency_ms,
        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
        error=error))


async def run_audit(store: Store, target: Target, cases: list, *,
                    run_id: str | None = None, config_snapshot: dict | None = None,
                    concurrency: int = 4, timeout_s: float = 60.0,
                    max_retries: int = 3, base_delay: float = 1.0,
                    notes: str | None = None) -> dict:
    """Run every case through the target. Pass an old run_id to resume that run."""
    run_id = run_id or f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"

    if store.get_run(run_id) is None:
        store.add_run(Run(run_id=run_id, target_name=target.name,
                          config_snapshot=config_snapshot or {},
                          created_at=datetime.now(), notes=notes))

    done = store.done_case_ids(run_id)               # resume: skip finished cases
    todo = [c for c in cases if c.id not in done]

    sem = asyncio.Semaphore(concurrency)
    outcomes = await asyncio.gather(
        *(_run_case(sem, store, target, run_id, c, timeout_s, max_retries, base_delay)
          for c in todo),
        return_exceptions=True)                      # safety net: never crash the run

    results = store.get_results(run_id)
    kinds = Counter("ok" if r.error is None else r.error.split(":")[0] for r in results)
    return {"run_id": run_id, "skipped": len(done), "attempted": len(todo),
            "internal_errors": sum(isinstance(o, Exception) for o in outcomes),
            "totals": dict(kinds)}