"""Compare the variables the template uses with the keys the summary provides."""
import sys
from pathlib import Path

import jinja2
from jinja2 import Template, meta

from audit.reporting.pdf import build_report

DB = sys.argv[1] if len(sys.argv) > 1 else "data/audit.db"
RUN_ID = sys.argv[2]  # pass a run_id from your DB
TEMPLATE = Path("src/audit/reporting/templates/report.html.j2")

captured = {}
_orig = Template.render


def _spy(self, *args, **kwargs):
    captured.update(dict(*args, **kwargs))
    return _orig(self, *args, **kwargs)


Template.render = _spy

try:
    build_report(DB, RUN_ID, "check_report.pdf")
    print("build_report finished without errors")
except Exception as e:
    print(f"build_report raised: {type(e).__name__}: {e}")

env = jinja2.Environment()
used = meta.find_undeclared_variables(env.parse(TEMPLATE.read_text(encoding="utf-8")))

print("\nKeys the summary provides:")
for k in sorted(captured):
    print("  ", k)

print("\nTemplate uses these names that the summary does NOT provide:")
missing = sorted(used - set(captured) - {"loop", "range", "namespace", "dict"})
for k in missing or ["(none)"]:
    print("  ", k)