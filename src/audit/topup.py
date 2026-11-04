"""Top up short categories from spare drafts, then review them with audit.review.

Usage:
    python -m audit.topup --dry     (preview)
    python -m audit.topup           (write)
"""
import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

import yaml

from audit.finalize import difficulty

ALIASES = {"paraphrased_informal": "paraphrased"}


def load(p):
    p = Path(p)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="data/demo/testset.jsonl")
    ap.add_argument("--drafts", nargs="+",
                    default=["data/demo/draft_generated_3.jsonl", "data/demo/draft_gap_cases.jsonl"])
    ap.add_argument("--rejected", default="data/demo/rejected_cases.jsonl")
    ap.add_argument("--config", default="configs/audit.yaml")
    ap.add_argument("--extra-multi-hop", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    rows = load(a.testset)
    rejected = load(a.rejected)
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    targets = {ALIASES.get(k, k): v for k, v in cfg["testset"]["categories"].items()}
    counts = Counter(r["category"] for r in rows)

    blocked = {norm(r["question"]) for r in rows + rejected}
    spares, seen = [], set()
    for p in a.drafts:
        for d in load(p):
            k = norm(d["question"])
            if k not in blocked and k not in seen:
                seen.add(k)
                spares.append(d)

    # drop spares too similar to anything already in the set or rejected
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    known = [r["question"] for r in rows + rejected]
    ke = model.encode(known, normalize_embeddings=True)
    se = model.encode([s["question"] for s in spares], normalize_embeddings=True)
    sims = se @ ke.T
    spares = [s for i, s in enumerate(spares) if sims[i].max() < a.threshold]

    used_ids = {r["id"] for r in rows}
    added, n = [], 0
    for cat, target in targets.items():
        need = target - counts.get(cat, 0)
        if need <= 0:
            continue
        if cat == "multi_hop":
            need += a.extra_multi_hop
        pool = [s for s in spares if s["category"] == cat]
        if len(pool) > need:
            step = len(pool) / need
            pool = [pool[int(j * step)] for j in range(need)]
        for s in pool:
            n += 1
            while f"add-{n:03d}" in used_ids:
                n += 1
            s["id"] = f"add-{n:03d}"
            used_ids.add(s["id"])
            s["reviewed"] = False
            s["difficulty"] = difficulty(s)
            added.append(s)
        print(f"{cat}: need {target - counts.get(cat, 0)}, adding {len(pool)}")

    if a.dry or not added:
        print("Dry run, nothing written." if a.dry else "Nothing to add.")
        return
    allrows = rows + added
    tmp = Path(a.testset).with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in allrows) + "\n",
                   encoding="utf-8")
    os.replace(tmp, a.testset)
    print(f"Added {len(added)} cases to review. Total now {len(allrows)}.")


if __name__ == "__main__":
    main()