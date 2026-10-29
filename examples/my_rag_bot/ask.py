"""Ask the bot one question from the terminal.

    $env:PYTHONPATH="src"; python examples/my_rag_bot/ask.py "How long do I have to return an item?"
    $env:PYTHONPATH="src"; python examples/my_rag_bot/ask.py "..." --show-context
"""
import argparse

from rag_bot import BotConfig, RagBot

parser = argparse.ArgumentParser()
parser.add_argument("question")
parser.add_argument("--show-context", action="store_true", help="print the retrieved chunks")
parser.add_argument("--model", default=None, help="override the model name")
args = parser.parse_args()

config = BotConfig(model=args.model) if args.model else BotConfig()
bot = RagBot(config)
result = bot.answer(args.question)

print("\nANSWER:\n" + result.answer)
print("\nSOURCES:")
for s in result.sources:
    print("  -", s)
if args.show_context:
    print("\nCONTEXT GIVEN TO THE MODEL:")
    for c in result.contexts:
        print("-" * 60 + "\n" + c)
print(f"\n[{result.input_tokens} in / {result.output_tokens} out tokens, "
      f"${result.cost_usd:.6f}, {result.latency_ms:.0f} ms]")
