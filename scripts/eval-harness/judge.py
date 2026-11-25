import os, json, re, time
from anthropic import Anthropic

client = Anthropic(max_retries=5)  # built-in backoff for rate limits
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-4-6")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")

RUBRIC = """Score the RESPONSE from 1 to 5:
5 = fully correct, complete, and clear for the INPUT
3 = partially correct or missing key points
1 = wrong, irrelevant, or unusable
Pass threshold: score >= 4."""

SYSTEM = f"""You are a strict evaluator. {RUBRIC}
Return ONLY a JSON object, no markdown, with keys:
"score" (integer 1-5),
"reasoning" (2-4 sentences),
"evidence" (list of 1-3 VERBATIM quotes copied exactly from the RESPONSE that support your score)."""

def call_judge(case):
    user = f"INPUT:\n{case['input']}\n\nRESPONSE:\n{case['output']}"
    last_err = None
    for attempt in range(3):  # retries bad JSON, not API errors
        try:
            r = client.messages.create(
                model=JUDGE_MODEL, max_tokens=800, temperature=0,
                system=SYSTEM, messages=[{"role": "user", "content": user}])
            text = r.content[0].text
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            assert 1 <= int(data["score"]) <= 5
            return data, r.usage.input_tokens, r.usage.output_tokens
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Judge failed for {case['id']}: {last_err}")

def verify_evidence(quotes, output):
    norm = lambda s: " ".join(s.split())
    out = norm(output)
    return bool(quotes) and all(norm(q) in out for q in quotes)