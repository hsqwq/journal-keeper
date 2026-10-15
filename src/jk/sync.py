"""jk u：把教学云平台的待办同步进「云邮」记事本。不走 AI，按平台编号（src=ucloud:<id>）对应。

规则：
- 平台上有、jk 里没有 → 新增；第一次同步时，其他记事本里手记的同一件事（名字相似、截止同日）会被认领并移进「云邮」。
- 平台上有、jk 里有 → 名字或截止变了就更新；你在 jk 里标的完成状态保持不变。
- jk 里有、平台上没了 → 平台上消失只会是已提交，自动标完成。
- 已归档的（做完满一天）不会因为平台还挂着而重新加回来。
"""

from __future__ import annotations

from datetime import datetime

from .model import DONE, TASK, UCLOUD_BOOK, Item, Notebook, fmt_dt, parse_due
from .ops import Change, _same_due, similar
from .store import get_notebook, next_free_id

PREFIX = "ucloud:"


def item_text(todo: dict) -> str:
    """〔课程〕标题；平台给的类型不是作业时（测验、讨论…）也标出来。"""
    title = " ".join(str(todo.get("title") or "").split()) or "（无标题）"
    if todo.get("type") and todo["type"] != "作业":
        title = f"{todo['type']}：{title}"
    course = " ".join(str(todo.get("course") or "").split())
    return f"〔{course}〕{title}" if course else title


def _due(todo: dict) -> str | None:
    try:
        return parse_due(todo.get("end_time") or None)
    except ValueError:
        return None


def sync(books: list[Notebook], archive: list[Notebook], todos: list[dict], now: datetime) -> list[Change]:
    """就地修改 books，返回改动说明（没有改动返回空列表）。"""
    stamp = fmt_dt(now)
    book = get_notebook(books, UCLOUD_BOOK)
    linked = {it.src: (nb, it) for nb in books for it in nb.items if it.src and it.src.startswith(PREFIX)}
    archived = {it.src for nb in archive for it in nb.items if it.src}
    used = {it.id for nb in books for it in nb.items}
    seen: set[str] = set()
    changes: list[Change] = []

    for todo in todos:
        src = f"{PREFIX}{todo.get('id')}"
        if not todo.get("id") or src in seen:
            continue
        seen.add(src)
        text, due = item_text(todo), _due(todo)
        if src in linked:
            nb, item = linked[src]
            notes = []
            if item.text != text:
                notes.append(f"名称「{item.text}」→「{text}」")
                item.text = text
            if item.due != due:
                notes.append(f"截止 {(item.due or '无').replace('T', ' ')} → {(due or '无').replace('T', ' ')}")
                item.due = due
            if nb is not book:  # 被手动或 AI 移走了：放回云邮
                nb.items.remove(item)
                book.items.append(item)
                notes.append(f"从 [{nb.name}] 放回 [{UCLOUD_BOOK}]")
            if notes:
                changes.append(Change("update", f"{item.id}. {item.text}", "；".join(notes)))
            continue
        if src in archived:
            continue
        claimed = _claim(books, book, todo, due)
        if claimed:
            nb, item = claimed
            old = item.text
            nb.items.remove(item)
            book.items.append(item)
            item.src, item.text, item.due = src, text, due or item.due
            changes.append(Change("update", f"{item.id}. {item.text}", f"认领 [{nb.name}] 里的「{old}」，移进 [{UCLOUD_BOOK}]"))
            continue
        item = Item(id=next_free_id(used), text=text, due=due, created=stamp, src=src)
        used.add(item.id)
        book.items.append(item)
        changes.append(Change("add", f"{item.id}. {item.text}", f"截止 {due.replace('T', ' ')}" if due else ""))

    for src, (nb, item) in linked.items():
        if src not in seen and item.state != DONE:
            item.state, item.done_at = DONE, stamp
            changes.append(Change("done", f"{item.id}. {item.text}", "平台上已没有这条待办（已提交）"))
    return changes


def _claim(books: list[Notebook], book: Notebook, todo: dict, due: str | None) -> tuple[Notebook, Item] | None:
    """找手记的同一件事：没有来源编号的任务，名字相似（课程名可有可无）且截止同日。"""
    title = str(todo.get("title") or "")
    for nb in books:
        if nb is book:
            continue
        for item in nb.items:
            if item.kind == TASK and not item.src and similar(item.text, title) and _same_due(item.due, due):
                return nb, item
    return None

