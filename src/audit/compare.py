from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, field
from collections import defaultdict

# wilson / paired_flip_test / paired_bootstrap_delta live in the reporting package.
# Try both module names so this works whichever file you put them in.
try:
    from audit.reporting.stats import wilson, paired_flip_test, paired_bootstrap_delta
except ImportError:
    try:
        from audit.reporting.summary import wilson, paired_flip_test, paired_bootstrap_delta
    except ImportError as e:
        raise ImportError(
            "Could not import wilson, paired_flip_test and paired_bootstrap_delta from "
            "audit.reporting.stats or audit.reporting.summary. Check that one of these "
            "files exists in src/audit/reporting/ and defines all three functions."
        ) from e

SMALL_N = 30          # below this, flag as "indicative only"
VERY_SMALL_N = 15
FEW_FLIPS = 10        # below this many changed cases, the flip test has low power
OVERALL_N_WARN = 100  # below this, warn about small differences overall
MIN_N_FOR_CI = 5      # below this, the bootstrap CI is not shown


@dataclass
class Cell:
    """One row of the comparison table (metric, category)."""
    metric: str
    category: str                 # "ALL" for the per-metric overall row
    n: int
    k_a: int
    k_b: int
    rate_a: float
    rate_b: float
    ci_a: tuple[float, float]
    ci_b: tuple[float, float]
    delta: float
    delta_ci: tuple[float, float]
    fixed: list[str] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)
    p_value: float = 1.0
    caveat: str = ""

    @property
    def significant(self) -> bool:
        # CI excludes zero AND the exact flip test agrees
        return (self.delta_ci[0] > 0 or self.delta_ci[1] < 0) and self.p_value < 0.05


