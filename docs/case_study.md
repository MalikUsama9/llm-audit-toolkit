# Auditing and improving a RAG support bot: a before/after case study

*Draft. This is my own bot, built on a fictional online store, not a client system. [CONFIRM STORE NAME: the roadmap says BrewNest, but the runs and docs say Tidewell Home.]*

## The finding

Two changes to my bot (a one-line prompt rule for ambiguous questions, and retrieving 8 chunks instead of 4) raised the share of fully correct answers from 74.6% to 80.5% on 118 test cases. On the held-out split the rate went from 70.3% to 78.4%, which is 3 more cases out of 37. These gains are not statistically distinguishable from noise. The paired correctness comparison is +4.0% with a 95% interval of −4.0% to +13.3% (exact flip test p=0.549). The clearest improvement is on ambiguous questions (4/8 to 8/8, with 4 fixed and 0 broken), but that is only 8 cases. The change also broke 4 previously correct answers, listed below.

## 1. Setup

- **Bot:** a retrieval-augmented support assistant for a fictional online shop (Tidewell Home). BM25 retriever, max chunk size 1,200 characters, temperature 0.0, max_tokens 1500.
- **Generator:** [VERIFY: config lists model gemini/gemini-3.5-flash-lite but models.generator gemini/gemini-3.1-flash-lite].
- **Judge:** groq/openai/gpt-oss-120b, same rubric and settings for both runs.
- **Test set:** 118 cases, split into 81 development and 37 held-out. The split was fixed before any change. Categories: adversarial 10, ambiguous 8, direct_factual 25, multi_hop 10, multi_intent 5, numeric_policy 15, off_topic 10, paraphrased 20, unanswerable 15.
- **Scoring:** 75 cases are scored on correctness and 43 on refusal/clarification behaviour. A case counts as passed only if fully correct (partial answers do not count as passed).
- **Judge reliability:** the judge agreed with my human labels on 22 of 24 cases (91.7%, 95% CI 74.2% to 97.7%, kappa 0.86). Only 24 cases were human-labelled. Both disagreements were cases I labelled correct that the judge scored partially correct, so the judge leans strict.
- **Baseline run:** run_20261117_110249_a29a22 (all 118 cases judged, 0 errors).

## 2. Baseline findings

| | Passed | Partial | Failed | Pass rate (95% CI) |
|---|---|---|---|---|
| All (n=118) | 88 | 10 | 20 | 74.6% (66.0% to 81.6%) |
| Dev (n=81) | 62 | 7 | 12 | 76.5% (66.2% to 84.4%) |
| Held-out (n=37) | 26 | 3 | 8 | 70.3% (54.2% to 82.5%) |

Weak spots in the baseline:

- **Ambiguous questions:** 4/8. The bot answered or refused instead of asking which product or order the customer meant (for example "can i cancel it").
- **False "I don't have that information":** on several questions whose answer is in the documents (for example add-001, gap-028, human-01), the bot declined to answer.
- **Unsupported extras:** several answers were correct but added claims not in the source, which the judge scores as partial.
- **Weakest categories:** multi_hop 5/10 and paraphrased 13/20.

Cases that guided the fixes (development set only). Clarifying-question rule: human-17, human-16, amb-07. top_k 4 to 8: add-001, gen-105, gap-028, human-01, human-03. Held-out discipline: held-out failures were visible in the audit compare --details output, so I cannot rule out indirect influence.

## 3. What changed

Two changes, made together:

1. **Prompt (v1 to day9):** added one rule: "If the question does not say which product, policy or situation it is about, ask one short clarifying question instead of answering."
2. **Retrieval:** top_k 4 to 8.

The test set, judge, rubric, model and temperature were unchanged. Because both changes were made at once, I cannot say how much of any effect comes from each.

After run: run_20261118_021953_c80e1b (all 118 judged, 0 errors).

## 4. Results

| | Before | After |
|---|---|---|
| All (n=118) | 88 passed (74.6%) | 95 passed (80.5%, CI 72.4% to 86.6%) |
| Dev (n=81) | 62 passed (76.5%) | 66 passed (81.5%, CI 71.7% to 88.4%) |
| Held-out (n=37) | 26 passed (70.3%) | 29 passed (78.4%, CI 62.8% to 88.6%) |
| Failed (all) | 20 | 13 |

The held-out interval for the after run (62.8% to 88.6%) overlaps heavily with the before run (54.2% to 82.5%), so I treat the held-out gain as suggestive, not proven.

