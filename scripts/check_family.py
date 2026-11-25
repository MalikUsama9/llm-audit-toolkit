# check_family.py  -> python check_family.py BOT_MODEL GENERATOR_MODEL JUDGE_MODEL
import sys

FAMILIES = {
    "gemini": "google", "google": "google",
    "gpt": "openai", "openai": "openai", "o1": "openai", "o3": "openai", "o4": "openai",
    "claude": "anthropic", "anthropic": "anthropic",
    "llama": "meta", "meta": "meta",
    "mistral": "mistral", "mixtral": "mistral",
    "qwen": "alibaba", "deepseek": "deepseek", "grok": "xai",
}

def family(name: str) -> str:
    s = name.lower()
    for key, fam in FAMILIES.items():
        if key in s:
            return fam
    return "unknown"

bot, gen, judge = sys.argv[1:4]
fb, fg, fj = family(bot), family(gen), family(judge)
print(f"bot={fb}  generator={fg}  judge={fj}")
if "unknown" in (fb, fg, fj):
    print("WARNING: could not identify one family; check by hand.")
if fj in (fb, fg):
    print("FAIL: judge shares a family with the bot or the generator. Pick another.")
    sys.exit(1)
print("OK: judge family differs from both.")