def load_outcomes(db: sqlite3.Connection, run_id: str) -> dict:
    """
    Returns {(case_id, metric): (category, passed: 0/1 or None)}.
    passed=None means the case errored (timeout, empty answer, HTTP error).

    ADAPT THIS QUERY to your store.py column names.
    """
    rows = db.execute(
        """
        SELECT s.case_id, s.metric, c.category, s.value, r.error
        FROM scores s
        JOIN cases c   ON c.id = s.case_id
        JOIN results r ON r.run_id = s.run_id AND r.case_id = s.case_id
        WHERE s.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    out = {}
    for case_id, metric, category, value, error in rows:
        if error or value is None:
            out[(case_id, metric)] = (category, None)
        else:
            out[(case_id, metric)] = (category, 1 if value >= 1 else 0)  # 1 = good outcome
    return out


def _caveat(n: int) -> str:
    if n < VERY_SMALL_N:
        return f"n={n}: too small for conclusions"
    if n < SMALL_N:
        return f"n={n}: indicative only"
    return ""


def _build_cell(metric, category, pairs):
    """pairs: list of (case_id, a, b) with a,b in {0,1}."""
    n = len(pairs)
    a = [p[1] for p in pairs]
    b = [p[2] for p in pairs]
    k_a, k_b = sum(a), sum(b)
    fixed = [cid for cid, x, y in pairs if x == 0 and y == 1]
    broken = [cid for cid, x, y in pairs if x == 1 and y == 0]
    return Cell(
        metric=metric, category=category, n=n, k_a=k_a, k_b=k_b,
        rate_a=k_a / n if n else 0.0, rate_b=k_b / n if n else 0.0,
        ci_a=wilson(k_a, n), ci_b=wilson(k_b, n),
        delta=(k_b - k_a) / n if n else 0.0,
        delta_ci=paired_bootstrap_delta(a, b),
        fixed=fixed, broken=broken,
        p_value=paired_flip_test(len(fixed), len(broken)),
        caveat=_caveat(n),
    )


# --- run-level stats (latency, errors, tokens, cost) -------------------------
COLS = {
    "latency": "latency_ms",
    "error": "error",
    "answer": "answer",
    "in_tok": "input_tokens",
    "out_tok": "output_tokens",
    "cost": "cost_usd",          # optional; ignored if the column doesn't exist
}

# Price per 1M tokens in USD. Replace these two numbers with the real prices
# from your provider's pricing page. The values below are EXAMPLES only.
INPUT_PRICE = 0.10     # USD per 1M input tokens
OUTPUT_PRICE = 0.40    # USD per 1M output tokens

PRICES = {"gemini/gemini-3.5-flash-lite": (INPUT_PRICE, OUTPUT_PRICE)}   # USD per 1M tokens
PRICE_MODEL = "gemini/gemini-3.5-flash-lite"


def _percentile(values: list[float], p: float):
    """Linear-interpolation percentile, p in 0..100. None if no values."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    pos = (len(s) - 1) * p / 100
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def run_stats(db: sqlite3.Connection, run_id: str) -> dict:
    existing = {r[1] for r in db.execute("PRAGMA table_info(results)")}
    wanted = {k: v for k, v in COLS.items() if v in existing}
    keys = list(wanted)
    query = f"SELECT {', '.join(wanted[k] for k in keys)} FROM results WHERE run_id = ?"
    rows = [dict(zip(keys, r)) for r in db.execute(query, (run_id,)).fetchall()]

    n = len(rows)
    # Mark each row once (faster than comparing whole dicts)
    is_failed = [bool(r.get("error")) or not (r.get("answer") or "").strip()
                 for r in rows]
    failed = [r for r, f in zip(rows, is_failed) if f]
    ok = [r for r, f in zip(rows, is_failed) if not f]

    latencies = [r["latency"] for r in ok if r.get("latency") is not None]
    in_tok = sum(r.get("in_tok") or 0 for r in rows)
    out_tok = sum(r.get("out_tok") or 0 for r in rows)

    cost = None
    if "cost" in wanted and any(r.get("cost") is not None for r in rows):
        cost = sum(r.get("cost") or 0 for r in rows)
    elif PRICE_MODEL in PRICES and (in_tok or out_tok):
        pin, pout = PRICES[PRICE_MODEL]
        cost = (in_tok * pin + out_tok * pout) / 1_000_000

    return {
        "n": n,
        "n_ok": len(ok),
        "errors": len(failed),
        "error_ci": wilson(len(failed), n),
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
        "in_tok": in_tok,
        "out_tok": out_tok,
        "cost": cost,
        # an error is not an answer, so divide by successful answers
        "cost_per_answer": (cost / len(ok)) if (cost is not None and ok) else None,
    }


def _fmt(v, kind):
    if v is None:
        return "n/a"
    return {"ms": f"{v:.0f} ms", "int": f"{v:,}", "usd": f"${v:.4f}"}[kind]


def _change(a, b, kind):
    if a is None or b is None:
        return ""
    d = b - a
    pct = f" ({d / a:+.0%})" if a else ""
    return {"ms": f"{d:+.0f} ms", "int": f"{d:+,}", "usd": f"{d:+.4f}"}[kind] + pct


def format_run_stats(stats: dict) -> str:
    a, b = stats["a"], stats["b"]
    rows = [
        ("Cases", f"{a['n']}", f"{b['n']}", ""),
        ("Errors / empty",
         f"{a['errors']}/{a['n']} [{a['error_ci'][0]:.0%}-{a['error_ci'][1]:.0%}]",
         f"{b['errors']}/{b['n']} [{b['error_ci'][0]:.0%}-{b['error_ci'][1]:.0%}]", ""),
        ("Latency p50", _fmt(a["p50"], "ms"), _fmt(b["p50"], "ms"), _change(a["p50"], b["p50"], "ms")),
        ("Latency p95", _fmt(a["p95"], "ms"), _fmt(b["p95"], "ms"), _change(a["p95"], b["p95"], "ms")),
        ("Input tokens", _fmt(a["in_tok"], "int"), _fmt(b["in_tok"], "int"), _change(a["in_tok"], b["in_tok"], "int")),
        ("Output tokens", _fmt(a["out_tok"], "int"), _fmt(b["out_tok"], "int"), _change(a["out_tok"], b["out_tok"], "int")),
        ("Cost (run)", _fmt(a["cost"], "usd"), _fmt(b["cost"], "usd"), _change(a["cost"], b["cost"], "usd")),
        ("Cost / answer", _fmt(a["cost_per_answer"], "usd"), _fmt(b["cost_per_answer"], "usd"),
         _change(a["cost_per_answer"], b["cost_per_answer"], "usd")),
    ]
    lines = ["\nCost, latency and errors (A vs B)",
             f"{'':<16}{'A':>22}  {'B':>22}  change", "-" * 80]
    lines += [f"{lab:<16}{x:>22}  {y:>22}  {c}" for lab, x, y, c in rows]

    notes = []
    if min(a["n_ok"], b["n_ok"]) < 30:
        notes.append(f"p95 is based on only {a['n_ok']} (A) and {b['n_ok']} (B) successful answers. "
                     "Treat it as rough.")
    if a["cost"] is None or b["cost"] is None:
        notes.append("Cost is n/a: no cost column and no price set in PRICES.")
    notes.append("Latency from cached or replayed answers is not real latency. "
                 "Compare latency only between uncached runs.")
    lines.append("\nNotes:")
    lines += [f"  - {n}" for n in notes]
    return "\n".join(lines)


def config_diff(db: sqlite3.Connection, run_a: str, run_b: str) -> list[str]:
    """List the settings that differ between the two runs' saved config snapshots."""
    cols = [r[1] for r in db.execute("PRAGMA table_info(runs)")]
    id_col = next((c for c in ("run_id", "id") if c in cols), None)
    snap_col = next((c for c in cols if "snapshot" in c or "config" in c), None)
    if id_col is None or snap_col is None:
        return ["config snapshot not available (no id or snapshot column in runs)"]

    def load(run_id: str) -> dict:
        row = db.execute(
            f"SELECT {snap_col} FROM runs WHERE {id_col} = ?", (run_id,)
        ).fetchone()
        if not row or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    a, b = load(run_a), load(run_b)
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"{k}: {str(a.get(k))[:70]!r} -> {str(b.get(k))[:70]!r}")
    return out or ["no config differences (same settings in both runs)"]


