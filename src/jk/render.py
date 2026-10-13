"""终端渲染：列表视图与时间描述。"""

from __future__ import annotations

from datetime import date, datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .model import DOING, DONE, NOTE, Item, Notebook, due_datetime

WEEKDAYS = "一二三四五六日"
ICONS = {"todo": ("☐", "magenta"), DOING: ("…", "yellow"), DONE: ("✔", "green"), NOTE: ("●", "blue")}
PRI_MARK = {2: ("!", "yellow"), 3: ("!!", "bold red")}


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
        return Text(label, style="dim")
    left = int((when - now).total_seconds() // 60)
    if left < 0:
        return Text(f"{label} · 已逾期 {span(left)}", style="bold red")
    style = "yellow" if left < 24 * 60 else "cyan"
    return Text(f"{label} · 还剩 {span(left)}", style=style)


def sort_key(item: Item) -> tuple:
    """未完成任务（进行中优先、优先级高优先、截止早优先）→ 笔记 → 已完成。"""
    if item.kind == NOTE:
        return (1, 0, "", item.id)
    if item.state == DONE:
        return (2, 0, item.done_at or "", item.id)
    due = due_datetime(item.due).isoformat() if item.due else "9999"
    return (0, -item.pri - (item.state == DOING), due, item.id)


def item_row(item: Item, now: datetime) -> tuple[Text, Text, Text, Text]:
    key = NOTE if item.kind == NOTE else item.state
    icon, color = ICONS[key]
    num = Text(f"{item.id}.", style="dim")
    body = Text(item.text)
    if item.state == DONE and item.kind != NOTE:
        body.stylize("dim strike")
    elif item.pri in PRI_MARK:
        mark, style = PRI_MARK[item.pri]
        body.stylize("bold")
        body.append(f" {mark}", style=style)
    if item.state == DOING and item.kind != NOTE:
        body.append(" 进行中", style="yellow")
    return num, Text(icon, style=color), body, due_text(item, now)


def notebook_header(nb: Notebook) -> Text:
    tasks = [i for i in nb.items if i.kind != NOTE]
    title = Text(f"  {nb.name}", style="bold underline")
    if tasks:
        done = sum(i.state == DONE for i in tasks)
        title.append(f" [{done}/{len(tasks)}]", style="dim")
    else:
        title.append(" [笔记]", style="dim")
    return title


def render_list(console: Console, books: list[Notebook], now: datetime | None = None) -> None:
    now = now or datetime.now()
    books = [nb for nb in books if nb.items]
    if not books:
        console.print("\n  [dim]还没有内容。试试：[/]jk a 明天下午三点前交作业 a\n")
        return
    console.print()
    for nb in books:
        console.print(notebook_header(nb))
        grid = Table.grid(padding=(0, 1))
        grid.add_column(justify="right", min_width=5)
        grid.add_column()
        grid.add_column(overflow="fold")
        grid.add_column(justify="right", no_wrap=True)
        for item in sorted(nb.items, key=sort_key):
            grid.add_row(*item_row(item, now))
        console.print(grid)
        console.print()
    console.print(summary(books))
    console.print()


def summary(books: list[Notebook]) -> Text:
    items = [i for nb in books for i in nb.items]
    tasks = [i for i in items if i.kind != NOTE]
    done = sum(i.state == DONE for i in tasks)
    doing = sum(i.state == DOING for i in tasks)
    notes = len(items) - len(tasks)
    pct = round(done * 100 / len(tasks)) if tasks else 0
    line = Text(f"  {pct}% 完成", style="bold")
    for count, label, style in (
        (done, "完成", "green"),
        (doing, "进行中", "yellow"),
        (len(tasks) - done - doing, "待办", "magenta"),
        (notes, "笔记", "blue"),
    ):
        line.append(" · ", style="dim")
        line.append(str(count), style=style)
        line.append(f" {label}", style="dim")
    return line
