import sys
sys.path.insert(0, "app")
from data import *

DB = "data/audit.db"
run = "run_20261114_001637_3dff61"
print("runs:", list_runs(DB)[:3])
print("totals:", correctness_totals(DB, run))
print(correctness_by_category(DB, run))
print("failures:", len(failures(DB, run)))
print(latency_summary(DB, run))
print(metric_summary(DB, run))