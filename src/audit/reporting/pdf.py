"""PDF report builder: SQLite -> summary dict -> Jinja2 HTML -> WeasyPrint PDF."""
import importlib
import inspect
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader
from jinja2 import meta as jinja_meta

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"

_STATS_MODULES = ("audit.reporting.stats", "audit.reporting.summary")
_PREFERRED_NAMES = (
    "build_summary", "build_run_summary", "summarize_run", "get_summary",
    "collect_summary", "load_summary", "make_summary", "summarize",
)


def _as_dict(x):
    """Turn dicts, None, pydantic models, namedtuples or Rows into a plain dict."""
    if isinstance(x, dict):
        return x
    if x is None:
        return {}
    for attr in ("model_dump", "_asdict", "dict"):
        fn = getattr(x, attr, None)
        if callable(fn):
            try:
                return dict(fn())
            except Exception:
                pass
    try:
        return dict(x)
    except Exception:
        return {}


def _find_summary_builder():
    """Locate the function from step 2 that returns the summary dict."""
    seen = []
    for modname in _STATS_MODULES:
        try:
            mod = importlib.import_module(modname)
        except ImportError:
            continue
        for name in _PREFERRED_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                print(f"Using summary function: {modname}.{name}{inspect.signature(fn)}")
                return fn
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            seen.append(f"{modname}.{name}")
            if "summar" in name.lower() and not name.startswith("_"):
                print(f"Using summary function: {modname}.{name}{inspect.signature(fn)}")
                return fn
    raise ImportError(
        "Could not find the summary function from step 2. Functions seen: "
        f"{seen or 'none'}. Edit _PREFERRED_NAMES in pdf.py with the right name."
    )


def _call_builder(fn, db_path, run_id):
    try:
        return fn(db_path, run_id)
    except TypeError as e:
        raise TypeError(
            f"{fn.__module__}.{fn.__name__}{inspect.signature(fn)} did not accept "
            f"(db_path, run_id). Adjust _call_builder in pdf.py. Original error: {e}"
        ) from e


def _get(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def _derive_strengths(categories):
    """Categories with enough cases and a high pass rate."""
    out = []
    for name, c in categories.items():
        n, rate = _get(c, "n", 0) or 0, _get(c, "rate")
        if n >= 5 and rate is not None and rate >= 0.8:
            out.append({"category": name, "n": n, "rate": rate,
                        "text": f"{name}: strong result ({_get(c, 'passed', '?')} of {n} passed)."})
    return out


def _derive_fixes(categories):
    """DRAFT fixes from weak categories. Review by hand before sending to a client."""
    rows = []
    for name, c in categories.items():
        n, rate = _get(c, "n", 0) or 0, _get(c, "rate")
        if n >= 3 and rate is not None and rate < 0.6:
            rows.append((rate, name, n, c))
    rows.sort(key=lambda r: r[0])  # worst first
    return [
        {"priority": i + 1, "category": name, "n": n, "rate": rate,
         "text": f"Investigate '{name}': {_get(c, 'passed', '?')} of {n} passed. "
                 "Review the failure examples below and decide on the root cause.",
         "draft": True}
        for i, (rate, name, n, c) in enumerate(rows)
    ]


def _prepare(summary: dict, run_id) -> dict:
    """Add the names the template expects. Never crashes on None or missing values."""
    summary = dict(_as_dict(summary))
    run = _as_dict(summary.get("run"))
    config = _as_dict(run.get("config"))
    models = _as_dict(config.get("models"))
    usage = _as_dict(summary.get("usage"))
    latency = _as_dict(summary.get("latency"))
    categories = _as_dict(summary.get("categories"))
    overall = _as_dict(summary.get("overall"))

    # Normalize overall so both 'k' and 'passed' are supported interchangeably
    if overall:
        if "passed" not in overall and "k" in overall:
            overall["passed"] = overall["k"]
        elif "k" not in overall and "passed" in overall:
            overall["k"] = overall["passed"]
        summary["overall"] = overall

    defaults = {
        **run,
        "target_name": run.get("target") or run.get("target_name") or "My RAG bot",
        "judge_model": run.get("judge_model") or models.get("judge"),
        "generator_model": models.get("generator") or config.get("model"),
        "run_id": run.get("run_id") or run_id,
    }
    existing = {k: v for k, v in _as_dict(summary.get("meta")).items() if v is not None}
    summary["meta"] = {**defaults, **existing}

    summary["cost"] = _as_dict(summary.get("cost")) or {**usage, **latency}
    summary["errors"] = summary.get("errors") or summary.get("error_cases") or []
    summary["strengths"] = summary.get("strengths") or _derive_strengths(categories)
    summary["fixes"] = summary.get("fixes") or _derive_fixes(categories)
    return summary


def _make_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,                 # bot answers can't break the layout
        undefined=ChainableUndefined,    # a missing key renders empty instead of crashing
    )


def _warn_missing_variables(env, summary):
    """List every template variable that is not in the summary, all at once."""
    src = env.loader.get_source(env, TEMPLATE_NAME)[0]
    needed = jinja_meta.find_undeclared_variables(env.parse(src))
    missing = sorted(k for k in needed if k not in summary and k not in env.globals)
    if missing:
        print("WARNING: template uses variables missing from the summary:", missing)
        print("   Those sections will be empty. Rename them in the template, "
              "or add them in _prepare().")


def render_html(summary: dict, warn_missing: bool = True) -> str:
    """Render an already-prepared summary dict to an HTML string."""
    env = _make_env()
    if warn_missing:
        _warn_missing_variables(env, summary)
    return env.get_template(TEMPLATE_NAME).render(**summary)


def build_report(db_path, run_id, out_path, html_only: bool = False,
                 debug: bool = False):
    raw = _call_builder(_find_summary_builder(), db_path, run_id)
    summary = _prepare(raw, run_id)

    if debug:
        print("SUMMARY KEYS:", list(summary.keys()))

    html = render_html(summary)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Always save the HTML too: it is useful for debugging and is the PDF fallback.
    html_path = out_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    if html_only:  # skip the PDF entirely, handy for checking layout in a browser
        return str(html_path)

    try:
        from weasyprint import HTML  # lazy import: CLI works without its system libs
        HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(str(out_path))
    except Exception as e:
        print(f"PDF generation failed: {e!r}")
        print(f"HTML report saved at {html_path}. Open it in a browser and use "
              "Print -> Save as PDF.")
        return str(html_path)
    return str(out_path)