from pathlib import Path
import re

HELPER = '''

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
'''

p = Path("src/audit/targets/python_target.py")
s = p.read_text(encoding="utf-8")
if "_load_bot_module" not in s:
    anchor = "from audit.targets.base import Target, TargetResponse\n"
    assert anchor in s, "anchor not found"
    s = s.replace(anchor, anchor + HELPER, 1)
    old_sig = 'def from_rag_bot(cls, llm, config=None, name: str = "my_rag_bot"):'
    assert old_sig in s, "signature not found"
    s = s.replace(old_sig, 'def from_rag_bot(cls, llm, config=None, name: str = "my_rag_bot", entrypoint=None):', 1)
    s, n = re.subn(r"from rag_bot import BotConfig, RagBot[^\n]*",
                   "mod = _load_bot_module(entrypoint)\n        BotConfig, RagBot = mod.BotConfig, mod.RagBot", s)
    assert n == 1, "import line not found"
    p.write_text(s, encoding="utf-8")
    print("python_target.py patched")
else:
    print("python_target.py already patched")

c = Path("src/audit/cli.py")
t = c.read_text(encoding="utf-8")
old = "PythonTarget.from_rag_bot(client, name=t.name)"
if old in t:
    t = t.replace(old, 'PythonTarget.from_rag_bot(client, name=t.name, entrypoint=getattr(t, "entrypoint", None))', 1)
    c.write_text(t, encoding="utf-8")
    print("cli.py patched")
else:
    print("cli.py: already patched or line not found")
