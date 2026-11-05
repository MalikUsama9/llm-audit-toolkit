"""HttpTarget: audits any bot that is reachable through a web API.

Every client's API looks different, so nothing about the request or the
response shape is hard-coded. It all comes from the `target:` section of YAML:

    target:
      name: client_bot
      type: http
      url: https://client.example.com/api/chat
      headers:
        Authorization: "Bearer ${CLIENT_API_KEY}"   # the secret lives in .env
      payload_template: {"question": "{question}"}
      answer_path: data.answer
      contexts_path: data.sources                   # optional

If the response has no contexts, `contexts` is None and the audit runs in
black-box mode.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
import time
from typing import Any

import httpx

from audit.targets.base import Target, TargetResponse


def _expand_env(value: str) -> str:
    """Replace ${VAR} with the environment variable VAR (empty if unset)."""
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def _fill(template: Any, question: str) -> Any:
    """Copy the template, replacing {question} inside every string."""
    if isinstance(template, str):
        return template.replace("{question}", question)
    if isinstance(template, dict):
        return {k: _fill(v, question) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, question) for v in template]
    return template


def _get_path(data: Any, path: str) -> Any:
    """Follow a dotted path like 'data.answers.0.text'. Raises KeyError/IndexError if missing."""
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _as_text(item: Any) -> str:
    """One context item -> text. Accepts plain strings or dicts with text/content."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("text", "content", "chunk", "snippet"):
            if key in item:
                return str(item[key])
    return str(item)


class HttpTarget(Target):
    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        payload_template: Any = None,
        answer_path: str = "answer",
        contexts_path: str | None = "contexts",
        timeout_s: float = 60.0,
        name: str = "http_bot",
        transport: httpx.AsyncBaseTransport | None = None,   # tests pass a fake transport
    ):
        self.url = url
        self.headers = {k: _expand_env(str(v)) for k, v in (headers or {}).items()}
        self.payload_template = payload_template or {"question": "{question}"}
        self.answer_path = answer_path
        self.contexts_path = contexts_path
        self.timeout_s = timeout_s
        self.name = name
        self._transport = transport

    @classmethod
    def from_config(cls, cfg: dict) -> "HttpTarget":
        """Build from the `target:` section of audit.yaml."""
        return cls(
            url=cfg["url"],
            headers=cfg.get("headers"),
            payload_template=cfg.get("payload_template"),
            answer_path=cfg.get("answer_path", "answer"),
            contexts_path=cfg.get("contexts_path", "contexts"),
            timeout_s=float(cfg.get("timeout_s", 60)),
            name=cfg.get("name", "http_bot"),
        )

    # ---- the async part: uses httpx.AsyncClient --------------------------
    async def aanswer(self, question: str) -> TargetResponse:
        start = time.perf_counter()

        def ms() -> float:
            return (time.perf_counter() - start) * 1000

        payload = _fill(self.payload_template, question)   # only the question goes out
        try:
            async with httpx.AsyncClient(
                    transport=self._transport, timeout=self.timeout_s) as client:
                resp = await client.post(self.url, json=payload, headers=self.headers)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as e:
            return TargetResponse(
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}", latency_ms=ms())
        except httpx.HTTPError as e:
            return TargetResponse(
                error=f"request failed: {type(e).__name__}: {e}", latency_ms=ms())
        except ValueError:
            return TargetResponse(error="response was not valid JSON", latency_ms=ms())

        try:
            answer = _get_path(body, self.answer_path)
        except (KeyError, IndexError, ValueError):
            return TargetResponse(
                error=f"answer_path '{self.answer_path}' not found in response", latency_ms=ms())

        contexts = None   # None = black-box mode (no retrieval info available)
        if self.contexts_path:
            try:
                raw = _get_path(body, self.contexts_path)
                if isinstance(raw, list) and raw:
                    contexts = [_as_text(item) for item in raw]
            except (KeyError, IndexError, ValueError):
                pass

        return TargetResponse(answer=str(answer), contexts=contexts, latency_ms=ms())

    # ---- the normal sync entry point, same as PythonTarget ----------------
    def answer(self, question: str) -> TargetResponse:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aanswer(question))
        # Already inside an event loop: run in a separate thread instead.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.aanswer(question)).result()

    def config_snapshot(self) -> dict:
        """Settings for runs.config_snapshot. Headers are left out (they hold secrets)."""
        return {
            "type": "http",
            "url": self.url,
            "payload_template": self.payload_template,
            "answer_path": self.answer_path,
            "contexts_path": self.contexts_path,
        }