import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from .summary import build_summary

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def build_report(db_path, run_id, out_path):
    summary = build_summary(db_path, run_id)
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    html = env.get_template("report.html.j2").render(**summary)
    HTML(string=html).write_pdf(out_path)
    return summary