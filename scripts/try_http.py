import httpx

from audit.targets.http_target import HttpTarget


def handler(request: httpx.Request) -> httpx.Response:
    # Fake client API: no real server needed.
    if request.url.path.endswith("/blackbox"):
        return httpx.Response(200, json={"data": {"answer": "30 days"}})
    if request.url.path.endswith("/broken"):
        return httpx.Response(500, text="server exploded")
    return httpx.Response(200, json={"data": {"answer": "30 days", "sources": ["Returns - 30 days"]}})


transport = httpx.MockTransport(handler)

print("1) with contexts:")
t = HttpTarget("http://fake/chat", answer_path="data.answer",
               contexts_path="data.sources", transport=transport)
print("  ", t.answer("How many days do I have to return an item?"))

print("2) black-box (no contexts):")
t = HttpTarget("http://fake/blackbox", answer_path="data.answer",
               contexts_path="data.sources", transport=transport)
print("  ", t.answer("How many days do I have to return an item?"))

print("3) server error (should return error=..., not crash):")
t = HttpTarget("http://fake/broken", answer_path="data.answer", transport=transport)
print("  ", t.answer("anything"))

print("4) wrong answer_path:")
t = HttpTarget("http://fake/chat", answer_path="nope.nothing", transport=transport)
print("  ", t.answer("anything"))

print(t.config_snapshot())