from audit.llm.client import LLMClient

MODEL = "gemini/gemini-3.8-flash"   # change only this line if Google renames models

llm = LLMClient()
msgs = [{"role": "user", "content": "Say hello in one sentence."}]

r1 = llm.complete(msgs, model=MODEL)
print(r1)   # first call: cached=False, shows tokens, cost, latency

r2 = llm.complete(msgs, model=MODEL)
print(r2)   # second call: cached=True, cost 0