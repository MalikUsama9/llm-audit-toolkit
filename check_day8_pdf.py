import sys
try:
    from pypdf import PdfReader
except ImportError:
    print("SKIP  pypdf not installed (run: pip install pypdf)")
    sys.exit()

def text(p):
    return " ".join(pg.extract_text() or "" for pg in PdfReader(p).pages).lower()

checks = [
    ("k of n shown", " of "),
    ("limitations", "limitation"),
    ("calibration", "calibration"),
    ("not tested", "not tested"),
    ("draft / human review", "draft"),
    ("what the bot does well", "well"),
    ("p95 latency", "p95"),
]

for path in ["out/_check.pdf", "examples/sample_report.pdf"]:
    try:
        t = text(path)
    except Exception as e:
        print(f"FAIL  cannot read {path}: {e}")
        continue
    for label, needle in checks:
        print(("PASS  " if needle in t else "FAIL  ") + f"{path}: {label}")