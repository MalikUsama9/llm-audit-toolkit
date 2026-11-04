"""Mark ~30% of each category as heldout (kept aside while fixing the bot).

Usage:
    python -m audit.assign_split --dry
    python -m audit.assign_split
Same test set in -> same split out (fixed seed).
"""
import argparse
import enum
import os
import random
import typing
from collections import Counter, defaultdict
from pathlib import Path

import json
import yaml

from audit.models import TestCase


def allowed_values():
    """Return the values the `split` field accepts (Literal or Enum), or None if free text."""
    ann = TestCase.model_fields["split"].annotation
    out = []

    def walk(a):
        if isinstance(a, type) and issubclass(a, enum.Enum):
            out.extend(m.value for m in a)
        elif typing.get_origin(a) is typing.Literal:
            out.extend(typing.get_args(a))
        else:
            for x in typing.get_args(a):
                walk(x)

    walk(ann)
    return out or None


def pick_names(vals):
    if vals is None:
        return "dev", "heldout"
    hold = [v for v in vals if isinstance(v, str) and any(k in v.lower() for k in ("hold", "held", "test"))]
    dev = [v for v in vals if isinstance(v, str) and any(k in v.lower() for k in ("dev", "train", "tune", "work"))]
    if len(hold) == 1 and len(dev) == 1:
        return dev[0], hold[0]
    raise SystemExit(f"Can't tell which split value means heldout. Allowed values: {vals}. "
                     "Send me this line and I'll set the names.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="data/demo/testset.jsonl")
    ap.add_argument("--config", default="configs/audit.yaml")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    frac = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))["testset"]["holdout_fraction"]
    dev_name, hold_name = pick_names(allowed_values())
    rows = [json.loads(l) for l in Path(a.testset).read_text(encoding="utf-8").splitlines() if l.strip()]

    by_cat = defaultdict(list)
    for i, r in sorted(enumerate(rows), key=lambda t: t[1]["id"]):
        by_cat[r["category"]].append(i)

    rng = random.Random(a.seed)
    for cat, idxs in sorted(by_cat.items()):
        rng.shuffle(idxs)
        n_hold = int(len(idxs) * frac + 0.5)
        for k, i in enumerate(idxs):
            rows[i]["split"] = hold_name if k < n_hold else dev_name

    for r in rows:
        TestCase(**r)      # stop with an error if anything is invalid

    print(f"Split values used: dev='{dev_name}', heldout='{hold_name}', fraction={frac}")
    for cat in sorted(by_cat):
        c = Counter(rows[i]["split"] for i in by_cat[cat])
        print(f"  {cat:15s} {dict(c)}")
    print("Total:", dict(Counter(r["split"] for r in rows)))

    if a.dry:
        print("Dry run, nothing written.")
        return
    tmp = Path(a.testset).with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    os.replace(tmp, a.testset)
    print(f"Wrote {a.testset}")


if __name__ == "__main__":
    main()