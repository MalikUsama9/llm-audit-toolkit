import sys
from audit.config import load_config
from audit.store import Store
from audit.reporting.stats import wilson, paired_flip_test, paired_bootstrap_delta

base, after = sys.argv[1], sys.argv[2]
store = Store(load_config("configs/audit.yaml").paths.database)
cases = {c.id: c for c in store.get_cases()}

def vals(run):
    return {s.case_id: s.value for s in store.get_scores(run)
            if s.metric in ("correctness", "refusal")}

b, a = vals(base), vals(after)
common = sorted(set(b) & set(a))

def split_of(i):
    c = cases.get(i)
    return c.split.value if c is not None and c.split is not None else "none"

def report(name, ids):
    n = len(ids)
    if n == 0:
        return
    kb = sum(b[i] >= 1.0 for i in ids)
    ka = sum(a[i] >= 1.0 for i in ids)
    (lb, hb), (la, ha) = wilson(kb, n), wilson(ka, n)
    fixed = [i for i in ids if b[i] < 1.0 and a[i] >= 1.0]
    broken = [i for i in ids if a[i] < 1.0 and b[i] >= 1.0]
    p = paired_flip_test(len(fixed), len(broken))
    lo, hi = paired_bootstrap_delta([b[i] for i in ids], [a[i] for i in ids])
    print(f"\n=== {name} (n={n}) ===")
    print(f"before: {kb} of {n} fully correct  ({kb/n:.1%}, 95% CI {lb:.1%} to {hb:.1%})")
    print(f"after:  {ka} of {n} fully correct  ({ka/n:.1%}, 95% CI {la:.1%} to {ha:.1%})")
    print(f"fixed: {len(fixed)}   newly broken: {len(broken)}   flip-test p = {p:.3f}")
    print(f"mean score change: {sum(a[i]-b[i] for i in ids)/n:+.3f}  (bootstrap 95% CI {lo:+.3f} to {hi:+.3f})")
    print("fixed ids:        ", ", ".join(fixed) or "-")
    print("newly broken ids: ", ", ".join(broken) or "-")

print(f"baseline {base}  vs  after {after}; {len(common)} cases scored in both")
report("DEV", [i for i in common if split_of(i) == "dev"])
report("HELD-OUT", [i for i in common if split_of(i) == "heldout"])
report("ALL", common)