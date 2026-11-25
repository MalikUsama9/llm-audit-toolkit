import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
from data import open_ro
from audit.compare import (
    MIN_N_FOR_CI, PRICE_MODEL, PRICES, caveat_notes, compare_runs,
    flip_details, flip_summary, format_table, run_stats,
)
from audit.reporting.summary import wilson

st.set_page_config(page_title="Chatbot Quality Audit", layout="wide")

# The dashboard opens the fictional demo database by default.
# To look at your own private database, set the AUDIT_DB environment variable
# (for example  $env:AUDIT_DB = "data/audit.db"  in PowerShell) or type the
# path into the "Database path" box in the sidebar.
ROOT = Path(__file__).resolve().parents[1]  # app\ -> repo root
DEFAULT_DB = os.environ.get("AUDIT_DB", str(ROOT / "data" / "demo" / "demo.db"))


@st.cache_data(ttl=60)
def run_query(db_path, sql, params=()):
    """Run a read-only query and return a DataFrame (cached for 60 s)."""
    con = open_ro(db_path)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def text_or(value, fallback):
    """Return value if it is a non-empty string, otherwise the fallback text."""
    return value if isinstance(value, str) and value.strip() else fallback


@st.cache_data(ttl=60)
def load_comparison(db_path, run_a, run_b):
    """Call compare_runs from audit/compare.py (no maths is redone here).

    Also loads question, answers and judge reasoning for every fixed and
    newly broken case, per metric."""
    con = open_ro(db_path)
    try:
        result = compare_runs(con, run_a, run_b)
        details = {}
        for c in result["cells"]:
            if c.category == "ALL":
                details[c.metric] = {
                    "fixed": flip_details(con, run_a, run_b, c.metric, c.fixed),
                    "broken": flip_details(con, run_a, run_b, c.metric, c.broken),
                }
        return result, details
    finally:
        con.close()


@st.cache_data(ttl=60)
def load_run_stats(db_path, run_ids):
    """One row per run, from run_stats() in audit/compare.py (nothing recalculated)."""
    con = open_ro(db_path)
    try:
        rows = []
        for rid in run_ids:
            st_ = run_stats(con, rid)
            rows.append({
                "run": rid,
                "answers": st_["n_ok"],
                "errors": st_["errors"],
                "p50_ms": st_["p50"],
                "p95_ms": st_["p95"],
                "input_tokens": st_["in_tok"],
                "output_tokens": st_["out_tok"],
                "cost_usd": st_["cost"],
                "cost_per_answer_usd": st_["cost_per_answer"],
            })
        return pd.DataFrame(rows)
    finally:
        con.close()


# ---------- sidebar ----------
st.sidebar.title("Chatbot Quality Audit")
db_path = st.sidebar.text_input("Database path", DEFAULT_DB)
if "demo" in db_path.replace("\\", "/").lower():
    st.sidebar.caption("Demo database: fictional data only.")

