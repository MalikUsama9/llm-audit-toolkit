# estimate_cost.py
# python estimate_cost.py --in-price 0.15 --out-price 0.60
import argparse

p = argparse.ArgumentParser()
p.add_argument("--in-price", type=float, required=True, help="USD per 1M input tokens")
p.add_argument("--out-price", type=float, required=True, help="USD per 1M output tokens")
p.add_argument("--cases", type=int, default=118)
p.add_argument("--in-tokens-per-case", type=int, default=1200)   # roadmap: ~145k/120
p.add_argument("--out-tokens-per-case", type=int, default=250)   # roadmap: ~30k/120
p.add_argument("--passes", type=int, default=6, help="Day 4 first run + ~5 tuning passes")
a = p.parse_args()

tin = a.cases * a.in_tokens_per_case
tout = a.cases * a.out_tokens_per_case
one = tin / 1e6 * a.in_price + tout / 1e6 * a.out_price
print(f"One full judge pass: {tin:,} in / {tout:,} out tokens = ${one:.3f}")
print(f"{a.passes} passes: ${one * a.passes:.2f}")
print(f"Suggested cap (2x safety): ${one * a.passes * 2:.2f}")