**Paired comparison (same cases, before vs after):**

- Correctness (n=75): 52/75 to 55/75, +4.0% (95% CI −4.0% to +13.3%), 7 fixed and 4 broken, exact flip test p=0.549. Within noise.
- Refusal/clarification (n=43): 36/43 to 40/43, +9.3% (95% CI +2.3% to +20.9%), 4 fixed and 0 broken, exact flip test p=0.125. The tool labels this within noise. The interval excludes zero but the flip test does not reach significance, so I call it suggestive.

**By category (before to after, passed/n):**

| Category | Metric | Before | After |
|---|---|---|---|
| direct_factual | correctness | 17/25 | 20/25 |
| multi_hop | correctness | 5/10 | 7/10 |
| multi_intent | correctness | 4/5 | 4/5 |
| numeric_policy | correctness | 13/15 | 12/15 |
| paraphrased | correctness | 13/20 | 12/20 |
| ambiguous | refusal/clarify | 4/8 | 8/8 |
| adversarial | refusal/clarify | 10/10 | 10/10 |
| off_topic | refusal/clarify | 10/10 | 10/10 |
| unanswerable | refusal/clarify | 12/15 | 12/15 |

All categories have fewer than 30 paired cases, so they are indicative only.

**Cases fixed (correctness):** add-002, gen-022, gen-037, gen-073, add-006, gap-028, gen-089.
**Cases fixed (clarification):** amb-04, amb-07, human-16, human-17.

**Cases that got worse (correctness):**

- **gen-096** (currency): the new answer added a claim that prices apply to orders to Canada, which is not in the source.
- **gen-068** (warranty): the new answer added a 10-year Dutch Oven warranty that is not in the retrieved source excerpt.
- **add-004** (shipping day): the new answer dropped the day name (Wednesday) that the reference requires.
- **human-04** (first-time-buyer code): the new answer asked a clarifying question instead of giving the WELCOME10 code.

No refusal/clarification cases got worse.

**Cost and latency:**

- Input tokens 44,593 to 77,238 (+73%); output tokens 4,264 to 3,356 (−21%).
- Cost per run $0.0062 to $0.0091 (+47%); cost per answer about $0.0001 in both. [VERIFY pricing source.]
- Latency is not comparable. The baseline p50/p95 (31 ms / 70 ms) looks like cached or replayed answers; the after run was 1,732 ms / 69,676 ms. I make no claim about speed.

## 5. What didn't work

- **The overall correctness gain is within noise.** 7 cases fixed and 4 broken is not enough to call it an improvement on correctness.
- **The clarification rule over-triggers.** For human-04 it asked a question when the answer was available, and human-02 ("do i have to pay to ship a return back") also gets a clarifying question instead of the $6.50 return-label answer. Paraphrased went from 13/20 to 12/20 and numeric_policy from 13/15 to 12/15 (small n).
- **Larger top_k may add unsupported detail.** gen-096 and gen-068 added extra claims after retrieval went from 4 to 8 chunks. This is a hypothesis; I did not test top_k separately.
- **Persistent failures.** gen-001, gen-105 and gap-041 fail in both runs. The bot says it lacks information (or answers wrongly) although the documents contain the answer, so more chunks did not fix the underlying retrieval or grounding problem.
- **Some "fixes" are shorter answers.** gen-022, gen-073 and gen-089 moved from partial to correct mainly because the bot stopped adding extra sentences the judge penalises. Part of the gain reflects judge strictness, not new information.

## 6. What I would do for a client

These are recommendations, not tested results.

1. Change one variable at a time (prompt alone, then top_k alone) so effects can be attributed.
2. Use a larger test set. At 118 cases (75 correctness, 43 refusal), differences below about 9% cannot be told from noise.
3. Investigate retrieval for the false "I don't have that information" failures (chunking, hybrid retrieval), since top_k alone did not fix them.
4. Narrow the clarification rule so it fires only when no product or policy can be identified from the question.
5. Add an instruction to answer only what was asked and avoid extra claims.
6. Re-measure latency on uncached runs and set cost prices explicitly.
7. Label more than 24 cases by hand to confirm the judge's agreement.

## Limitations

- Results come from this test set only, scored by an automated judge.
- Single-turn questions only; multi-turn conversations and live integrations were not tested.
- Categories with fewer than 20 cases are indicative only.
- This is my own bot on a fictional store, not a client system.