# Opening a missing path would silently create an empty database file, which
# then fails with "no such table". Check first and explain what to do.
if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
    st.sidebar.error(f"No database found at {db_path}.")
    st.error(
        f"The database file **{db_path}** does not exist or is empty. "
        "Build the demo database first:\n\n"
        "`python scripts/make_demo_db.py list --source data/audit.db`\n\n"
        "then\n\n"
        "`python scripts/make_demo_db.py build --source data/audit.db "
        "--out data/demo/demo.db --runs RUN_ID_1 RUN_ID_2`")
    st.stop()

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
    ["Overview", "Categories", "Failure explorer", "Worst answers",
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
    st.dataframe(summary, width="stretch", hide_index=True)


def page_categories():
    st.header("Category breakdown")
    df = data.correctness_by_category(db_path, run_id)
    if df.empty:
        st.warning("No correctness scores for this run.")
        return

    rows = []
    for _, r in df.iterrows():
        n, k, partial = int(r["n"]), int(r["k"]), int(r["partial"])
        lo, hi = wilson(k, n)
        rows.append({
            "category": r["category"], "n": n, "correct": k,
            "partial": partial, "wrong": n - k - partial,
            "acc": k / n, "lo": lo, "hi": hi,
            "note": "indicative only" if n < 30 else "",
        })
    t = pd.DataFrame(rows)

    fig = go.Figure(go.Bar(
        x=[f"{c}<br>(n={n})" for c, n in zip(t["category"], t["n"])],
        y=t["acc"] * 100,
        error_y=dict(
            type="data", symmetric=False,
            array=(t["hi"] - t["acc"]) * 100,
            arrayminus=(t["acc"] - t["lo"]) * 100),
        text=[f"{a:.0%}" for a in t["acc"]], textposition="outside",
    ))
    fig.update_layout(
        title="Fully correct answers by category (% of scored cases, 95% Wilson CI)",
        yaxis_title="% fully correct", xaxis_title="Category (n = cases scored)",
        yaxis_range=[0, 110])
    st.plotly_chart(fig, width="stretch")

    st.caption("Error bars are 95% Wilson confidence intervals. "
               "Categories with fewer than 30 cases are indicative only.")

    show = t.assign(
        accuracy=[f"{a:.1%}" for a in t["acc"]],
        ci_95=[f"{l:.0%} to {h:.0%}" for l, h in zip(t["lo"], t["hi"])],
    )[["category", "n", "correct", "partial", "wrong", "accuracy", "ci_95", "note"]]
    st.dataframe(show, width="stretch", hide_index=True)


def page_failures():
    st.header("Failure explorer")
    df = data.failures(db_path, run_id)
    if df.empty:
        st.success("No failed cases in this run (or it has no correctness scores yet).")
        return

    df = df.copy()
    df["verdict"] = (df["value"].map({0.0: "wrong", 0.5: "partially correct"})
                     .fillna("other"))
    df["bot_error"] = df["error"].fillna("").astype(str).str.strip() != ""

    # ---------- filters ----------
    f1, f2, f3 = st.columns(3)
    cats = sorted(df["category"].dropna().unique())
    sel_cats = f1.multiselect("Category", cats, default=cats)
    verdicts = sorted(df["verdict"].unique())
    sel_verdicts = f2.multiselect("Verdict", verdicts, default=verdicts)
    err_mode = f3.selectbox(
        "Bot error", ["All", "Only with bot error", "Only without bot error"])

    view = df[df["category"].isin(sel_cats) & df["verdict"].isin(sel_verdicts)]
    if err_mode == "Only with bot error":
        view = view[view["bot_error"]]
    elif err_mode == "Only without bot error":
        view = view[~view["bot_error"]]
    view = view.reset_index(drop=True)

    st.write(f"Showing **{len(view)} of {len(df)}** failed cases "
             "(cases that were not fully correct). Click a row to see the details.")
    if view.empty:
        st.info("No cases match these filters.")
        return

    # ---------- table ----------
    table = view[["case_id", "category", "verdict", "value", "bot_error"]].rename(
        columns={"value": "score (0 to 1)"})

    # The key changes whenever a filter changes, so an old row selection is reset
    # instead of pointing at a different case.
    filter_key = "|".join([
        str(run_id),
        ",".join(map(str, sel_cats)),
        ",".join(map(str, sel_verdicts)),
        err_mode,
    ])
    event = st.dataframe(
        table, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row",
        key=f"failure_table_{filter_key}")

    # ---------- detail ----------
    rows = event.selection.rows
    if not rows or rows[0] >= len(view):
        st.caption("No row selected yet.")
        return
    r = view.iloc[rows[0]]

    st.subheader(f"Case {r['case_id']}  ({r['category']}, {r['verdict']})")
    st.markdown(f"**Question:** {r['question']}")
    left, right = st.columns(2)
    with left:
        st.markdown("**Bot answer**")
        st.info(text_or(r["answer"], "(no answer stored)"))
    with right:
        st.markdown("**Reference answer**")
        st.success(text_or(r["reference_answer"],
                           "(none: case should not be answerable)"))
    st.markdown("**Judge reasoning**")
    st.write(text_or(r["reasoning"], "(no reasoning stored)"))
    if r["bot_error"]:
        st.error(f"Bot error: {r['error']}")


def page_worst():
    st.header("10 worst answers")
    df = data.failures(db_path, run_id)
    if df.empty:
        st.success("No failed cases in this run (or it has no correctness scores yet).")
        return

    df = df.copy()
    df["verdict"] = (df["value"].map({0.0: "wrong", 0.5: "partially correct"})
                     .fillna("other"))
    df["bot_error"] = df["error"].fillna("").astype(str).str.strip() != ""

    # Worst first: lowest score, then cases where the bot itself errored.
    worst = (df.sort_values(["value", "bot_error", "case_id"],
                            ascending=[True, False, True])
               .head(10).reset_index(drop=True))

    st.caption(f"Ranked by judge score (wrong first, then partially correct); "
               f"bot errors come first within the same score. "
               f"Showing {len(worst)} of {len(df)} failed cases in this run.")

    # Quick summary table: a reader sees all 10 at a glance
    summary = pd.DataFrame({
        "rank": range(1, len(worst) + 1),
        "case_id": worst["case_id"],
        "category": worst["category"],
        "verdict": worst["verdict"],
        "score (0 to 1)": worst["value"],
        "question": worst["question"],
    })
    st.dataframe(summary, width="stretch", hide_index=True)

    st.subheader("Details")
    for i, r in worst.iterrows():
        with st.container(border=True):
            st.markdown(f"**#{i + 1}  Case {r['case_id']}**  "
                        f"({r['category']}, {r['verdict']}, score {r['value']})")
            st.markdown(f"**Question:** {r['question']}")
            st.markdown("**Bot answer**")
            st.info(text_or(r["answer"], "(no answer stored)"))
            left, right = st.columns(2)
            with left:
                st.markdown("**Reference answer**")
                st.success(text_or(r["reference_answer"],
                                   "(none: case should not be answerable)"))
            with right:
                st.markdown("**Judge reasoning**")
                st.warning(text_or(r["reasoning"], "(no reasoning stored)"))
            if r["bot_error"]:
                st.error(f"Bot error: {r['error']}")


def show_flipped(items, empty_msg, run_a, run_b):
    """One expander per case that changed between run A and run B."""
    if not items:
        st.info(empty_msg)
        return
    for d in items:
        question = text_or(d["question"], "(no question stored)")
        short = question if len(question) <= 90 else question[:87] + "..."
        with st.expander(f"{d['case_id']}: {short}"):
            st.markdown(f"**Question:** {question}")
            st.markdown("**Reference answer**")
            st.success(text_or(d["reference"], "(none: case should not be answerable)"))
            left, right = st.columns(2)
            with left:
                st.markdown(f"**Run A answer** ({run_a})")
                st.info(text_or(d["answer_a"], "(no answer stored)"))
                st.markdown("**Run A judge reasoning**")
                st.write(text_or(d["judge_a"], "(no reasoning stored)"))
            with right:
                st.markdown(f"**Run B answer** ({run_b})")
                st.info(text_or(d["answer_b"], "(no answer stored)"))
                st.markdown("**Run B judge reasoning**")
                st.write(text_or(d["judge_b"], "(no reasoning stored)"))


def page_compare():
    st.header("Run comparison")
    if len(run_list) < 2:
        st.info("You need at least two runs to compare. "
                "Run the audit pipeline again to create a second run.")
        return

    c1, c2 = st.columns(2)
    run_a = c1.selectbox("Run A (baseline)", run_list, index=1, key="cmp_run_a")
    run_b = c2.selectbox("Run B (new)", run_list, index=0, key="cmp_run_b")
    if run_a == run_b:
        st.warning("Pick two different runs to compare.")
        return

    try:
        result, details = load_comparison(db_path, run_a, run_b)
    except Exception as e:
        st.error(f"Could not compare these runs: {e}")
        return

    # ---------- settings that differ ----------
    with st.expander("Settings that differ between the two runs"):
        for line in result["config_diff"]:
            st.write(f"- {line}")

    overall = [c for c in result["cells"] if c.category == "ALL"]
    if not overall:
        st.warning("No scored cases found in both runs. "
                   "Run the judge step on both runs first.")
        return

    # ---------- pick the metric (usually only correctness) ----------
    metrics = [c.metric for c in overall]
    if len(metrics) > 1:
        default = metrics.index("correctness") if "correctness" in metrics else 0
        metric = st.selectbox("Metric", metrics, index=default)
    else:
        metric = metrics[0]
    cell = next(c for c in overall if c.metric == metric)

    # ---------- accuracy with confidence intervals ----------
    st.subheader("Accuracy")
    st.caption(f"Compared on the {cell.n} cases that were scored in both runs "
               "(cases with a bot error are excluded).")
    m1, m2, m3 = st.columns(3)
    m1.metric("Run A fully correct", f"{cell.k_a} of {cell.n}  ({cell.rate_a:.1%})")
    m1.caption(f"95% CI: {cell.ci_a[0]:.1%} to {cell.ci_a[1]:.1%}")
    m2.metric("Run B fully correct", f"{cell.k_b} of {cell.n}  ({cell.rate_b:.1%})")
    m2.caption(f"95% CI: {cell.ci_b[0]:.1%} to {cell.ci_b[1]:.1%}")
    m3.metric("Change (B minus A)", f"{cell.delta * 100:+.1f} points")
    if cell.n < MIN_N_FOR_CI:
        m3.caption("95% CI of the change: n/a (too few cases)")
    else:
        m3.caption(f"95% CI of the change: {cell.delta_ci[0]:+.1%} "
                   f"to {cell.delta_ci[1]:+.1%}")

    if cell.significant:
        st.success("The difference is statistically significant: the confidence "
                   "interval excludes zero and the flip test agrees.")
    else:
        st.info("No clear difference: the change is within noise.")
    if cell.caveat:
        st.caption(cell.caveat)

    # ---------- flip test ----------
    st.subheader("Flip test")
    f1, f2, f3 = st.columns(3)
    f1.metric("Fixed (wrong in A, right in B)", len(cell.fixed))
    f2.metric("Newly broken (right in A, wrong in B)", len(cell.broken))
    f3.metric("Flip test p-value", f"{cell.p_value:.3f}")
    st.caption(flip_summary(cell))

    # ---------- fixed and newly broken cases ----------
    st.subheader("Fixed and newly broken cases")
    tab_broken, tab_fixed = st.tabs(
        [f"Newly broken ({len(cell.broken)})", f"Fixed ({len(cell.fixed)})"])
    with tab_broken:
        show_flipped(details[metric]["broken"],
                     "No newly broken cases: nothing that was right in A is wrong in B.",
                     run_a, run_b)
    with tab_fixed:
        show_flipped(details[metric]["fixed"],
                     "No fixed cases: nothing that was wrong in A is right in B.",
                     run_a, run_b)

    # ---------- by category ----------
    st.subheader("By category")
    cats = [c for c in result["cells"]
            if c.metric == metric and c.category != "ALL"]
    if cats:
        rows = []
        for c in cats:
            ci = ("n/a" if c.n < MIN_N_FOR_CI
                  else f"{c.delta_ci[0]:+.1%} to {c.delta_ci[1]:+.1%}")
            rows.append({
                "category": c.category,
                "n": c.n,
                "run A": f"{c.k_a}/{c.n} ({c.rate_a:.0%})",
                "run B": f"{c.k_b}/{c.n} ({c.rate_b:.0%})",
                "change": f"{c.delta:+.1%}",
                "95% CI of change": ci,
                "fixed": len(c.fixed),
                "broken": len(c.broken),
                "flip test p": round(c.p_value, 3),
                "note": c.caveat or ("significant" if c.significant else "within noise"),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ---------- errors and unpaired cases ----------
    err = result["errors"].get(metric, {"a": 0, "b": 0})
    if err["a"] or err["b"]:
        st.warning(f"Cases with a bot error (excluded from the rates above): "
                   f"{err['a']} in run A, {err['b']} in run B.")
    u = result["unpaired"]
    if u["only_in_a"] or u["only_in_b"]:
        st.warning(f"Scored cases found in only one run (ignored): "
                   f"{u['only_in_a']} only in A, {u['only_in_b']} only in B.")

    # ---------- caveats ----------
    st.subheader("Caveats")
    st.markdown("\n".join(f"- {n}" for n in caveat_notes(result)))

    # ---------- same text as the command line ----------
    with st.expander("Full text output (same as `audit compare`)"):
        st.code(format_table(result), language="text")


def page_cost():
    st.header("Cost and latency")
    st.info("Latency from cached or replayed answers is not real latency. "
            "Compare latency only between uncached runs.")

    # ---------- how many runs to chart ----------
    n_runs = len(run_list)
    show_n = int(st.number_input(
        "Number of latest runs to chart", min_value=1,
        max_value=min(n_runs, 20), value=min(n_runs, 10), step=1))
    runs = list(reversed(run_list[:show_n]))          # oldest on the left
    df = load_run_stats(db_path, tuple(runs))

    # ---------- table ----------
    st.subheader("Per-run summary")
    table = df.rename(columns={
        "run": "run", "answers": "answers (no error)", "errors": "errors",
        "p50_ms": "p50 latency (ms)", "p95_ms": "p95 latency (ms)",
        "input_tokens": "input tokens", "output_tokens": "output tokens",
        "cost_usd": "cost (USD)", "cost_per_answer_usd": "cost per answer (USD)"})
    table["p50 latency (ms)"] = table["p50 latency (ms)"].round(0)
    table["p95 latency (ms)"] = table["p95 latency (ms)"].round(0)
    table["cost (USD)"] = table["cost (USD)"].round(4)
    table["cost per answer (USD)"] = table["cost per answer (USD)"].round(5)
    st.dataframe(table, width="stretch", hide_index=True)
    if (df["answers"] < 30).any():
        st.caption("Some runs have fewer than 30 answers: their p95 latency is rough.")

    # ---------- latency chart ----------
    st.subheader("Latency")
    if df["p50_ms"].isna().all():
        st.warning("No latency was recorded for these runs.")
    else:
        log_scale = st.checkbox(
            "Log scale (keeps small runs readable next to one very slow run)",
            value=False)
        fig = go.Figure([
            go.Bar(name="p50 (median)", x=df["run"], y=df["p50_ms"]),
            go.Bar(name="p95", x=df["run"], y=df["p95_ms"]),
        ])
        fig.update_layout(
            title="Answer latency per run: p50 and p95 (ms)",
            barmode="group", xaxis_title="Run",
            yaxis_title="Latency (ms, log scale)" if log_scale else "Latency (ms)")
        if log_scale:
            fig.update_yaxes(type="log")
        st.plotly_chart(fig, width="stretch")

    # ---------- tokens chart ----------
    st.subheader("Tokens")
    fig = go.Figure([
        go.Bar(name="input tokens", x=df["run"], y=df["input_tokens"]),
        go.Bar(name="output tokens", x=df["run"], y=df["output_tokens"]),
    ])
    fig.update_layout(
        title="Tokens per run: input and output (tokens)",
        barmode="stack", xaxis_title="Run", yaxis_title="Tokens")
    st.plotly_chart(fig, width="stretch")

    # ---------- cost chart ----------
    st.subheader("Cost")
    if df["cost_usd"].isna().all():
        st.warning("Cost is not available: the results table has no cost column "
                   "and no price is set in src/audit/compare.py (PRICES).")
    else:
        fig = go.Figure(go.Bar(
            x=df["run"], y=df["cost_usd"],
            text=[f"${c:.4f}" if pd.notna(c) else "n/a" for c in df["cost_usd"]],
            textposition="outside"))
        fig.update_layout(
            title="Estimated cost per run (USD)",
            xaxis_title="Run", yaxis_title="Cost (USD)")
        st.plotly_chart(fig, width="stretch")
        prices = PRICES.get(PRICE_MODEL)
        if prices:
            st.caption(f"Cost comes from the cost_usd column if the results table has "
                       f"one. Otherwise it is calculated from the prices in "
                       f"src/audit/compare.py for {PRICE_MODEL}: ${prices[0]} per 1M "
                       f"input tokens and ${prices[1]} per 1M output tokens. "
                       "Check that these are your provider's real prices. "
                       "Cost covers the bot's answers only, not the judge.")

    # ---------- selected run: detail ----------
    st.subheader(f"Selected run: {run_id}")
    detail = data.latency_by_case(db_path, run_id)
    if detail.empty:
        st.warning("This run has no stored answers.")
        return
    detail = detail.copy()
    detail["category"] = detail["category"].fillna("(no category)")
    detail["bot_error"] = detail["error"].fillna("").astype(str).str.strip() != ""
    ok = detail[~detail["bot_error"]].copy()
    ok["output_tokens"] = ok["output_tokens"].fillna(0)
    lat = ok["latency_ms"].dropna()
    if lat.empty:
        st.warning("No latency was recorded for this run.")
        return

    p50 = float(lat.quantile(0.5))
    p95 = float(lat.quantile(0.95))
    hist = go.Figure(go.Histogram(x=lat, nbinsx=20))
    hist.add_vline(x=p50, line_dash="dash", annotation_text=f"p50 {p50:,.0f} ms")
    hist.add_vline(x=p95, line_dash="dot", annotation_text=f"p95 {p95:,.0f} ms")
    hist.update_layout(
        title="How long answers took in the selected run (ms per case)",
        xaxis_title="Latency (ms)", yaxis_title="Number of cases")
    st.plotly_chart(hist, width="stretch")

    g = (ok.groupby("category")
           .agg(n=("case_id", "count"),
                median_ms=("latency_ms", "median"),
                p95_ms=("latency_ms", lambda x: x.quantile(0.95)),
                avg_output_tokens=("output_tokens", "mean"))
           .round(0).reset_index())
    g = g.rename(columns={"median_ms": "p50 latency (ms)",
                          "p95_ms": "p95 latency (ms)",
                          "avg_output_tokens": "avg output tokens"})
    st.markdown("**Latency by category**")
    st.dataframe(g, width="stretch", hide_index=True)

    st.markdown("**10 slowest answers**")
    slow = ok.nlargest(10, "latency_ms")[
        ["case_id", "category", "latency_ms", "output_tokens"]].copy()
    slow["latency_ms"] = slow["latency_ms"].round(0).astype(int)
    slow["output_tokens"] = slow["output_tokens"].round(0).astype(int)
    slow = slow.rename(
        columns={"latency_ms": "latency (ms)", "output_tokens": "output tokens"})
    st.dataframe(slow, width="stretch", hide_index=True)


{
    "Overview": page_overview,
    "Categories": page_categories,
    "Failure explorer": page_failures,
    "Worst answers": page_worst,
    "Run comparison": page_compare,
    "Cost and latency": page_cost,
}[page]()