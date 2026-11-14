"""PythonTarget: wraps the RAG bot so the audit can call it through the Target interface."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from audit.targets.base import Target, TargetResponse


def _load_bot_module(entrypoint):
    """Load the bot file named in the YAML entrypoint (default: rag_bot.py)."""
    import importlib.util
    path = Path(entrypoint or "examples/my_rag_bot/rag_bot.py").resolve()
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("bot_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class PythonTarget(Target):
    def __init__(self, bot, name: str = "my_rag_bot", config=None):
        self.bot = bot
        self.name = name
        self.config = config          # the bot's BotConfig, used for the snapshot

    @classmethod
    def from_rag_bot(cls, llm, config=None, name: str = "my_rag_bot", entrypoint=None):
        """Build the demo bot. `llm` is the object with .complete(...)."""
        sys.path.insert(0, str(Path("examples/my_rag_bot").resolve()))
        mod = _load_bot_module(entrypoint)
        BotConfig, RagBot = mod.BotConfig, mod.RagBot

        config = config or BotConfig()
        return cls(RagBot(config, llm=llm), name=name, config=config)

    def answer(self, question: str) -> TargetResponse:
        start = time.perf_counter()
        try:
            out = self.bot.answer(question)        # the bot gets ONLY the question
        except Exception as e:
            return TargetResponse(
                error=f"{type(e).__name__}: {e}",
                latency_ms=(time.perf_counter() - start) * 1000)
        return TargetResponse(
            answer=out.answer,
            contexts=out.contexts,
            latency_ms=(time.perf_counter() - start) * 1000,
            input_tokens=out.input_tokens,
            output_tokens=out.output_tokens)

    def config_snapshot(self) -> dict:
        """Prompt, model and settings, stored in runs.config_snapshot."""
        return self.config.snapshot() if self.config else {}