def compare_runs(db: sqlite3.Connection, run_a: str, run_b: str) -> dict:
    A = load_outcomes(db, run_a)
    B = load_outcomes(db, run_b)

    shared = set(A) & set(B)
    only_a = len(set(A) - set(B))
    only_b = len(set(B) - set(A))

    grouped = defaultdict(list)       # (metric, category) -> [(case_id, a, b)]
    errors = defaultdict(lambda: {"a": 0, "b": 0})
    # sorted() keeps the case order (and so the bootstrap CI) the same on every run
    for case_id, metric in sorted(shared):
        cat, pa = A[(case_id, metric)]
        _, pb = B[(case_id, metric)]
        if pa is None or pb is None:
            # errors are reported separately, never counted as "wrong"
            errors[metric]["a"] += pa is None
            errors[metric]["b"] += pb is None
            continue
        grouped[(metric, cat)].append((case_id, pa, pb))

    cells = []
    metrics = sorted({m for m, _ in grouped})
    for metric in metrics:
        overall = [p for (m, _), ps in sorted(grouped.items()) if m == metric for p in ps]
        cells.append(_build_cell(metric, "ALL", overall))
        for (m, cat), ps in sorted(grouped.items()):
            if m == metric:
                cells.append(_build_cell(metric, cat, ps))

    return {
        "run_a": run_a, "run_b": run_b,
        "cells": cells,
        "errors": dict(errors),
        "unpaired": {"only_in_a": only_a, "only_in_b": only_b},
        "stats": {"a": run_stats(db, run_a), "b": run_stats(db, run_b)},
        "config_diff": config_diff(db, run_a, run_b),
    }


def flip_summary(cell: Cell) -> str:
    """One-line summary of the cases that changed between run A and run B."""
    f, b = len(cell.fixed), len(cell.broken)
    flips = f + b
    if flips == 0:
        return "no cases flipped"
    verdict = "significant" if cell.p_value < 0.05 else "not significant"
    caveat = "; few flips, low power" if flips < FEW_FLIPS else ""
    return (f"fixed={f} broken={b} of {cell.n} paired cases; "
            f"exact flip test p={cell.p_value:.3f} ({verdict}{caveat})")


def caveat_notes(result: dict) -> list[str]:
    """Plain-language warnings about how far the numbers can be trusted."""
    notes = []
    for c in result["cells"]:
        if c.category != "ALL":
            continue
        half_width = (c.delta_ci[1] - c.delta_ci[0]) / 2
        if c.n < OVERALL_N_WARN:
            notes.append(
                f"{c.metric}: n = {c.n} paired cases. Treat differences smaller than "
                f"about {half_width:.0%} as noise (half-width of the 95% CI)."
            )
        if len(c.fixed) + len(c.broken) < FEW_FLIPS:
            notes.append(
                f"{c.metric}: only {len(c.fixed) + len(c.broken)} cases changed result, "
                f"so the flip test has low power."
            )

    small = sorted({(c.category, c.n) for c in result["cells"]
                    if c.category != "ALL" and c.n < SMALL_N})
    if small:
        listed = ", ".join(f"{cat} (n={n})" for cat, n in small)
        notes.append(f"Indicative only (fewer than {SMALL_N} cases): {listed}.")

    notes.append("Scores come from an automated judge. Check the calibration results "
                 "before trusting small differences.")
    return notes


