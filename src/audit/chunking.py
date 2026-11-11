# src/audit/chunking.py
import re
from pathlib import Path
from pydantic import BaseModel

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


class Chunk(BaseModel):
    chunk_id: str   # "03_returns_and_refunds.md#refund-window"
    doc: str
    heading: str    # "Returns > Refund window"
    text: str


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "intro"


def split_sections(text: str) -> list[tuple[str, str]]:
    sections, path, buf = [], [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" > ".join(path) or "Intro", body))

    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            buf.clear()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    flush()
    return sections


def split_long(body: str, max_words: int) -> list[str]:
    if len(body.split()) <= max_words:
        return [body]
    parts, cur = [], []
    for para in re.split(r"\n\s*\n", body):
        if cur and len(" ".join(cur + [para]).split()) > max_words:
            parts.append("\n\n".join(cur))
            cur = []
        cur.append(para)
    if cur:
        parts.append("\n\n".join(cur))
    return parts


def chunk_markdown(path: Path, min_words=60, max_words=350) -> list[Chunk]:
    merged: list[list[str]] = []
    for heading, body in split_sections(path.read_text(encoding="utf-8")):
        if merged and len(body.split()) < min_words:
            merged[-1][1] += f"\n\n{heading}\n{body}"   # fold tiny section into previous
        else:
            merged.append([heading, body])

    chunks, seen = [], {}
    for heading, body in merged:
        for piece in split_long(body, max_words):
            slug = slugify(heading.split(" > ")[-1])
            seen[slug] = seen.get(slug, 0) + 1
            suffix = "" if seen[slug] == 1 else f"-{seen[slug]}"
            chunks.append(Chunk(
                chunk_id=f"{path.name}#{slug}{suffix}",
                doc=path.name,
                heading=heading,
                text=f"{heading}\n\n{piece}",
            ))
    return chunks


def chunk_dir(folder: str) -> list[Chunk]:
    out = []
    for p in sorted(Path(folder).glob("*.md")):
        out.extend(chunk_markdown(p))
    return out  