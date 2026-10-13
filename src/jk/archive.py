"""自动归档：完成满 N 天的任务从记事本移到 archive/ 同名文件（移动，不删除）。"""

from __future__ import annotations

from datetime import date, timedelta

from .model import DONE, TASK, Notebook
from .store import Store, get_notebook


def auto_archive(store: Store, books: list[Notebook], days: int, today: date | None = None) -> int:
    """归档完成日期 <= 今天-days 的任务；days=0 表示关闭。返回归档条数（已写盘）。"""
    if days <= 0:
        return 0
    cutoff = ((today or date.today()) - timedelta(days=days)).isoformat()
    archive = store.load_archive()
    moved = 0
    for nb in books:
        keep = []
        for it in nb.items:
            if it.kind == TASK and it.state == DONE and it.done_at and it.done_at[:10] <= cutoff:
                get_notebook(archive, nb.name).items.append(it)
                moved += 1
            else:
                keep.append(it)
        nb.items = keep
    if moved:
        # 先写归档再写记事本：中途失败最多多一份，不会丢
        store.save_archive(archive)
        store.save(books)
    return moved
