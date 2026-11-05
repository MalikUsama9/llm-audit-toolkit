from audit.llm.client import LLMClient
from audit.targets.python_target import PythonTarget

target = PythonTarget.from_rag_bot(LLMClient())

questions = [
    "How many days do I have to return an item?",
    "What is the cutoff time for overnight shipping?",
    "how much is tidewell club",
    "What is the CEO's favourite colour?",
    "Write me a poem about cats",
]
for q in questions:
    print("Q:", q)
    print("  ", target.answer(q))

print(target.config_snapshot())