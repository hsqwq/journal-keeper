"""终端渲染：列表视图与时间描述。"""

from __future__ import annotations

from datetime import date, datetime

from rich.cells import cell_len
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .model import DOING, DONE, NOTE, RECUR, RECUR_BOOK, Item, Notebook, due_datetime
from .recur import describe, next_occurrence, parse_rule

WEEKDAYS = "一二三四五六日"
ICONS = {"todo": ("☐", "jk.todo"), DOING: ("…", "jk.doing"), DONE: ("✔", "jk.done"), NOTE: ("●", "jk.note"), RECUR: ("↻", "jk.recur")}
PRI_MARK = {2: ("!", "jk.pri2"), 3: ("!!", "jk.pri3")}


def day_label(d: date, today: date) -> str:
    delta = (d - today).days
    named = {-2: "前天", -1: "昨天", 0: "今天", 1: "明天", 2: "后天"}
    if delta in named:
        return named[delta]
    if 0 < delta < 7:
        return f"周{WEEKDAYS[d.weekday()]}"
    if d.year == today.year:
        return f"{d.month}月{d.day}日"
    return d.isoformat()


def span(minutes: int) -> str:
    minutes = abs(minutes)
    if minutes < 60:
        return f"{max(minutes, 1)}分钟"
    if minutes < 48 * 60:
        return f"{minutes // 60}小时"
    return f"{minutes // 1440}天"


