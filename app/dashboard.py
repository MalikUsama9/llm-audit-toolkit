import sqlite3
import pandas as pd
import streamlit as st

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
    if show_unscored:
        runs = run_query(db_path, "select run_id from runs order by rowid desc")
    else:
        runs = run_query(
            db_path,
            "select run_id from runs where run_id in "
            "(select distinct run_id from scores) order by rowid desc")
except Exception as e:
    st.sidebar.error(f"Cannot read database: {e}")
    st.stop()

if runs.empty:
    if show_unscored:
        st.sidebar.warning("No runs in this database.")
    else:
        st.sidebar.warning("No scored runs yet. Tick 'Show unscored runs' to see all runs.")
    st.stop()

run_id = st.sidebar.selectbox("Run", runs["run_id"].tolist())
page = st.sidebar.radio(
    "Page",
    ["Overview", "Categories", "Failure explorer",
     "Run comparison", "Cost and latency"],
)


# ---------- pages (filled in during the next blocks) ----------
def page_overview():
    st.header("Overview")
    scores = run_query(
        db_path,
        "select case_id, metric, value from scores where run_id=?", (run_id,))
    res = run_query(
        db_path,
        "select count(*) as n, "
        "sum(case when error is not null and error != '' then 1 else 0 end) as errors "
        "from results where run_id=?", (run_id,))

    n_results = int(res["n"][0])
    n_errors = int(res["errors"][0] or 0)

    corr = scores[scores["metric"] == "correctness"]
    n = len(corr)
    k = int((corr["value"] >= 1.0).sum())   # change if your values differ

    c1, c2, c3 = st.columns(3)
    c1.metric("Cases answered", n_results)
    c2.metric("Cases scored (correctness)", n)
    c3.metric("Errors / empty answers", n_errors)

    if n == 0:
        st.warning("This run has no correctness scores yet.")
        return

    lo, hi = wilson(k, n)
    st.subheader("Correctness")
    st.metric(f"{k} of {n} correct", f"{k / n:.1%}",
              help="95% Wilson confidence interval shown below")
    st.write(f"95% confidence interval: **{lo:.1%} to {hi:.1%}** (n = {n})")
    if n < 30:
        st.caption("Fewer than 30 scored cases: treat this as indicative only.")

    st.subheader("All metrics in this run")
    summary = (scores.groupby("metric")["value"]
               .agg(cases="count", mean_value="mean").round(3).reset_index())
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