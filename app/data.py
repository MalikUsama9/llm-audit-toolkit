"""Query helpers for the dashboard. All SQL lives here, so pages stay simple."""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]  # app\ -> repo root


def open_ro(db_path):
    """Open the database read-only. Relative paths are resolved from the repo root."""
    p = Path(db_path)
    if not p.is_absolute():
        p = ROOT / p
    return sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)


CASE_ID = "id"            # change to "case_id" if your cases table uses that
CORRECT_MIN = 1.0         # correctness value that counts as fully correct


@st.cache_data(ttl=60)
def query(db_path, sql, params=()):
    con = open_ro(db_path)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


# ---------- runs ----------
def list_runs(db_path, scored_only=True):
    if scored_only:
        sql = ("select run_id from runs where run_id in "
               "(select distinct run_id from scores) order by rowid desc")
    else:
        sql = "select run_id from runs order by rowid desc"
    return query(db_path, sql)["run_id"].tolist()


def get_run(db_path, run_id):
    return query(db_path, "select * from runs where run_id=?", (run_id,))


# ---------- cases ----------
def get_cases(db_path):
    return query(db_path, "select * from cases")


# ---------- results ----------
def get_results(db_path, run_id):
    return query(db_path, "select * from results where run_id=?", (run_id,))


def result_counts(db_path, run_id):
    return query(
        db_path,
        "select count(*) as n, "
        "sum(case when error is not null and error != '' then 1 else 0 end) as errors "
        "from results where run_id=?", (run_id,)).iloc[0]


# ---------- scores ----------
def get_scores(db_path, run_id, metric=None):
    if metric:
        return query(db_path,
                     "select * from scores where run_id=? and metric=?",
                     (run_id, metric))
    return query(db_path, "select * from scores where run_id=?", (run_id,))


def metric_summary(db_path, run_id):
    """One row per metric: cases scored and mean value (pre-aggregated in SQL)."""
    return query(
        db_path,
        "select metric, count(*) as cases, round(avg(value), 3) as mean_value "
        "from scores where run_id=? group by metric order by metric", (run_id,))


def correctness_totals(db_path, run_id):
    """(k fully-correct, n scored) for the correctness metric."""
    r = query(
        db_path,
        "select count(*) as n, "
        "sum(case when value >= ? then 1 else 0 end) as k "
        "from scores where run_id=? and metric='correctness'",
        (CORRECT_MIN, run_id)).iloc[0]
    return int(r["k"] or 0), int(r["n"] or 0)


def correctness_by_category(db_path, run_id):
    """Per-category n, fully correct, partial. Used by the category page."""
    return query(
        db_path,
        f"select c.category, count(*) as n, "
        f"sum(case when s.value >= {CORRECT_MIN} then 1 else 0 end) as k, "
        f"sum(case when s.value = 0.5 then 1 else 0 end) as partial "
        f"from scores s join cases c on c.{CASE_ID} = s.case_id "
        f"where s.run_id=? and s.metric='correctness' "
        f"group by c.category order by c.category", (run_id,))


def failures(db_path, run_id):
    """Cases not fully correct, with answer, reference and judge reasoning."""
    return query(
        db_path,
        f"select s.case_id, c.category, s.value, c.question, "
        f"c.reference_answer, r.answer, s.reasoning, r.error "
        f"from scores s "
        f"join cases c on c.{CASE_ID} = s.case_id "
        f"left join results r on r.run_id = s.run_id and r.case_id = s.case_id "
        f"where s.run_id=? and s.metric='correctness' and s.value < {CORRECT_MIN} "
        f"order by s.value asc, c.category", (run_id,))


def correctness_breakdown(db_path, run_id):
    """Counts of fully correct, partial and wrong correctness scores."""
    r = query(
        db_path,
        "select count(*) as n, "
        "sum(case when value >= ? then 1 else 0 end) as correct, "
        "sum(case when value > 0 and value < ? then 1 else 0 end) as partial, "
        "sum(case when value = 0 then 1 else 0 end) as wrong "
        "from scores where run_id=? and metric='correctness'",
        (CORRECT_MIN, CORRECT_MIN, run_id)).iloc[0]
    return {k: int(r[k] or 0) for k in ("n", "correct", "partial", "wrong")}


# ---------- run comparison ----------
def compare_cases(db_path, run_a, run_b):
    """Correctness of the same case in two runs (only cases scored in both).

    Columns: case_id, category, question, value_a (baseline), value_b (new).
    """
    return query(
        db_path,
        f"select s1.case_id, c.category, c.question, "
        f"s1.value as value_a, s2.value as value_b "
        f"from scores s1 "
        f"join scores s2 on s2.case_id = s1.case_id "
        f"and s2.run_id = ? and s2.metric = 'correctness' "
        f"join cases c on c.{CASE_ID} = s1.case_id "
        f"where s1.run_id = ? and s1.metric = 'correctness' "
        f"order by c.category, s1.case_id", (run_b, run_a))


# ---------- cost and latency ----------
def latency_summary(db_path, run_id):
    df = get_results(db_path, run_id)
    ok = df[df["error"].isna() | (df["error"] == "")]
    if ok.empty:
        return {}
    return {
        "answers": len(ok),
        "p50_ms": float(ok["latency_ms"].quantile(0.5)),
        "p95_ms": float(ok["latency_ms"].quantile(0.95)),
        "input_tokens": int(ok["input_tokens"].sum()),
        "output_tokens": int(ok["output_tokens"].sum()),
    }


def latency_by_case(db_path, run_id):
    """One row per answered case: latency, tokens and bot error (slowest first)."""
    return query(
        db_path,
        f"select r.case_id, c.category, r.latency_ms, "
        f"r.input_tokens, r.output_tokens, r.error "
        f"from results r left join cases c on c.{CASE_ID} = r.case_id "
        f"where r.run_id=? order by r.latency_ms desc", (run_id,))