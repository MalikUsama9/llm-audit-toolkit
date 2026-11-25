# try_judge.py  -> run with: python try_judge.py
import logging
import sqlite3

from audit.judge import judge_case, load_rubric, log_run_settings

logging.basicConfig(level=logging.INFO)

# ---- ADAPT: how your project loads its config and client -------------------
# Check src/audit/config.py for the real name of the function that loads
# the YAML file. "load_config" is a guess.
from audit.config import load_config
from audit.llm.client import LLMClient

cfg = load_config("configs/audit.yaml")
client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)
# ----------------------------------------------------------------------------

DB_PATH = "data/audit.db"
CASE_ID = "human-01"                      # a dev case NOT in few_shot_ids.txt
RUN_ID = "run_20261110_005907_b09fcd"     # the run named in your day4 notes

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
row = con.execute(
    """
    SELECT c.id, c.question, c.reference_answer, c.source_text, r.answer
    FROM cases c JOIN results r ON r.case_id = c.id
    WHERE c.id = ? AND r.run_id = ?
    """,
    (CASE_ID, RUN_ID),
).fetchone()
assert row, f"case {CASE_ID} not found for run {RUN_ID}"

rubric = load_rubric("faithfulness", cfg.judge.rubric_dir)
log_run_settings(cfg.judge, {"faithfulness": rubric})

result = judge_case(
    client, cfg.judge, rubric, row["id"],
    row["question"], row["reference_answer"], row["source_text"], row["answer"],
)

if result is None:
    print("judge failed (see judge_failure in the log above)")
else:
    print("verdict      :", result.output.verdict)
    print("hallucinated :", result.hallucinated)
    for c in result.output.claims:
        print(f" - [{c.status}] {c.claim}")