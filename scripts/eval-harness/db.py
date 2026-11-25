import sqlite3, threading, hashlib, json

DB_PATH = "evals.db"
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, started_at TEXT, judge_model TEXT, prompt_version TEXT);
CREATE TABLE IF NOT EXISTS results(
  cache_key TEXT PRIMARY KEY,
  run_id TEXT, case_id TEXT, check_name TEXT,
  score REAL, passed INTEGER,
  reasoning TEXT, evidence TEXT, evidence_verified INTEGER,
  tokens_in INTEGER, tokens_out INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_results_case ON results(case_id);
"""

def get_conn():
    """One connection per thread."""
    if not hasattr(_local, "conn"):
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn = c
    return _local.conn

def cache_key(case, check_name, judge_model, prompt_version, rubric):
    payload = json.dumps(
        [case["id"], case["input"], case["output"], check_name,
         judge_model, prompt_version, rubric], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def get_cached(key):
    return get_conn().execute(
        "SELECT * FROM results WHERE cache_key=?", (key,)).fetchone()

def save_result(key, run_id, case_id, check_name, score, passed,
                reasoning, evidence, verified, tin=0, tout=0):
    c = get_conn()
    c.execute(
        """INSERT OR REPLACE INTO results
           (cache_key, run_id, case_id, check_name, score, passed, reasoning,
            evidence, evidence_verified, tokens_in, tokens_out)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (key, run_id, case_id, check_name, score, int(passed), reasoning,
         json.dumps(evidence), int(verified), tin, tout))
    c.commit()