import json, uuid, argparse, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import db, judge
from checks import DET_CHECKS

STATS = {"hits": 0, "calls": 0, "errors": 0}
LOCK = threading.Lock()

def bump(k):
    with LOCK:
        STATS[k] += 1

def evaluate(case, run_id):
    # 1. Deterministic checks (free)
    for name, fn in DET_CHECKS.items():
        ok, detail = fn(case, case["output"])
        key = db.cache_key(case, f"det:{name}", "none", "none", "none")
        db.save_result(key, run_id, case["id"], f"det:{name}",
                       float(ok), ok, detail, [], True)

    # 2. LLM judge (cached)
    key = db.cache_key(case, "judge", judge.JUDGE_MODEL,
                       judge.PROMPT_VERSION, judge.RUBRIC)
    if db.get_cached(key):
        bump("hits")
        return
    data, tin, tout = judge.call_judge(case)
    quotes = data.get("evidence", [])
    verified = judge.verify_evidence(quotes, case["output"])
    score = int(data["score"])
    db.save_result(key, run_id, case["id"], "judge:quality", score / 5,
                   score >= 4, data["reasoning"], quotes, verified, tin, tout)
    bump("calls")

def summary():
    c = db.get_conn()
    print("\n=== Pass rate by check ===")
    for r in c.execute("""SELECT check_name, COUNT(*) n, ROUND(AVG(passed)*100,1) pr
                          FROM results GROUP BY check_name"""):
        print(f"{r['check_name']:<22} n={r['n']:<4} pass={r['pr']}%")
    j = c.execute("""SELECT ROUND(AVG(score)*5,2) m, COUNT(*) n,
                     SUM(evidence_verified=0) bad, SUM(tokens_in) ti,
                     SUM(tokens_out) tout
                     FROM results WHERE check_name='judge:quality'""").fetchone()
    print(f"\nJudge mean score (1-5): {j['m']}  over {j['n']} cases")
    print(f"Unverified-evidence rows: {j['bad']}")
    print(f"Total judge tokens stored: in={j['ti']} out={j['tout']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="cases.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    cases = [json.loads(l) for l in open(a.cases) if l.strip()]
    if a.limit:
        cases = cases[:a.limit]

    run_id = uuid.uuid4().hex[:8]
    db.get_conn().execute(
        "INSERT INTO runs VALUES (?,?,?,?)",
        (run_id, datetime.now().isoformat(), judge.JUDGE_MODEL, judge.PROMPT_VERSION))
    db.get_conn().commit()

    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(evaluate, c, run_id): c["id"] for c in cases}
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                bump("errors")
                print(f"ERROR {futs[f]}: {e}")

    print(f"\nrun_id={run_id} cases={len(cases)} "
          f"judge_calls={STATS['calls']} cache_hits={STATS['hits']} errors={STATS['errors']}")
    summary()