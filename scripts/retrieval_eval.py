"""Step 5.6: retrieval evaluator for glass-box runs. No LLM calls.
Usage: python scripts\retrieval_eval.py RUN_ID [--k 4] [--verbose] [--save]
"""
import sqlite3, json, re, csv, argparse, os
from statistics import mean

ap = argparse.ArgumentParser()
ap.add_argument("run_id")
ap.add_argument("--k", type=int, default=4)
ap.add_argument("--verbose", action="store_true", help="show missed cases")
ap.add_argument("--save", action="store_true", help="write retrieval_* rows into scores table")
args = ap.parse_args()

con = sqlite3.connect("data/audit.db")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def first_line(text):
    return (text or "").strip().split("\n")[0]


def heading_slug(text):
    fl = first_line(text)
    if " > " in fl:
        fl = fl.rsplit(" > ", 1)[1]
    elif " - " in fl:
        fl = fl.split(" - ", 1)[1]
    return slug(fl)


def parse_refs(raw):
    try:
        refs = json.loads(raw) if raw else []
    except Exception:
        refs = [raw] if raw else []
    if isinstance(refs, str):
        refs = [refs]
    out = []
    for r in refs:
        anchor = slug(r.split("#", 1)[1]) if "#" in r else ""
        if anchor and anchor not in [a for _, a in out]:
            out.append((r, anchor))
    return out  # list of (original ref, anchor slug)


def chunk_matches(chunk, anchor):
    """A chunk matches a gold source if its heading equals the anchor (or contains it)."""
    return heading_slug(chunk) == anchor or anchor in slug(first_line(chunk))


def parse_contexts(raw):
    try:
        items = json.loads(raw) if raw else []
    except Exception:
        return []
    return [i if isinstance(i, str) else (i.get("text") or str(i)) for i in items]


rows = con.execute("""
    SELECT c.id, c.question, c.source_ref, r.contexts, r.error
    FROM results r JOIN cases c ON c.id = r.case_id
    WHERE r.run_id = ? ORDER BY c.id""", (args.run_id,)).fetchall()
if not rows:
    raise SystemExit(f"No results for run {args.run_id}")

correct = {cid: v for cid, v in con.execute(
    "SELECT case_id, value FROM scores WHERE run_id=? AND metric='correctness'", (args.run_id,))}

skipped = {"no gold source": 0, "no contexts (black-box or error)": 0}
per_case = []  # one dict per evaluated case
for cid, q, ref_raw, ctx_raw, err in rows:
    refs = parse_refs(ref_raw)
    chunks = parse_contexts(ctx_raw)
    if not refs:
        skipped["no gold source"] += 1
        continue
    if not chunks or err:
        skipped["no contexts (black-box or error)"] += 1
        continue
    rec = {"case_id": cid, "question": q, "refs": refs, "chunks": chunks}
    for k in range(1, args.k + 1):
        top = chunks[:k]
        found = [a for _, a in refs if any(chunk_matches(ch, a) for ch in top)]
        good_chunks = sum(1 for ch in top if any(chunk_matches(ch, a) for _, a in refs))
        rec[f"hit@{k}"] = 1.0 if found else 0.0
        rec[f"recall@{k}"] = len(found) / len(refs)
        rec[f"prec@{k}"] = good_chunks / len(top)
    rr = 0.0
    for rank, ch in enumerate(chunks[:args.k], 1):
        if any(chunk_matches(ch, a) for _, a in refs):
            rr = 1.0 / rank
            break
    rec["mrr"] = rr
    per_case.append(rec)

n = len(per_case)
print(f"Run: {args.run_id}")
print(f"Cases in run: {len(rows)} | evaluated: {n} | skipped: {skipped}")
if n == 0:
    raise SystemExit("Nothing to evaluate. Use a glass-box run whose cases have source_ref.")
if n < 15:
    print("WARNING: very few evaluated cases, so these numbers are rough.")

print("\nRetrieval quality by k (uses the first k stored chunks)")
print(f"  {'k':>2} {'Hit@k':>7} {'Recall@k':>9} {'Prec@k':>7}")
for k in range(1, args.k + 1):
    print(f"  {k:>2} {mean(r[f'hit@{k}'] for r in per_case):>7.1%} "
          f"{mean(r[f'recall@{k}'] for r in per_case):>9.1%} "
          f"{mean(r[f'prec@{k}'] for r in per_case):>7.1%}")
print(f"\n  MRR@{args.k} = {mean(r['mrr'] for r in per_case):.3f}")

# retrieval vs answer correctness (is the failure retrieval or generation?)
hit_key = f"hit@{args.k}"
if correct:
    cells = {("hit", "right"): 0, ("hit", "wrong"): 0, ("miss", "right"): 0, ("miss", "wrong"): 0}
    for r in per_case:
        if r["case_id"] not in correct:
            continue
        a = "hit" if r[hit_key] == 1.0 else "miss"
        b = "right" if correct[r["case_id"]] >= 1.0 else "wrong"
        cells[(a, b)] += 1
    print("\nRetrieval vs answer correctness (cases that have a correctness score)")
    print(f"  retrieved correct chunk, answer right : {cells[('hit','right')]}")
    print(f"  retrieved correct chunk, answer wrong : {cells[('hit','wrong')]}  <- generation problem")
    print(f"  missed correct chunk,    answer right : {cells[('miss','right')]}  <- lucky or answered from elsewhere")
    print(f"  missed correct chunk,    answer wrong : {cells[('miss','wrong')]}  <- retrieval problem")

misses = [r for r in per_case if r[hit_key] == 0.0]
print(f"\nMissed cases at k={args.k}: {len(misses)} of {n}")
if args.verbose:
    for r in misses[:10]:
        print(f"\n  {r['case_id']}: {r['question'][:90]}")
        print("    wanted   :", [ref for ref, _ in r["refs"]])
        for i, ch in enumerate(r["chunks"][:args.k], 1):
            print(f"    got #{i}   :", first_line(ch)[:80])

os.makedirs("data/demo", exist_ok=True)
out = f"data/demo/retrieval_{args.run_id}.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["case_id", "hit", "recall", "precision", "mrr", "wanted", "retrieved_headers"])
    for r in per_case:
        w.writerow([r["case_id"], r[hit_key], r[f"recall@{args.k}"], r[f"prec@{args.k}"], r["mrr"],
                    " | ".join(ref for ref, _ in r["refs"]),
                    " | ".join(first_line(ch)[:60] for ch in r["chunks"][:args.k])])
print("Saved", out)

if args.save:
    for metric, key in (("retrieval_hit", hit_key), ("retrieval_recall", f"recall@{args.k}"), ("retrieval_mrr", "mrr")):
        con.execute("DELETE FROM scores WHERE run_id=? AND metric=?", (args.run_id, metric))
        for r in per_case:
            con.execute("INSERT INTO scores (run_id, case_id, metric, value, reasoning, judge_model) VALUES (?,?,?,?,?,?)",
                        (args.run_id, r["case_id"], metric, r[key], "deterministic heading match", "none"))
    con.commit()
    print("Saved retrieval_hit / retrieval_recall / retrieval_mrr into the scores table")