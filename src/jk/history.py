"""改动前快照与撤销：每次改动前把 notebooks/ 与 archive/ 整体复制到 history/。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .store import Store

KEEP = 50
_TRACKED = ("notebooks", "archive")


def snapshot(store: Store, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = store.history_dir / stamp
    dest.mkdir(parents=True)
    for name in _TRACKED:
        src = store.home / name
        if src.is_dir():
            shutil.copytree(src, dest / name)
    (dest / "meta.json").write_text(
        json.dumps({"label": label, "time": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
        encoding="utf-8",
    )
    _prune(store)
    return dest


def _snapshots(store: Store) -> list[Path]:
    if not store.history_dir.is_dir():
        return []
    return sorted(p for p in store.history_dir.iterdir() if (p / "meta.json").is_file())


def _prune(store: Store) -> None:
    snaps = _snapshots(store)
    for old in snaps[: max(0, len(snaps) - KEEP)]:
        shutil.rmtree(old)


def undo(store: Store) -> str | None:
    """恢复到最近一次改动之前；返回被撤销操作的说明，没有可撤销的返回 None。"""
    snaps = _snapshots(store)
    if not snaps:
        return None
    last = snaps[-1]
    label = json.loads((last / "meta.json").read_text(encoding="utf-8"))["label"]
    for name in _TRACKED:
        cur = store.home / name
        trash = store.home / f".{name}.undo-old"
        if trash.exists():
            shutil.rmtree(trash)
        if cur.exists():
            cur.rename(trash)
        if (last / name).is_dir():
            shutil.copytree(last / name, cur)
        if trash.exists():
            shutil.rmtree(trash)
    shutil.rmtree(last)
    return label
