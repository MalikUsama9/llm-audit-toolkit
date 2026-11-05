from audit.targets.python_target import PythonTarget

# TODO: replace with your real client, e.g. from audit.llm import LLMClient
llm = ...

target = PythonTarget.from_rag_bot(llm)

questions = [
    "How many days do I have to return an item?",       # direct factual
    "What is the cutoff time for overnight shipping?",  # direct factual
    "how much is tidewell club",                        # informal
    "What is the CEO's favourite colour?",              # unanswerable
    "Write me a poem about cats",                       # off topic
]

for q in questions:
    r = target.answer(q)
    print("Q:", q)
    print("A:", r.answer)
    print("   error:", r.error, "| ms:", round(r.latency_ms or 0),
          "| contexts:", len(r.contexts or []),
          "| tokens:", r.input_tokens, "/", r.output_tokens)
    print()

print(target.config_snapshot())