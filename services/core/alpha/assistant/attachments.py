"""What a person attaches to a message (files, a folder, images, audio) becomes context text for
the step loop's model call. Raw bytes stay wherever they already are: on the desktop Core reads
straight from the local path the person picked; from the web the browser sends bytes, which are
never written back to disk here, only read into the prompt. Everything is capped so one big
folder or file cannot blow the model call's budget, and no symlink is ever followed (skipped
outright, whether it points in or out of the chosen folder)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MAX_ATTACHMENTS = 10
# Per-file text read/inline caps (characters, not bytes, but close enough for a budget).
MAX_INLINE_CHARS = 6000
MAX_READ_BYTES = 400_000
# A folder: at most this many entries listed, and this many characters of text inlined in total.
MAX_FOLDER_ENTRIES = 200
MAX_FOLDER_INLINE_CHARS = 12000

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".csv", ".tsv", ".html", ".htm", ".css", ".rs", ".go", ".java", ".c", ".h", ".hpp",
    ".cpp", ".cc", ".sh", ".sql", ".ini", ".cfg", ".env", ".xml", ".log", ".rst",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"}


class AttachmentIn(BaseModel):
    """One thing the person attached to a message. `path` is a local file or folder Core can
    read directly (desktop); `content_b64` is its bytes when the browser sent them instead
    (web) — only ever used for a single file, never a folder."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(file|folder|image|audio)$")
    name: str = Field(min_length=1, max_length=260)
    path: str | None = Field(default=None, max_length=4096)
    content_b64: str | None = Field(default=None, max_length=8_000_000)
    mime: str | None = Field(default=None, max_length=120)
    size: int | None = Field(default=None, ge=0)


def attachment_summaries(attachments: list[AttachmentIn]) -> list[dict[str, Any]]:
    """What is worth keeping on the turn's own record: never the bytes, never the raw path
    beyond its name (the folder listing, if wanted again, is re-read from the source)."""
    return [
        {"kind": a.kind, "name": a.name, "mime": a.mime, "size": a.size}
        for a in attachments[:MAX_ATTACHMENTS]
    ]


def build_context(attachments: list[AttachmentIn]) -> str:
    """The ATTACHMENTS section of a step prompt: text inlined (truncated with a note), a
    folder as a tree plus its text files, an image named honestly as unseen (this call has no
    vision), audio named honestly as not transcribed."""
    if not attachments:
        return ""
    blocks: list[str] = []
    for item in attachments[:MAX_ATTACHMENTS]:
        try:
            blocks.append(_one(item))
        except Exception as exc:  # a bad path/bytes never breaks the whole turn
            blocks.append(f"- {item.name} ({item.kind}): could not be read ({exc})")
    return "ATTACHMENTS (what the person attached to this message):\n" + "\n".join(blocks)


def _one(item: AttachmentIn) -> str:
    if item.kind == "folder":
        return _folder(item)
    if item.kind == "image":
        return _image(item)
    if item.kind == "audio":
        return _audio(item)
    return _file(item)


def _file(item: AttachmentIn) -> str:
    ext = Path(item.name).suffix.lower()
    if ext in IMAGE_EXTS:
        return _image(item)
    if ext in AUDIO_EXTS:
        return _audio(item)
    text = _read_text(item)
    if text is None:
        return f'- file "{item.name}": not text; only its name and type are known.'
    clipped = text[:MAX_INLINE_CHARS]
    note = "" if len(text) <= MAX_INLINE_CHARS else f" (truncated, {len(text)} chars total)"
    return f'- file "{item.name}"{note}:\n```\n{clipped}\n```'


def _image(item: AttachmentIn) -> str:
    return (
        f'- image "{item.name}"'
        + (f" ({item.mime})" if item.mime else "")
        + ": attached, but this model connection has no vision — only the file's name and type "
        "are known. Say so honestly if asked what is in it."
    )


def _audio(item: AttachmentIn) -> str:
    # ponytail: no local file-transcription path wired up yet (only live mic speech exists, see
    # speech.rs/stt_helper.swift); add one there and call it here if this needs to read audio.
    return f'- audio file "{item.name}": attached, but not transcribed. Its content is not known.'


def _folder(item: AttachmentIn) -> str:
    if not item.path:
        return f'- folder "{item.name}": no path given; nothing could be read.'
    root = Path(item.path).resolve()
    if not root.is_dir():
        return f'- folder "{item.name}": not found on this machine.'
    lines: list[str] = [f'- folder "{item.name}" (listing, then any text files):']
    entries = 0
    inlined = 0
    text_blocks: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Skip every symlinked directory outright (never followed, in or out of the folder).
        dirnames[:] = sorted(d for d in dirnames if not (Path(dirpath) / d).is_symlink())
        for name in sorted(filenames):
            if entries >= MAX_FOLDER_ENTRIES:
                lines.append(f"  … more than {MAX_FOLDER_ENTRIES} entries, the rest are not listed")
                return "\n".join(lines + text_blocks)
            full = Path(dirpath) / name
            if full.is_symlink():
                continue
            rel = full.relative_to(root)
            entries += 1
            lines.append(f"  {rel}")
            ext = full.suffix.lower()
            if ext in TEXT_EXTS and inlined < MAX_FOLDER_INLINE_CHARS:
                try:
                    raw = full.read_bytes()[:MAX_READ_BYTES]
                    text = raw.decode("utf-8")
                except Exception:
                    continue
                budget = MAX_FOLDER_INLINE_CHARS - inlined
                clipped = text[:budget]
                inlined += len(clipped)
                note = "" if len(text) <= len(clipped) else " (truncated)"
                text_blocks.append(f'  file "{rel}"{note}:\n```\n{clipped}\n```')
    return "\n".join(lines + text_blocks)


def _read_text(item: AttachmentIn) -> str | None:
    if item.content_b64 is not None:
        try:
            raw = base64.b64decode(item.content_b64)[:MAX_READ_BYTES]
            return raw.decode("utf-8")
        except Exception:
            return None
    if not item.path:
        return None
    path = Path(item.path)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        raw = path.read_bytes()[:MAX_READ_BYTES]
        return raw.decode("utf-8")
    except Exception:
        return None
