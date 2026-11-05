"""Command line: `audit run`.

    audit run --target configs/audit.yaml --testset data/demo/testset.jsonl --limit 5
    audit run --resume run_20261105_120000_ab12cd     # continue an earlier run

Reads the config, builds the target, loads the test cases, calls run_audit(),
prints progress while it works, and a summary (errors, p50/p95 latency) at the end.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from audit.config import AuditConfig, load_config
from audit.models import TestCase
from audit.runner import run_audit
from audit.store import Store
from audit.targets.base import Target


# ---------------------------------------------------------------- helpers
def percentile(values: list[float], p: float) -> float:
    """p in 0..100. Linear interpolation between the closest ranks."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load_testset(path: str | Path) -> list[TestCase]:
    """Read a .jsonl file: one test case per line."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Test set not found: {p}")
    cases = []
    with p.open(encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(TestCase(**json.loads(line)))
            except (json.JSONDecodeError, ValidationError) as e:
                raise ValueError(f"{p}, line {n}: {e}") from e
    return cases


def build_target(cfg: AuditConfig) -> Target:
    """Pick PythonTarget / HttpTarget / FileTarget from `target.type` in the YAML."""
    t = cfg.target
    if t.type == "python":
        from audit.llm.client import LLMClient
        from audit.targets.python_target import PythonTarget
        target = PythonTarget.from_rag_bot(LLMClient(), name=t.name)
        if t.model:                      # the model named in the YAML wins
            target.config.model = t.model
        return target
    if t.type == "http":
        from audit.targets.http_target import HttpTarget
        if not t.url:
            raise ValueError("target.type is 'http' but target.url is missing in the YAML")
        return HttpTarget.from_config(t.model_dump(exclude_none=True))
    if t.type == "file":
        from audit.targets.file_target import FileTarget
        if not t.answers_file:
            raise ValueError("target.type is 'file' but target.answers_file is missing")
        return FileTarget.from_csv(t.answers_file, name=t.name)
    raise ValueError(f"unknown target type: {t.type}")


async def _show_progress(store: Store, run_id: str, total: int, every_s: float = 2.0) -> None:
    """Print 'done/total (errors)' every few seconds while the run is going."""
    last = -1
    while True:
        await asyncio.sleep(every_s)
        results = store.get_results(run_id)
        done = len(results)
        if done != last:
            errors = sum(1 for r in results if r.error is not None)
            print(f"  progress: {done}/{total} saved, {errors} errors", flush=True)
            last = done


def print_summary(store: Store, run_id: str, case_ids: set[str], outcome: dict) -> int:
    """Print the end-of-run summary. Returns the number of errors."""
    results = [r for r in store.get_results(run_id) if r.case_id in case_ids]
    errors = [r for r in results if r.error is not None]
    kinds: dict[str, int] = {}
    for r in errors:
        kind = r.error.split(":")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    latencies = [r.latency_ms for r in results if r.error is None and r.latency_ms is not None]

    print()
    print("=" * 50)
    print(f"Run:        {run_id}")
    print(f"Cases:      {len(results)} saved (skipped {outcome['skipped']} already done, "
          f"asked {outcome['attempted']} this time)")
    print(f"Succeeded:  {len(results) - len(errors)}")
    print(f"Errors:     {len(errors)}" + (f"  {kinds}" if kinds else ""))
    if latencies:
        print(f"Latency:    p50 = {percentile(latencies, 50):.0f} ms   "
              f"p95 = {percentile(latencies, 95):.0f} ms   (successful calls only)")
    else:
        print("Latency:    no successful calls")
    if outcome.get("internal_errors"):
        print(f"WARNING:    {outcome['internal_errors']} internal runner errors")
    if errors:
        print(f"To retry the failed cases:  audit run --resume {run_id}")
    print("=" * 50)
    return len(errors)


# ---------------------------------------------------------------- the command
def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.target)
    for w in cfg.warnings():
        print(f"warning: {w}")

    testset_path = args.testset or cfg.paths.testset
    cases = load_testset(testset_path)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        print("No test cases to run.")
        return 1

    store = Store(cfg.paths.database)

    run_id = args.resume or f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    if args.resume and store.get_run(run_id) is None:
        print(f"error: no run called '{run_id}' in {cfg.paths.database}")
        return 1

    # results point at cases, so the cases must be in the database first
    known = {c.id for c in store.get_cases()}
    new = [c for c in cases if c.id not in known]
    if new:
        store.add_cases(new)

    target = build_target(cfg)
    snapshot = {**target.config_snapshot(), "models": cfg.models.model_dump()}
    concurrency = args.concurrency or cfg.budget.max_concurrency

    print(f"Run {run_id}: {len(cases)} cases, concurrency {concurrency}, "
          f"target '{cfg.target.name}' ({cfg.target.type})")

    async def go() -> dict:
        ticker = asyncio.create_task(_show_progress(store, run_id, len(cases)))
        try:
            return await run_audit(
                store, target, cases, run_id=run_id, config_snapshot=snapshot,
                concurrency=concurrency, timeout_s=cfg.budget.timeout_s)
        finally:
            ticker.cancel()

    try:
        outcome = asyncio.run(go())
    except KeyboardInterrupt:
        print(f"\nStopped. Finished cases are saved. Continue with:  audit run --resume {run_id}")
        return 130

    n_errors = print_summary(store, run_id, {c.id for c in cases}, outcome)
    return 0 if n_errors == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audit", description="LLM audit toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="ask the target every test question and save the answers")
    run.add_argument("--target", default="configs/audit.yaml",
                     help="path to the audit YAML (default: configs/audit.yaml)")
    run.add_argument("--testset", default=None,
                     help="path to the .jsonl test cases (default: paths.testset in the YAML)")
    run.add_argument("--concurrency", type=int, default=None,
                     help="cases asked at the same time (default: budget.max_concurrency)")
    run.add_argument("--resume", metavar="RUN_ID", default=None,
                     help="continue this run: skip finished cases, retry failed ones")
    run.add_argument("--limit", type=int, default=None, metavar="N",
                     help="only run the first N cases")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "concurrency", None) is not None and args.concurrency < 1:
        print("error: --concurrency must be at least 1")
        return 1
    if getattr(args, "limit", None) is not None and args.limit < 1:
        print("error: --limit must be at least 1")
        return 1
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, ValidationError) as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())