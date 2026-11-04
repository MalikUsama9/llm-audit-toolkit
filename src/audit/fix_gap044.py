import json
from pathlib import Path

from audit.models import TestCase

TESTSET = Path("data/demo/testset.jsonl")
REJECTED = Path("data/demo/rejected_cases.jsonl")
HUMAN = Path("data/demo/human_cases.jsonl")

rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
bad = [r for r in rows if r["id"] == "gap-044"]
if not bad:
    raise SystemExit("gap-044 not found (already fixed?)")
rows = [r for r in rows if r["id"] != "gap-044"]
with REJECTED.open("a", encoding="utf-8") as f:
    f.write(json.dumps(bad[0], ensure_ascii=False) + "\n")

origin = json.loads(HUMAN.read_text(encoding="utf-8").splitlines()[0]).get("origin", "human")

new = {
    "id": "hand-001",
    "category": "multi_hop",
    "question": "I live in the contiguous US and only want to buy the Glass Storage Containers. Will Standard shipping be free?",
    "reference_answer": "No, not unless you are a Tidewell Club member. The Glass Storage Containers cost $42, which is below the $49 minimum for free Standard shipping to the contiguous US. Tidewell Club members get free Standard shipping on all US orders with no minimum.",
    "difficulty": "hard",
    "expected_behavior": "answer",
    "source_ref": ["14_product_catalog.md#kitchen", "02_shipping_policy.md#free-shipping"],
    "source_text": (
        "Product Catalog and Price List > Kitchen\n"
        "| Product | Details | Price |\n|---|---|---|\n"
        "| Tidewell Enameled Dutch Oven | 5.5 qt, Sea Glass, Oat or Charcoal | $119 |\n"
        "| Pinebrook Knife Set | 6 pieces with bamboo block | $89 |\n"
        "| Everyday Stoneware Dinner Set | 16 pieces, serves 4 | $64 |\n"
        "| Glass Storage Containers | 10 pieces (5 containers, 5 lids) | $42 |\n"
        "\n---\n\n"
        "Shipping Policy > Free shipping\n"
        "Standard shipping is free on orders of $49 or more to the contiguous US. "
        "The $49 is measured after discounts and promo codes are applied and before tax. "
        "Free shipping applies to Standard only. If you choose Expedited or Overnight on a "
        "qualifying order, you pay the full price of that option. Tidewell Club members get "
        "free Standard shipping on all US orders with no minimum."
    ),
    "origin": origin,
    "reviewed": True,
}
TestCase(**new)          # stops with an error if any field is invalid
rows.append(new)
TESTSET.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(f"Removed gap-044, added hand-001. Total now {len(rows)}.")