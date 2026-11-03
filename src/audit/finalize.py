"""Block 4: merge, dedup (exact + embedding), optional trim, difficulty tags, IDs -> testset.jsonl"""
import argparse, json, re
from pathlib import Path

# ---- change these if your TestCase fields have other names ----
Q, CAT, SRC, ID, DIFF, ORIGIN = "question", "category", "source_ref", "id", "difficulty", "origin"
# ----------------------------------------------------------------

# config name -> name used in the data
ALIASES = {"paraphrased_informal": "paraphrased"}

def load(path):
    p = Path(path)
    if not p.exists():
        print(f"  (missing, skipped) {path}")
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  loaded {len(rows):3d}  {path}")
    return rows

def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()

def exact_dedup(rows):
    seen, out, dropped = set(), [], []
    for r in rows:
        k = norm(r[Q])
        if k in seen:
            dropped.append(r)
        else:
            seen.add(k)
            out.append(r)
    return out, dropped

def embedding_dedup(rows, threshold):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode([r[Q] for r in rows], normalize_embeddings=True)
    sims = emb @ emb.T
    drop, pairs = set(), []
    for i in range(len(rows)):
        if i in drop:
            continue
        for j in range(i + 1, len(rows)):
            if j not in drop and sims[i][j] >= threshold:
                drop.add(j)  # later file = lower priority, so drop it
                pairs.append((sims[i][j], rows[i][Q], rows[j][Q]))
    return [r for k, r in enumerate(rows) if k not in drop], pairs

def load_targets(config_path):
    import yaml
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    raw = data["testset"]["categories"]
    return {ALIASES.get(k, k): v for k, v in raw.items()}

def trim(rows, targets):
    """Cut GENERATED cases down to each category's target.
    Human and edge cases are never dropped. Generated cases are sampled evenly
    so every document stays represented."""
    by_cat = {}
    for idx, r in enumerate(rows):
        by_cat.setdefault(r.get(CAT), []).append(idx)
    drop = set()
    for cat, idxs in by_cat.items():
        if cat not in targets:
            continue
        gen = [i for i in idxs if rows[i].get(ORIGIN) == "generated"]
        keep_n = max(targets[cat] - (len(idxs) - len(gen)), 0)
        if len(gen) <= keep_n:
            continue
        step = len(gen) / keep_n if keep_n else 0
        chosen = {gen[int(j * step)] for j in range(keep_n)} if keep_n else set()
        drop |= set(gen) - chosen
    return [r for i, r in enumerate(rows) if i not in drop], len(drop)

def difficulty(r):
    q = r[Q]
    cat = str(r.get(CAT, "")).lower()
    if cat in ("adversarial", "ambiguous"):
        return "hard"
    n_src = len(r.get(SRC) or [])
    multi_intent = (" and " in q.lower() and q.count("?") >= 1 and len(q.split()) > 18) or q.count("?") > 1
    if n_src > 1 or multi_intent:
        return "hard"
    if re.search(r"\d", q) or "how much" in q.lower() or "how many" in q.lower() or "how long" in q.lower():
        return "medium"
    if cat in ("unanswerable", "off_topic"):
        return "easy"
    return "easy" if len(q.split()) <= 12 else "medium"

def assign_ids(rows):
    used, out, counters = set(), [], {}
    for r in rows:
        cat = str(r.get(CAT, "case")).lower()[:5]
        old = r.get(ID)
        if old and old not in used:
            used.add(old)
        else:
            counters[cat] = counters.get(cat, 0) + 1
            new = f"{cat}-{counters[cat]:03d}"
            while new in used:
                counters[cat] += 1
                new = f"{cat}-{counters[cat]:03d}"
            r[ID] = new
            used.add(new)
        out.append(r)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", default="data/demo/human_cases.jsonl")
    ap.add_argument("--edge", default="data/demo/draft_edge_cases.jsonl")
    ap.add_argument("--gen", nargs="+", default=["data/demo/draft_generated_3.jsonl"])
    ap.add_argument("--out", default="data/demo/testset.jsonl")
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--trim", action="store_true",
                    help="cut generated cases down to the targets in the config")
    ap.add_argument("--config", default="configs/audit.yaml")
    ap.add_argument("--dry", action="store_true", help="report only, do not write")
    a = ap.parse_args()

    print("Loading (priority order: human > edge > generated):")
    rows = load(a.human) + load(a.edge)
    for g in a.gen:
        rows += load(g)
    print(f"Total before dedup: {len(rows)}")

    rows, d1 = exact_dedup(rows)
    print(f"Exact dedup removed {len(d1)} -> {len(rows)}")

    rows, pairs = embedding_dedup(rows, a.threshold)
    print(f"Embedding dedup (>= {a.threshold}) removed {len(pairs)} -> {len(rows)}")
    for s, kept, gone in pairs:
        print(f"  {s:.2f}  KEEP: {kept}\n        DROP: {gone}")

    if a.trim:
        targets = load_targets(a.config)
        rows, n_cut = trim(rows, targets)
        print(f"Trim to config targets removed {n_cut} generated cases -> {len(rows)}")

    for r in rows:
        r[DIFF] = difficulty(r)
    rows = assign_ids(rows)

    from collections import Counter
    counts = Counter(str(r.get(CAT)) for r in rows)
    print("\nBy category:  ", dict(counts))
    print("By difficulty:", dict(Counter(r[DIFF] for r in rows)))
    if a.trim:
        short = {c: f"{counts.get(c, 0)}/{t}" for c, t in load_targets(a.config).items()
                 if counts.get(c, 0) < t}
        if short:
            print("Still below target (have/target):", short)

    if a.dry:
        print("\nDry run, nothing written.")
        return
    Path(a.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"\nWrote {len(rows)} cases to {a.out}")

if __name__ == "__main__":
    main()