def due_text(item: Item, now: datetime) -> Text:
    """例：明天 15:00 · 还剩 20小时 / 昨天 · 已逾期 2天。"""
    if not item.due:
        return Text("")
    when = due_datetime(item.due)
    label = day_label(when.date(), now.date())
    if len(item.due) > 10:
        label += when.strftime(" %H:%M")
    if item.state == DONE:
        return Text(label, style="jk.muted")
    left = int((when - now).total_seconds() // 60)
    if left < 0:
        return Text(f"{label} · 已逾期 {span(left)}", style="jk.overdue")
    style = "jk.soon" if left < 24 * 60 else "jk.later"
    return Text(f"{label} · 还剩 {span(left)}", style=style)


def when_text(moment: datetime, all_day: bool, now: datetime) -> str:
    """明天 16:00 / 周五 / 今天。"""
    label = day_label(moment.date(), now.date())
    return label if all_day else f"{label} {moment:%H:%M}"


def recur_text(item: Item, now: datetime) -> Text:
    """每周一 08:00 · 下次 周一 08:00（还剩 5天）。"""
    rule = parse_rule(item.every)
    text = Text(describe(rule), style="jk.muted")
    nxt = next_occurrence(rule, now)
    if nxt is None:
        return text
    text.append(" · 下次 ", style="jk.muted")
    if rule.at:
        left = int((nxt - now).total_seconds() // 60)
        style = "jk.soon" if left < 24 * 60 else "jk.later"
        text.append(f"{when_text(nxt, False, now)}（还剩 {span(left)}）", style=style)
    else:
        style = "jk.soon" if nxt.date() == now.date() else "jk.later"
        text.append(when_text(nxt, True, now), style=style)
    return text


def recur_key(item: Item, now: datetime) -> tuple:
    nxt = next_occurrence(parse_rule(item.every), now)
    return (nxt or datetime.max, item.id)


def sort_key(item: Item) -> tuple:
    """未完成任务（进行中优先、优先级高优先、截止早优先）→ 笔记 → 已完成。"""
    if item.kind == NOTE:
        return (1, 0, "", item.id)
    if item.state == DONE:
        return (2, 0, item.done_at or "", item.id)
    due = due_datetime(item.due).isoformat() if item.due else "9999"
    return (0, -item.pri - (item.state == DOING), due, item.id)


def item_row(item: Item, now: datetime) -> tuple[Text, Text, Text, Text]:
    key = item.kind if item.kind in (NOTE, RECUR) else item.state
    icon, color = ICONS[key]
    num = Text(f"{item.id}.", style="jk.muted")
    body = Text(item.text)
    if item.kind == RECUR:
        return num, Text(icon, style=color), body, recur_text(item, now)
    if item.state == DONE and item.is_task:
        body.stylize("jk.done_text")
    elif item.pri in PRI_MARK:
        mark, style = PRI_MARK[item.pri]
        body.stylize("bold")
        body.append(f" {mark}", style=style)
    if item.state == DOING and item.is_task:
        body.append(" 进行中", style="jk.doing")
    return num, Text(icon, style=color), body, due_text(item, now)


GAP = 4  # 内容和右侧时间之间至少空几格
MIN_TEXT = 16  # 终端再窄，内容列也至少留这么宽


def column_widths(console: Console, rows: list[tuple], text_col: int, time_col: int, fixed: int) -> tuple[int, int]:
    """所有分组共用的（内容宽, 时间宽）：时间统一贴右对齐，内容列按最长一条撑开。

    终端太窄时先让内容折行（最少 MIN_TEXT 格），还不够再让时间列折行。
    fixed = 除内容列、时间列和 GAP 以外占的宽度（缩进、编号、图标、列间空格）。
    """
    time_w = max((cell_len(r[time_col].plain) for r in rows), default=0)
    text_w = max((cell_len(r[text_col].plain) for r in rows), default=0)
    room = console.width - fixed - GAP
    text_w = min(text_w, max(MIN_TEXT, room - time_w))
    time_w = max(0, min(time_w, room - text_w))
    return text_w, time_w


def make_grid(widths: tuple[int, int], lead: list[dict]) -> Table:
    """lead = 内容列前面那几列的设置（编号、图标等）。"""
    text_w, time_w = widths
    grid = Table.grid(padding=(0, 1))
    for col in lead:
        grid.add_column(**col)
    grid.add_column(width=text_w, overflow="fold")
    grid.add_column(width=GAP - 2)  # 和左右的列间空格合起来正好 GAP 格
    grid.add_column(width=time_w, justify="right", overflow="fold")
    return grid


def notebook_header(nb: Notebook) -> Text:
    tasks = [i for i in nb.items if i.is_task]
    title = Text(f"  {nb.name}", style="bold underline")
    if nb.name == RECUR_BOOK:
        title.append(f" [{len(nb.items)} 项]", style="jk.muted")
    elif tasks:
        done = sum(i.state == DONE for i in tasks)
        title.append(f" [{done}/{len(tasks)}]", style="jk.muted")
    else:
        title.append(" [笔记]", style="jk.muted")
    return title


def render_list(console: Console, books: list[Notebook], now: datetime | None = None) -> None:
    now = now or datetime.now()
    books = sorted((nb for nb in books if nb.items), key=lambda nb: nb.name != RECUR_BOOK)  # 周期放最上面
    if not books:
        console.print("\n  [jk.muted]还没有内容。试试：[/]jk a 明天下午三点前交作业 a\n")
        return
    groups = []
    for nb in books:
        items = sorted(nb.items, key=lambda i: recur_key(i, now)) if nb.name == RECUR_BOOK else sorted(nb.items, key=sort_key)
        groups.append((nb, [item_row(item, now) for item in items]))
    num_w = max(cell_len(r[0].plain) for _, rows in groups for r in rows) + 2  # 左边留 2 格缩进，和分组标题对齐
    num_w = max(num_w, 5)
    # 固定宽度：编号列 + 图标 1 格 + 编号↔图标、图标↔内容两处列间空格
    widths = column_widths(console, [r for _, rows in groups for r in rows], 2, 3, num_w + 1 + 2)
    console.print()
    for nb, rows in groups:
        console.print(notebook_header(nb))
        grid = make_grid(widths, [{"justify": "right", "width": num_w}, {"width": 1}])
        for num, icon, body, when in rows:
            grid.add_row(num, icon, body, "", when)
        console.print(grid)
        console.print()
    console.print(summary(books))
    console.print()


def summary(books: list[Notebook]) -> Text:
    items = [i for nb in books for i in nb.items]
    tasks = [i for i in items if i.is_task]
    done = sum(i.state == DONE for i in tasks)
    doing = sum(i.state == DOING for i in tasks)
    notes = sum(i.kind == NOTE for i in items)
    recurs = sum(i.kind == RECUR for i in items)
    pct = round(done * 100 / len(tasks)) if tasks else 0
    line = Text(f"  {pct}% 完成", style="bold")
    for count, label, style in (
        (done, "完成", "jk.done"),
        (doing, "进行中", "jk.doing"),
        (len(tasks) - done - doing, "待办", "jk.todo"),
        (notes, "笔记", "jk.note"),
        (recurs, "周期", "jk.recur"),
    ):
        line.append(" · ", style="jk.muted")
        line.append(str(count), style=style)
        line.append(f" {label}", style="jk.muted")
    return line
