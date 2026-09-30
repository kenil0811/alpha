"""Attachment context building: a file inlined, a folder as a tree with its text files, an
image and an audio file named honestly, symlinks never followed, and every size capped."""

from __future__ import annotations

import base64
from pathlib import Path

from alpha.assistant.attachments import (
    MAX_FOLDER_INLINE_CHARS,
    MAX_INLINE_CHARS,
    AttachmentIn,
    attachment_summaries,
    build_context,
)


def test_no_attachments_is_empty() -> None:
    assert build_context([]) == ""


def test_text_file_inlined(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello from the file")
    ctx = build_context([AttachmentIn(kind="file", name="notes.txt", path=str(path))])
    assert "hello from the file" in ctx
    assert "notes.txt" in ctx


def test_text_file_truncated_with_note(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("x" * (MAX_INLINE_CHARS + 500))
    ctx = build_context([AttachmentIn(kind="file", name="big.txt", path=str(path))])
    assert "truncated" in ctx
    assert ctx.count("x") <= MAX_INLINE_CHARS + 20  # inlined body capped, not the whole file


def test_web_upload_via_base64(tmp_path: Path) -> None:
    content = base64.b64encode(b"from the browser").decode()
    ctx = build_context([AttachmentIn(kind="file", name="upload.txt", content_b64=content)])
    assert "from the browser" in ctx


def test_image_is_named_honestly_not_read() -> None:
    ctx = build_context([AttachmentIn(kind="image", name="photo.png", mime="image/png")])
    assert "photo.png" in ctx
    assert "no vision" in ctx


def test_audio_is_named_honestly_not_transcribed() -> None:
    ctx = build_context([AttachmentIn(kind="audio", name="memo.m4a")])
    assert "memo.m4a" in ctx
    assert "not transcribed" in ctx


def test_folder_lists_entries_and_inlines_text(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "readme.md").write_text("# hi")
    (root / "photo.png").write_bytes(b"\x89PNG\r\n")
    ctx = build_context([AttachmentIn(kind="folder", name="proj", path=str(root))])
    assert "readme.md" in ctx
    assert "# hi" in ctx
    assert "photo.png" in ctx  # listed, but its bytes are never inlined


def test_folder_caps_total_inlined_text(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for i in range(5):
        (root / f"f{i}.txt").write_text("y" * (MAX_FOLDER_INLINE_CHARS // 2))
    ctx = build_context([AttachmentIn(kind="folder", name="proj", path=str(root))])
    assert ctx.count("y") <= MAX_FOLDER_INLINE_CHARS + 50


def test_folder_never_follows_a_symlink(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read me")
    (root / "link.txt").symlink_to(outside)
    ctx = build_context([AttachmentIn(kind="folder", name="proj", path=str(root))])
    assert "do not read me" not in ctx
    assert "link.txt" not in ctx  # skipped outright, not even listed


def test_folder_skips_a_symlinked_subdirectory(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "leak.txt").write_text("outside content")
    (root / "linked_dir").symlink_to(outside_dir)
    ctx = build_context([AttachmentIn(kind="folder", name="proj", path=str(root))])
    assert "outside content" not in ctx
    assert "leak.txt" not in ctx


def test_missing_folder_path_is_reported_not_raised() -> None:
    ctx = build_context([AttachmentIn(kind="folder", name="gone", path="/no/such/dir")])
    assert "not found" in ctx


def test_binary_file_is_named_not_garbled(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(bytes(range(256)))
    ctx = build_context([AttachmentIn(kind="file", name="data.bin", path=str(path))])
    assert "not text" in ctx


def test_attachment_summaries_never_carry_bytes_or_path() -> None:
    content = base64.b64encode(b"z").decode()
    items = [
        AttachmentIn(kind="file", name="a.txt", path="/secret/path/a.txt", size=12),
        AttachmentIn(kind="file", name="b.txt", content_b64=content, size=1),
    ]
    summaries = attachment_summaries(items)
    assert summaries == [
        {"kind": "file", "name": "a.txt", "mime": None, "size": 12},
        {"kind": "file", "name": "b.txt", "mime": None, "size": 1},
    ]
    assert "path" not in str(summaries) and "/secret/" not in str(summaries)
