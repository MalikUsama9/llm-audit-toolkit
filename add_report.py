import ast, pathlib, re

skip = {".venv", "venv", "env", "node_modules", ".git", "__pycache__", "site-packages"}
files = [p for p in pathlib.Path(".").rglob("*.py")
         if not any(s in skip for s in p.parts) and p.name != "add_report.py"]

cli = next((p for p in files if "typer.Typer(" in p.read_text(encoding="utf-8")
            and ".command(" in p.read_text(encoding="utf-8")), None)
pdf = next((p for p in files if p.name == "pdf.py"), None)
if not cli or not pdf:
    raise SystemExit(f"Could not find files. CLI={cli} pdf.py={pdf}")

text = cli.read_text(encoding="utf-8")
if re.search(r"def report\(", text):
    raise SystemExit(f"'report' command already exists in {cli}")

app_var = re.search(r"(\w+)\s*=\s*typer\.Typer\(", text).group(1)

tree = ast.parse(pdf.read_text(encoding="utf-8"))
funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
fn = next((f for f in funcs if "report" in f.name.lower()), None) \
  or next((f for f in funcs if re.match(r"(build|generate|make|create)", f.name)), None) \
  or funcs[0]
arg = next((a.arg for a in fn.args.args
            if a.arg in ("out_path", "output_path", "out", "output", "path", "filename", "outfile")), None)
call = f"{fn.name}({arg}=out)" if arg else f"{fn.name}(out)"

parts = list(pdf.with_suffix("").parts)
if parts[0] == "src":
    parts = parts[1:]
module = ".".join(parts)

snippet = f'''

@{app_var}.command()
def report(out: str = "examples/sample_report.pdf"):
    """Generate the PDF audit report."""
    from {module} import {fn.name}
    {call}
    typer.echo(f"Report saved to {{out}}")
'''

m = re.search(r'\nif __name__ == ["\']__main__["\']:', text)
text = text[:m.start()] + snippet + text[m.start():] if m else text.rstrip() + "\n" + snippet
cli.write_text(text, encoding="utf-8")
print(f"Added 'report' to {cli} using {module}.{fn.name} ({call})")