def format_table(result: dict) -> str:
    lines = [f"Run A: {result['run_a']}   Run B: {result['run_b']}\n"]

    if "config_diff" in result:
        lines.append("Config differences (A -> B):")
        lines += [f"  - {d}" for d in result["config_diff"]]
        lines.append("")

    hdr = f"{'metric':<16}{'category':<14}{'n':>4}  {'A':>16}  {'B':>16}  {'delta (95% CI)':>24}  note"
    lines += [hdr, "-" * len(hdr)]

    if not result["cells"]:
        lines.append("\nNo scored cases found in both runs. "
                     "Run the judge/labeling step on both runs first.")

    for c in result["cells"]:
        fa = f"{c.k_a}/{c.n} [{c.ci_a[0]:.0%}-{c.ci_a[1]:.0%}]"
        fb = f"{c.k_b}/{c.n} [{c.ci_b[0]:.0%}-{c.ci_b[1]:.0%}]"
        if c.n < MIN_N_FOR_CI:
            fd = f"{c.delta:+.1%} [n/a]"
        else:
            fd = f"{c.delta:+.1%} [{c.delta_ci[0]:+.1%}, {c.delta_ci[1]:+.1%}]"
        note = c.caveat or ("significant" if c.significant else "within noise")
        lines.append(f"{c.metric:<16}{c.category:<14}{c.n:>4}  {fa:>16}  {fb:>16}  {fd:>24}  {note}")
        if c.fixed or c.broken:
            lines.append(f"{'':<16}{flip_summary(c)}")

    if result["errors"]:
        lines.append("\nErrors (excluded from rates): " + str(result["errors"]))
    u = result["unpaired"]
    if u["only_in_a"] or u["only_in_b"]:
        lines.append(f"Warning: cases only in A: {u['only_in_a']}, only in B: {u['only_in_b']} (ignored)")

    if "stats" in result:
        lines.append(format_run_stats(result["stats"]))

    notes = caveat_notes(result)
    if notes:
        lines.append("\nCaveats:")
        lines += [f"  - {n}" for n in notes]
    return "\n".join(lines)


# --- flip details (question, answers and judge reasoning per flipped case) ---
def flip_details(db: sqlite3.Connection, run_a: str, run_b: str,
                 metric: str, case_ids: list[str]) -> list[dict]:
    """For each case id: the question, reference answer, both runs' answers and
    the judge's reasoning for `metric` in both runs."""
    out = []
    for cid in case_ids:
        case = db.execute(
            "SELECT question, reference_answer FROM cases WHERE id = ?", (cid,)
        ).fetchone()
        item = {
            "case_id": cid,
            "question": case[0] if case else None,
            "reference": case[1] if case else None,
        }
        for tag, run in (("a", run_a), ("b", run_b)):
            ans = db.execute(
                "SELECT answer FROM results WHERE run_id = ? AND case_id = ?",
                (run, cid),
            ).fetchone()
            why = db.execute(
                "SELECT reasoning FROM scores WHERE run_id = ? AND case_id = ? AND metric = ?",
                (run, cid, metric),
            ).fetchone()
            item[f"answer_{tag}"] = ans[0] if ans else None
            item[f"judge_{tag}"] = why[0] if why else None
        out.append(item)
    return out


def format_flip_details(title: str, details: list[dict]) -> str:
    """Readable block for one list of flipped cases."""
    lines = [f"\n=== {title}: {len(details)} case(s) ==="]
    if not details:
        lines.append("  (none)")
    for d in details:
        lines.append(f"\n--- {d['case_id']} ---")
        lines.append(f"Q:     {d['question']}")
        lines.append(f"REF:   {d['reference']}")
        lines.append(f"A answer: {d['answer_a']}")
        lines.append(f"A judge:  {d['judge_a']}")
        lines.append(f"B answer: {d['answer_b']}")
        lines.append(f"B judge:  {d['judge_b']}")
    return "\n".join(lines)