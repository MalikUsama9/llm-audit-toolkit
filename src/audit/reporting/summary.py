"""Summary data layer: data/audit.db -> one dict for the report template.

Usage (list runs):    python src/audit/reporting/summary.py data/audit.db
Usage (one summary):  python src/audit/reporting/summary.py data/audit.db RUN_ID
"""
import json
import sqlite3
import sys
from math import sqrt

# ---- settings you may edit ------------------------------------------------
PRICE_IN_PER_M = None      # USD per 1M input tokens (from provider's pricing page)
PRICE_OUT_PER_M = None     # USD per 1M output tokens
SMALL_N = 20
REFUSE_BEHAVIORS = {"refuse", "handoff"}
HUMAN_LABELS = ["correct", "partially_correct", "wrong"]
# ---------------------------------------------------------------------------


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    m = z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    i = (len(s) - 1) * q
    lo = int(i)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def cohen_kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in set(a) | set(b))
    return None if pe == 1 else (po - pe) / (1 - pe)


def value_to_label(v):
    if v >= 1.0:
        return "correct"
    return "partially_correct" if v > 0 else "wrong"


def _rows(db, sql, args=()):
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(sql, args).fetchall()]


def list_runs(db_path):
    db = sqlite3.connect(db_path)
    return _rows(db, """
        SELECT r.run_id, r.target_name, r.created_at,
          (SELECT COUNT(*) FROM results x WHERE x.run_id = r.run_id) AS n_results,
          (SELECT COUNT(*) FROM scores s WHERE s.run_id = r.run_id
              AND s.metric IN ('correctness','refusal')) AS n_judged
        FROM runs r ORDER BY n_results DESC, r.created_at DESC""")


def _block(items):
    n = len(items)
    k = sum(r["value"] >= 1.0 for r in items)
    part = sum(0 < r["value"] < 1.0 for r in items)
    lo, hi = wilson(k, n)
    return {"n": n, "passed": k, "partial": part, "failed": n - k - part,
            "rate": k / n if n else None, "ci_low": lo, "ci_high": hi,
            "small_sample": n < SMALL_N}


def _calibration(db):
    rows = _rows(db, """
        SELECT h.label AS human, s.value AS jv
        FROM human_labels h
        JOIN scores s ON s.run_id = h.run_id AND s.case_id = h.case_id
                     AND s.metric = 'correctness'""")
    if not rows:
        return {}
    human = ["wrong" if r["human"] == "hallucinated" else r["human"] for r in rows]
    judge = [value_to_label(r["jv"]) for r in rows]
    n = len(rows)
    agree = sum(h == j for h, j in zip(human, judge))
    cm = {h: {j: 0 for j in HUMAN_LABELS} for h in HUMAN_LABELS}
    for h, j in zip(human, judge):
        if h in cm:
            cm[h][j] += 1
    return {"n": n, "agree": agree, "agreement": agree / n,
            "agreement_ci": wilson(agree, n), "kappa": cohen_kappa(human, judge),
            "confusion": cm, "labels": HUMAN_LABELS,
            "note": "Computed on all labeled cases; report agreement on a held-aside half if you tuned the rubric on these."}


