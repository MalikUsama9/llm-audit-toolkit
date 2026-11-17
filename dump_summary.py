import json, sys
from jinja2 import Template
from audit.reporting.pdf import build_report

captured = {}
_orig = Template.render

def _spy(self, *a, **k):
    captured.update(dict(*a, **k))
    return _orig(self, *a, **k)

Template.render = _spy
try:
    build_report(sys.argv[1], sys.argv[2], "x.pdf")
except Exception as e:
    print("expected error:", e)

def trim(v):
    if isinstance(v, dict):
        return {k: trim(x) for k, x in list(v.items())[:15]}
    if isinstance(v, list):
        return [trim(x) for x in v[:2]] + ([f"... {len(v)} items"] if len(v) > 2 else [])
    if isinstance(v, str) and len(v) > 80:
        return v[:80] + "..."
    return v

keys = ["run", "overall", "usage", "latency", "counts", "error_cases", "splits", "categories"]
print(json.dumps({k: trim(captured.get(k)) for k in keys}, indent=1, default=str))