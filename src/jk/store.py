"""数据目录读写：~/.jk/notebooks/*.md。"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .model import Item, Notebook, now_minute, fmt_dt, parse_notebook, DONE


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "-", name).strip("-.")
    return (cleaned or "untitled") + ".md"


class Store:
    def __init__(self, home: Path):
        self.home = home
        self.notebooks_dir = home / "notebooks"
        self.archive_dir = home / "archive"
        self.history_dir = home / "history"

    # ---------- 读 ----------
    def _read_dir(self, directory: Path) -> list[Notebook]:
        if not directory.is_dir():
            return []
        books = []
        for path in sorted(directory.glob("*.md")):
            books.append(parse_notebook(path.read_text(encoding="utf-8"), path.stem))
        return books

    def load(self) -> list[Notebook]:
        """读全部记事本，并修复手写条目：补 id、补创建时间、补完成时间。"""
        books = self._read_dir(self.notebooks_dir)
        now = fmt_dt(now_minute())
        used = {it.id for nb in books for it in nb.items if it.id > 0}
        dirty = False
        for nb in books:
            seen: set[int] = set()
            for it in nb.items:
                if it.id <= 0 or it.id in seen:
                    it.id = next_free_id(used)
                    used.add(it.id)
                    dirty = True
                seen.add(it.id)
                if not it.created:
                    it.created, dirty = now, True
                if it.state == DONE and not it.done_at:
                    it.done_at, dirty = now, True
            if not nb.created:
                nb.created, dirty = now[:10], True
        if dirty:
            self.save(books)
        return books

    def load_archive(self) -> list[Notebook]:
        return self._read_dir(self.archive_dir)

    # ---------- 写 ----------
    def save(self, books: list[Notebook]) -> None:
        """写回全部记事本；空记事本删除文件，改名的记事本清掉旧文件。"""
        self.notebooks_dir.mkdir(parents=True, exist_ok=True)
        keep: set[str] = set()
        for nb in books:
            if not nb.items and not nb.extra:
                continue
            nb.items.sort(key=lambda i: i.id)
            fname = safe_filename(nb.name)
            keep.add(fname)
            path = self.notebooks_dir / fname
            content = nb.to_markdown()
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                atomic_write(path, content)
        for path in self.notebooks_dir.glob("*.md"):
            if path.name not in keep:
                path.unlink()

    def save_archive(self, books: list[Notebook]) -> None:
        for nb in books:
            atomic_write(self.archive_dir / safe_filename(nb.name), nb.to_markdown())


def next_free_id(used: set[int]) -> int:
    """取最小的未占用编号，让编号保持短小（已归档条目的编号会被复用）。"""
    i = 1
    while i in used:
        i += 1
    return i


def find_item(books: list[Notebook], item_id: int) -> tuple[Notebook, Item] | None:
    for nb in books:
        for it in nb.items:
            if it.id == item_id:
                return nb, it
    return None


def get_notebook(books: list[Notebook], name: str, create: bool = True) -> Notebook | None:
    for nb in books:
        if nb.name == name:
            return nb
    if not create:
        return None
    nb = Notebook(name=name, created=fmt_dt(now_minute())[:10])
    books.append(nb)
    return nb