def build_summary(db_path, run_id, top_n=10):
    db = sqlite3.connect(db_path)

    run = _rows(db, "SELECT * FROM runs WHERE run_id = ?", (run_id,))
    if not run:
        raise ValueError(f"run_id not found: {run_id}")
    run = run[0]

    rows = _rows(db, """
        SELECT c.id AS case_id, c.category, c.question, c.reference_answer,
               c.expected_behavior, c.split,
               r.answer, r.latency_ms, r.input_tokens, r.output_tokens, r.error,
               k.status AS check_status
        FROM results r
        JOIN cases c ON c.id = r.case_id
        LEFT JOIN checks k ON k.run_id = r.run_id AND k.case_id = r.case_id
        WHERE r.run_id = ?""", (run_id,))

    sc = {}
    for s in _rows(db, "SELECT case_id, metric, value, reasoning, judge_model "
                       "FROM scores WHERE run_id = ?", (run_id,)):
        sc.setdefault(s["case_id"], {})[s["metric"]] = s

    errors, judged, not_judged = [], [], []
    for r in rows:
        if r["error"] or not r["answer"] or r["check_status"] in ("error", "empty"):
            errors.append(r)
            continue
        order = (["refusal", "correctness"] if r["expected_behavior"] in REFUSE_BEHAVIORS
                 else ["correctness", "refusal"])
        m = next((x for x in order if x in sc.get(r["case_id"], {})), None)
        if m is None:
            not_judged.append(r)
            continue
        s = sc[r["case_id"]][m]
        r.update(metric=m, value=s["value"], reasoning=s["reasoning"], judge_model=s["judge_model"])
        judged.append(r)

    by_cat, by_split = {}, {}
    for r in judged:
        by_cat.setdefault(r["category"], []).append(r)
        if r["split"]:
            by_split.setdefault(r["split"], []).append(r)

    bad = sorted((r for r in judged if r["value"] < 1.0),
                 key=lambda r: (r["value"], r["category"]))[:top_n]
    failures = [{"case_id": r["case_id"], "category": r["category"], "metric": r["metric"],
                 "score": r["value"], "question": r["question"],
                 "reference": r["reference_answer"], "answer": (r["answer"] or "")[:600],
                 "reasoning": r["reasoning"]} for r in bad]

    hits = [s["retrieval_hit"]["value"] for s in sc.values() if "retrieval_hit" in s]
    mrr = [s["retrieval_mrr"]["value"] for s in sc.values() if "retrieval_mrr" in s]
    retrieval = None
    if hits:
        k = sum(h >= 1.0 for h in hits)
        lo, hi = wilson(k, len(hits))
        retrieval = {"n": len(hits), "hits": k, "hit_rate": k / len(hits),
                     "ci_low": lo, "ci_high": hi,
                     "mean_mrr": sum(mrr) / len(mrr) if mrr else None}

    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    tin = sum(r["input_tokens"] or 0 for r in rows)
    tout = sum(r["output_tokens"] or 0 for r in rows)
    cost = None
    if PRICE_IN_PER_M is not None and PRICE_OUT_PER_M is not None:
        cost = tin / 1e6 * PRICE_IN_PER_M + tout / 1e6 * PRICE_OUT_PER_M

    try:
        cfg = json.loads(run.get("config_snapshot") or "{}")
    except json.JSONDecodeError:
        cfg = {}

    statuses = {}
    for r in rows:
        key = r["check_status"] or "none"
        statuses[key] = statuses.get(key, 0) + 1

    return {
        "run": {"run_id": run_id, "target": run.get("target_name"),
                "created_at": run.get("created_at"), "notes": run.get("notes"),
                "judge_model": next((r["judge_model"] for r in judged), None),
                "config": cfg},
        "counts": {"total": len(rows), "judged": len(judged),
                   "errors": len(errors), "not_judged": len(not_judged)},
        "overall": _block(judged),
        "categories": {c: _block(v) for c, v in sorted(by_cat.items())},
        "splits": {c: _block(v) for c, v in sorted(by_split.items())},
        "failures": failures,
        "error_cases": [{"case_id": r["case_id"], "category": r["category"],
                         "error": r["error"] or r["check_status"] or "empty answer"}
                        for r in errors[:10]],
        "check_statuses": statuses,
        "retrieval": retrieval,
        "latency": {"p50_ms": percentile(lat, 0.5), "p95_ms": percentile(lat, 0.95)},
        "usage": {"input_tokens": tin, "output_tokens": tout,
                  "est_cost_usd": cost,
                  "est_cost_per_answer_usd": cost / len(rows) if cost is not None and rows else None},
        "calibration": _calibration(db),
        "limitations": [
            "Results reflect this test set only, scored by an automated judge.",
            "Single-turn questions only; multi-turn conversations and live integrations were not tested.",
            f"Categories with fewer than {SMALL_N} cases are indicative only.",
            "Error cases (timeouts, empty answers) are reported separately and not counted as wrong answers.",
        ],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python summary.py DB_PATH [RUN_ID]")
    if len(sys.argv) == 2:
        print(f"{'run_id':36} {'target':14} {'results':>8} {'judged':>7}")
        for r in list_runs(sys.argv[1])[:15]:
            print(f"{r['run_id']:36} {r['target_name']:14} {r['n_results']:>8} {r['n_judged']:>7}")
    else:
        print(json.dumps(build_summary(sys.argv[1], sys.argv[2]), indent=2, default=str))