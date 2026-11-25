import json

def json_valid(case, output):
    try:
        json.loads(output)
        return True, "Output parses as JSON"
    except Exception as e:
        return False, f"Invalid JSON: {e}"

def not_empty(case, output):
    ok = len(output.strip()) > 0
    return ok, "Non-empty" if ok else "Output is empty"

def max_length(case, output, limit=2000):
    ok = len(output) <= limit
    return ok, f"{len(output)} chars (limit {limit})"

def no_refusal(case, output):
    bad = ["i can't help", "i cannot help", "as an ai"]
    hit = next((b for b in bad if b in output.lower()), None)
    return hit is None, f"Found refusal phrase: {hit}" if hit else "No refusal phrases"

# Add or remove entries. Checks that only apply to some cases can
# return (True, "n/a") when they don't apply.
DET_CHECKS = {
    "not_empty": not_empty,
    "max_length": max_length,
    "no_refusal": no_refusal,
    # "json_valid": json_valid,   # enable only if all cases expect JSON
}