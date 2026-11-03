# src/audit/gap_generator.py
"""Generate the two missing categories: paraphrased and multi_hop.

Usage:
    python -m audit.gap_generator
"""
import argparse
import json
import re
from pathlib import Path

from pydantic import ValidationError

from audit.chunking import chunk_dir
from audit.models import TestCase
from audit.qa_generator import QuotaExceeded, call_llm

PARA_PROMPT = """You write test questions for a customer-support chatbot.

Using ONLY the excerpt below, write {k} questions that a real customer might type
in a chat window. Make them informal and messy: lowercase, slang or abbreviations,
vague wording, a small typo now and then. Do NOT copy the excerpt's wording.
Each question must still be fully answerable from the excerpt alone.
The reference_answer must use only facts stated in the excerpt (1-3 sentences).

Return ONLY JSON, no preamble and no code fences:
{{"items": [{{"question": "...", "reference_answer": "...", "difficulty": "easy"}}]}}

Excerpt (id: {chunk_id}):
{text}
"""

MULTI_PROMPT = """You write test questions for a customer-support chatbot.

Below are TWO excerpts from different documents. Write {k} questions that a real
customer might ask where the answer REQUIRES facts from BOTH excerpts (for example
combining a policy from one with a product detail or price from the other).
Rules:
- A question answerable from only one excerpt does not count.
- The reference_answer must use only facts stated in the two excerpts (1-3 sentences).
- If the excerpts have nothing natural to combine, return {{"items": []}}.

Return ONLY JSON, no preamble and no code fences:
{{"items": [{{"question": "...", "reference_answer": "...", "difficulty": "hard"}}]}}

Excerpt A (id: {id_a}):
{text_a}

Excerpt B (id: {id_b}):
{text_b}
"""


def parse_items(raw: str) -> list[dict]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned).get("items", [])


def make_rows(items, category, source_ref, source_text):
    rows = []
    for it in items:
        q, a = str(it.get("question", "")).strip(), str(it.get("reference_answer", "")).strip()
        if not q or not a:
            continue
        diff = it.get("difficulty", "medium")
        rows.append({
            "category": category,
            "question": q,
            "reference_answer": a,
            "difficulty": diff if diff in ("easy", "medium", "hard") else "medium",
            "expected_behavior": "answer",
            "source_ref": source_ref,
            "source_text": source_text,
            "origin": "generated",
            "reviewed": False,
        })
    return rows


def pick_pairs(chunks, n_pairs):
    """Pair each chunk with its most similar chunk from a DIFFERENT file."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode([c.text for c in chunks], normalize_embeddings=True)
    sims = emb @ emb.T
    file_of = [c.chunk_id.split("#")[0] for c in chunks]
    cands = []
    for i in range(len(chunks)):
        best, best_s = None, -1.0
        for j in range(len(chunks)):
            if file_of[j] != file_of[i] and sims[i][j] > best_s:
                best, best_s = j, sims[i][j]
        if best is not None:
            cands.append((best_s, i, best))
    cands.sort(reverse=True)
    used, pairs = set(), []
    for s, i, j in cands:
        if i in used or j in used:
            continue
        used |= {i, j}
        pairs.append((chunks[i], chunks[j]))
        if len(pairs) == n_pairs:
            break
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="data/demo/docs")
    ap.add_argument("--out", default="data/demo/draft_gap_cases.jsonl")
    ap.add_argument("--para-chunks", type=int, default=9, help="chunks used for paraphrased")
    ap.add_argument("--para-k", type=int, default=3)
    ap.add_argument("--pairs", type=int, default=12, help="chunk pairs used for multi_hop")
    ap.add_argument("--multi-k", type=int, default=2)
    args = ap.parse_args()

    chunks = chunk_dir(args.docs)
    rows: list[dict] = []

    try:
        # --- paraphrased: evenly spaced chunks so every doc area is covered ---
        step = len(chunks) / args.para_chunks
        chosen = [chunks[int(i * step)] for i in range(args.para_chunks)]
        print(f"Paraphrased: {len(chosen)} chunks")
        for n, ch in enumerate(chosen, 1):
            print(f"  [{n}/{len(chosen)}] {ch.chunk_id}")
            try:
                raw = call_llm(PARA_PROMPT.format(k=args.para_k, chunk_id=ch.chunk_id, text=ch.text))
                rows += make_rows(parse_items(raw), "paraphrased", [ch.chunk_id], ch.text)
            except QuotaExceeded:
                raise
            except (json.JSONDecodeError, ValueError, Exception) as e:
                print(f"    skipped: {type(e).__name__}: {str(e)[:120]}")

        # --- multi_hop: related chunks from different documents ---
        pairs = pick_pairs(chunks, args.pairs)
        print(f"\nMulti-hop: {len(pairs)} chunk pairs")
        for n, (a, b) in enumerate(pairs, 1):
            print(f"  [{n}/{len(pairs)}] {a.chunk_id}  +  {b.chunk_id}")
            try:
                raw = call_llm(MULTI_PROMPT.format(
                    k=args.multi_k, id_a=a.chunk_id, text_a=a.text, id_b=b.chunk_id, text_b=b.text))
                rows += make_rows(parse_items(raw), "multi_hop", [a.chunk_id, b.chunk_id],
                                  a.text + "\n\n---\n\n" + b.text)
            except QuotaExceeded:
                raise
            except Exception as e:
                print(f"    skipped: {type(e).__name__}: {str(e)[:120]}")
    except QuotaExceeded as e:
        print(f"\nQUOTA EXCEEDED: {e}\nSaving what was generated so far. Run again later.")
    except KeyboardInterrupt:
        print("\nStopped by you. Saving what was generated so far.")

    valid = []
    for n, r in enumerate(rows, 1):
        r["id"] = f"gap-{n:03d}"
        try:
            TestCase(**r)
            valid.append(r)
        except ValidationError as e:
            print(f"  invalid case {r['id']} dropped: {e.errors()[0]['msg']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in valid) + "\n", encoding="utf-8")
    from collections import Counter
    print(f"\nWrote {len(valid)} cases to {out}: {dict(Counter(r['category'] for r in valid))}")


if __name__ == "__main__":
    main()