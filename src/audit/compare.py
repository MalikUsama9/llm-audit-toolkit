from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from collections import defaultdict

from audit.reporting.stats import wilson, paired_flip_test, paired_bootstrap_delta

SMALL_N = 30          # below this, flag as "indicative only"
VERY_SMALL_N = 15
FEW_FLIPS = 10        # below this many changed cases, the flip test has low power


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


def compare_runs(db: sqlite3.Connection, run_a: str, run_b: str) -> dict:
    A = load_outcomes(db, run_a)
    B = load_outcomes(db, run_b)

    shared = set(A) & set(B)
    only_a = len(set(A) - set(B))
    only_b = len(set(B) - set(A))

    grouped = defaultdict(list)       # (metric, category) -> [(case_id, a, b)]
    errors = defaultdict(lambda: {"a": 0, "b": 0})
    for case_id, metric in shared:
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
        overall = [p for (m, _), ps in grouped.items() if m == metric for p in ps]
        cells.append(_build_cell(metric, "ALL", overall))
        for (m, cat), ps in sorted(grouped.items()):
            if m == metric:
                cells.append(_build_cell(metric, cat, ps))

    return {
        "run_a": run_a, "run_b": run_b,
        "cells": cells,
        "errors": dict(errors),
        "unpaired": {"only_in_a": only_a, "only_in_b": only_b},
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


def format_table(result: dict) -> str:
    lines = [f"Run A: {result['run_a']}   Run B: {result['run_b']}\n"]
    hdr = f"{'metric':<16}{'category':<14}{'n':>4}  {'A':>16}  {'B':>16}  {'delta (95% CI)':>24}  note"
    lines += [hdr, "-" * len(hdr)]

    if not result["cells"]:
        lines.append("\nNo scored cases found in both runs. "
                     "Run the judge/labeling step on both runs first.")

    for c in result["cells"]:
        fa = f"{c.k_a}/{c.n} [{c.ci_a[0]:.0%}-{c.ci_a[1]:.0%}]"
        fb = f"{c.k_b}/{c.n} [{c.ci_b[0]:.0%}-{c.ci_b[1]:.0%}]"
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
    return "\n".join(lines)