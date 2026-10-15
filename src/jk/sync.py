"""jk u：把教学云平台的待办同步进「云邮」记事本。不走 AI，按平台编号（src=ucloud:<id>）对应。

规则：
- 平台上有、jk 里没有 → 新增；第一次同步时，其他记事本里手记的同一件事（名字相似、截止同日）会被认领并移进「云邮」。
- 平台上有、jk 里有 → 名字或截止变了就更新；完成状态以平台为准：jk 里标了完成但平台上还挂着，改回未完成。
- jk 里有、平台上没了 → 平台上消失只会是已提交，自动标完成。
- 已归档的（包括手记后归档的同一件事）平台上还挂着 → 从归档拿回「云邮」，改回未完成（编号会重新分配）。
"""

from __future__ import annotations

from datetime import datetime

from .model import DONE, TASK, TODO, UCLOUD_BOOK, Item, Notebook, fmt_dt, parse_due
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
    """就地修改 books 和 archive，返回改动说明（没有改动返回空列表）。"""
    stamp = fmt_dt(now)
    book = get_notebook(books, UCLOUD_BOOK)
    linked = {it.src: (nb, it) for nb in books for it in nb.items if it.src and it.src.startswith(PREFIX)}
    archived = {it.src: (nb, it) for nb in archive for it in nb.items if it.src and it.src.startswith(PREFIX)}
    used = {it.id for nb in books for it in nb.items}
    seen: set[str] = set()
    changes: list[Change] = []

    for todo in todos:
        src = f"{PREFIX}{todo.get('id')}"
        if not todo.get("id") or src in seen:
            continue
        seen.add(src)
        text, due = item_text(todo), _due(todo)
        notes: list[str] = []
        if src in linked:
            nb, item = linked[src]
        else:
            hit = archived.get(src) or _claim_in(archive, None, todo, due)
            if hit:  # 已归档：平台上还挂着说明没提交，拿回来
                nb, item = hit
                nb.items.remove(item)
                item.id = next_free_id(used)  # 归档后编号可能已被别的条目用掉
                used.add(item.id)
                notes.append("从归档拿回")
            else:
                hit = _claim_in(books, book, todo, due)
                if not hit:
                    item = Item(id=next_free_id(used), text=text, due=due, created=stamp, src=src)
                    used.add(item.id)
                    book.items.append(item)
                    changes.append(Change("add", f"{item.id}. {item.text}", f"截止 {due.replace('T', ' ')}" if due else ""))
                    continue
                nb, item = hit
                notes.append(f"认领 [{nb.name}] 里的「{item.text}」")
            item.src = src
        if item.text != text:
            if src in linked:
                notes.append(f"名称「{item.text}」→「{text}」")
            item.text = text
        if due and item.due != due:
            notes.append(f"截止 {(item.due or '无').replace('T', ' ')} → {due.replace('T', ' ')}")
            item.due = due
        if nb is not book:  # 认领、从归档拿回、或被移走了：放进云邮
            if any(nb is b for b in books):  # 按身份比较：归档里可能有同名同内容的记事本
                nb.items.remove(item)
                if src in linked:
                    notes.append(f"从 [{nb.name}] 放回 [{UCLOUD_BOOK}]")
            book.items.append(item)
        if item.state == DONE:  # 完成状态以平台为准：平台上还挂着 = 没提交
            item.state, item.done_at = TODO, None
            changes.append(Change("undone", f"{item.id}. {item.text}", "；".join(["平台上还没提交", *notes])))
        elif notes:
            changes.append(Change("update", f"{item.id}. {item.text}", "；".join(notes)))

    for src, (nb, item) in linked.items():
        if src not in seen and item.state != DONE:
            item.state, item.done_at = DONE, stamp
            changes.append(Change("done", f"{item.id}. {item.text}", "平台上已没有这条待办（已提交）"))
    return changes


def _claim_in(books: list[Notebook], skip: Notebook | None, todo: dict, due: str | None) -> tuple[Notebook, Item] | None:
    """找手记的同一件事：没有来源编号的任务，名字相似（课程名可有可无）且截止同日。"""
    title = str(todo.get("title") or "")
    for nb in books:
        if nb is skip:
            continue
        for item in nb.items:
            if item.kind == TASK and not item.src and similar(item.text, title) and _same_due(item.due, due):
                return nb, item
    return None
