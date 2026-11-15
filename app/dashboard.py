import sqlite3

import pandas as pd
import streamlit as st

import data
from audit.reporting.stats import wilson

st.set_page_config(page_title="Chatbot Quality Audit", layout="wide")

DEFAULT_DB = "data/audit.db"   # switch to the demo DB in the "Demo database" block


@st.cache_data(ttl=60)
def run_query(db_path, sql, params=()):
    """Run a read-only query and return a DataFrame (cached for 60 s)."""
    con = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


# ---------- sidebar ----------
st.sidebar.title("Chatbot Quality Audit")
db_path = st.sidebar.text_input("Database path", DEFAULT_DB)

show_unscored = st.sidebar.checkbox("Show unscored runs", value=False)
try:
    run_list = data.list_runs(db_path, scored_only=not show_unscored)
except Exception as e:
    st.sidebar.error(f"Cannot read database: {e}")
    st.stop()

if not run_list:
    if show_unscored:
        st.sidebar.warning("No runs in this database.")
    else:
        st.sidebar.warning("No scored runs yet. Tick 'Show unscored runs' to see all runs.")
    st.stop()

run_id = st.sidebar.selectbox("Run", run_list)
page = st.sidebar.radio(
    "Page",
    ["Overview", "Categories", "Failure explorer",
     "Run comparison", "Cost and latency"],
)


# ---------- pages ----------
def page_overview():
    st.header("Overview")

    counts = data.result_counts(db_path, run_id)
    n_results = int(counts["n"])
    n_errors = int(counts["errors"] or 0)
    b = data.correctness_breakdown(db_path, run_id)
    n = b["n"]
    judge_failed = max(n_results - n, 0)   # answered but have no correctness score

    # Row 1: every number shows its denominator
    c1, c2, c3 = st.columns(3)
    c1.metric("Cases answered", f"{n_results}")
    c2.metric("Bot errors / empty answers", f"{n_errors} of {n_results}")
    c3.metric("Judge failures (no score)", f"{judge_failed} of {n_results}")
    if judge_failed:
        st.warning(f"{judge_failed} answered cases have no correctness score "
                   "(judge failure or not yet scored). They are excluded from accuracy.")

    if n == 0:
        st.warning("This run has no correctness scores yet.")
        return

    # Row 2: accuracy with Wilson CI
    k = b["correct"]
    lo, hi = wilson(k, n)
    st.subheader("Correctness")
    a1, a2 = st.columns(2)
    a1.metric(f"Fully correct (n = {n})", f"{k} of {n}  ({k / n:.1%})")
    a2.metric("95% confidence interval", f"{lo:.1%} to {hi:.1%}")

    # Row 3: full breakdown
    st.write(f"Breakdown of {n} scored cases: "
             f"**{b['correct']} correct**, "
             f"**{b['partial']} partially correct**, "
             f"**{b['wrong']} wrong**.")
    if n < 30:
        st.caption(f"Only {n} scored cases (fewer than 30): treat this as indicative only.")

    # Row 4: all metrics, with n per metric
    st.subheader("All metrics in this run")
    summary = data.metric_summary(db_path, run_id).rename(
        columns={"cases": "n (cases scored)", "mean_value": "mean score (0 to 1)"})
    st.dataframe(summary, use_container_width=True, hide_index=True)


def page_categories():
    st.header("Category breakdown")
    st.info("Coming in the category block.")


def page_failures():
    st.header("Failure explorer")
    st.info("Coming in the failure explorer block.")


def page_compare():
    st.header("Run comparison")
    st.info("Coming in the run comparison block.")


def page_cost():
    st.header("Cost and latency")
    st.info("Coming in the cost and latency block.")


{
    "Overview": page_overview,
    "Categories": page_categories,
    "Failure explorer": page_failures,
    "Run comparison": page_compare,
    "Cost and latency": page_cost,
}[page]()