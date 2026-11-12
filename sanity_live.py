"""Live sanity checks for the judge (costs a few cents).

    python sanity_live.py                       # known answers + 10 real cases
    python sanity_live.py --n 10 --run run_20261110_005907_b09fcd
    python sanity_live.py --faithfulness        # also compute the hallucination flag
"""
import argparse
import logging
import random
from collections import Counter
from types import SimpleNamespace

from audit.config import load_config
from audit.judge import judge_with_checks, load_rubric
from audit.llm.client import LLMClient
from audit.store import Store

# These cases appear inside the judge prompts as examples, so never grade them.
FEW_SHOT_IDS = {"add-001", "add-003", "add-006", "synthetic-S5", "synthetic-S6", "unans-01"}
SKIP = {"empty", "error"}

REFUSAL = ("I'm sorry, I don't have that information. "
           "Please contact support at support@tidewellhome.example for assistance!")
FABRICATED = "Sure! Use code SAVE50 at checkout for 50% off your entire order."


def main() -> None:
    # Shows judge_parse_error / judge_failure lines so you can see WHY a call failed.
    logging.basicConfig(level=logging.WARNING)

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run_20261110_005907_b09fcd")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--config", default="configs/audit.yaml")
    ap.add_argument("--faithfulness", action="store_true",
                    help="also run the faithfulness rubric (the only one that sets the "
                         "hallucination flag) on answers that are not refusals")
    args = ap.parse_args()
    random.seed(0)

    cfg = load_config(args.config)
    jcfg = cfg.judge or SimpleNamespace(model=cfg.models.judge, temperature=0.0,
                                        max_tokens=800, rubric_dir="configs/rubrics",
                                        budget_usd=3.0)
    client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=jcfg.budget_usd)
    rubrics = {n: load_rubric(n, jcfg.rubric_dir)
               for n in ("correctness", "refusal", "faithfulness")}
    store = Store(cfg.paths.database)
    cases = {c.id: c for c in store.get_cases() if c.id not in FEW_SHOT_IDS}
    start_id = client.db.execute("SELECT COALESCE(MAX(id),0) FROM call_log").fetchone()[0]

    def ask(rubric_name, case, answer):
        return judge_with_checks(client, jcfg, rubrics[rubric_name], case.id,
                                 case.question, case.reference_answer or "",
                                 case.source_text or "", answer)

    # ------------------------------------------------ Part 2: known answers
    print("=" * 60, "\nPART 2: known correct / wrong / refusal\n", "=" * 60, sep="")
    answerable = [c for c in cases.values() if c.expected_behavior.value == "answer"
                  and c.reference_answer and c.source_text]
    unanswerable = [c for c in cases.values() if c.expected_behavior.value == "refuse"]
    a3 = random.sample(answerable, 3)
    u2 = random.sample(unanswerable, 2)

    tests = []  # (label, rubric, case, answer, acceptable verdicts)
    for i, c in enumerate(a3):
        other = a3[(i + 1) % 3]          # another case's answer = known wrong
        tests += [
            (f"{c.id} correct", "correctness", c, c.reference_answer, {"correct"}),
            (f"{c.id} wrong", "correctness", c, other.reference_answer, {"incorrect"}),
            (f"{c.id} refusal", "correctness", c, REFUSAL, {"incorrect"}),
        ]
    tests.append((f"{a3[0].id} over-refusal", "refusal", a3[0], REFUSAL, {"wrongful_refusal"}))
    for c in u2:
        tests += [
            (f"{c.id} good refusal", "refusal", c, REFUSAL, {"appropriate_refusal"}),
            (f"{c.id} fabricated", "refusal", c, FABRICATED, {"fabricated"}),
        ]

    passed, part2_failures = 0, 0
    for label, rubric, case, answer, ok in tests:
        _, res = ask(rubric, case, answer)
        if res is None:
            part2_failures += 1
        got = res.output.verdict if res else "JUDGE_FAILURE"
        good = got in ok
        passed += good
        print(f"{'PASS' if good else 'FAIL'}  {label:28} expected {sorted(ok)}  got {got}")
    print(f"\n{passed}/{len(tests)} matched expectations   "
          f"(judge failures in part 2: {part2_failures})")

    # ------------------------------------------------ Part 3: real cases
    print("\n" + "=" * 60, f"\nPART 3: {args.n} real cases from {args.run}\n", "=" * 60, sep="")
    results = {r.case_id: r for r in store.get_results(args.run)}
    checks = store.get_checks(args.run)
    plan = [("answer", "ok", 3), ("answer", "refusal", 3), ("refuse", "refusal", 2),
            ("refuse", "ok", 1), ("answer", "partial", 1)]
    picked = []
    for expected, status, n in plan:
        pool = [cid for cid, c in cases.items() if cid in results and cid in checks
                and c.expected_behavior.value == expected and checks[cid]["status"] == status]
        random.shuffle(pool)
        picked += pool[:n]
    picked = picked[: args.n]

    verdicts = Counter()
    failures, skipped = 0, 0
    hallucinated, faith_runs = 0, 0
    for cid in picked:
        case, r = cases[cid], results[cid]
        status = checks[cid]["status"]
        rubric = "refusal" if (status == "refusal" or case.expected_behavior.value != "answer") \
            else "correctness"
        check, res = ask(rubric, case, r.answer or "")

        if res is not None:
            got = res.output.verdict
        elif check.status in SKIP:
            got = f"SKIPPED({check.status})"      # deliberately not judged
            skipped += 1
        else:
            got = "JUDGE_FAILURE"                 # judge ran but output was unusable
            failures += 1
        verdicts[(rubric, got)] += 1

        print(f"\n[{cid}] expected={case.expected_behavior.value} check={status} "
              f"rubric={rubric}\n  Q: {case.question[:90]}\n  A: {(r.answer or '')[:110]!r}\n"
              f"  verdict={got}"
              + (f"  claims={len(res.output.claims)}" if res else "")
              + (f"\n  why: {res.output.reasoning[:140]}" if res else ""))

        # The hallucination flag only means something under the faithfulness rubric.
        # (Refusal and correctness claims are not factual claims about the source.)
        if args.faithfulness and status in ("ok", "partial") and check.status not in SKIP:
            _, fres = ask("faithfulness", case, r.answer or "")
            if fres is not None:
                faith_runs += 1
                hallucinated += fres.hallucinated
                print(f"  faithfulness: hallucinated={fres.hallucinated} "
                      f"claims={[c.status for c in fres.output.claims]}")
            else:
                failures += 1
                print("  faithfulness: JUDGE_FAILURE")

    # ------------------------------------------------ cost
    n_calls, n_cached, tin, tout, cost = client.db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cached),0), COALESCE(SUM(input_tokens),0), "
        "COALESCE(SUM(output_tokens),0), COALESCE(SUM(cost_usd),0) "
        "FROM call_log WHERE id>?", (start_id,)).fetchone()
    # Real (uncached, successful) calls across ALL runs, for a trustworthy average.
    life_calls, life_cost, life_in, life_out = client.db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_usd),0), COALESCE(SUM(input_tokens),0), "
        "COALESCE(SUM(output_tokens),0) FROM call_log "
        "WHERE cached=0 AND error IS NULL AND model=?", (jcfg.model,)).fetchone()

    print("\n" + "=" * 60, "\nSUMMARY\n", "=" * 60, sep="")
    for (rubric, v), n in sorted(verdicts.items()):
        print(f"  {rubric:12} {v:24} {n}")
    print(f"Judge failures: {failures}   deliberately skipped: {skipped}   cases: {len(picked)}")
    if args.faithfulness:
        print(f"Hallucination flags (faithfulness only): {hallucinated}/{faith_runs}")
    else:
        print("Hallucination flag: not computed (run with --faithfulness)")
    print(f"LLM calls this run: {n_calls} ({n_cached} from cache)   tokens in/out: {tin}/{tout}")
    print(f"Cost this run: ${cost:.4f}   (judge cap: ${jcfg.budget_usd:.2f})")

    print(f"\nAll real judge calls so far ({jcfg.model}): {life_calls} calls, "
          f"tokens in/out {life_in}/{life_out}, logged cost ${life_cost:.4f}")
    if life_calls and life_cost == 0 and (life_in + life_out) > 0:
        print("WARNING: tokens were used but the logged cost is $0. Either the model is "
              "free, or LiteLLM has no price for it. Price it by hand:")
        print("  cost = tokens_in/1e6 * input_price + tokens_out/1e6 * output_price")
        avg_in, avg_out = life_in / life_calls, life_out / life_calls
        print(f"  average per call: {avg_in:.0f} in / {avg_out:.0f} out tokens")
        print(f"  full run (118 cases x 3 rubrics): about {avg_in * 354:.0f} in / "
              f"{avg_out * 354:.0f} out tokens")
    elif life_calls:
        per_call = life_cost / life_calls
        print(f"Average cost per call: ${per_call:.5f}   "
              f"full run (118 cases x 3 rubrics): about ${per_call * 118 * 3:.2f}")


if __name__ == "__main__":
    main()