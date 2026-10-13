"""时间线：上半回顾最近几天新建/完成了什么，下半按截止日排出接下来要交的。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from .model import NOTE, Notebook, due_datetime
from .render import WEEKDAYS, day_label, due_text


def _day_title(d: date, today: date) -> Text:
    title = Text(f"  {d.month:02d}-{d.day:02d} 周{WEEKDAYS[d.weekday()]}", style="bold")
    if abs((d - today).days) <= 2:  # 前天 ~ 后天 额外标出
        title.append(f" {day_label(d, today)}", style="cyan")
    return title


def render_timeline(console: Console, books: list[Notebook], archive: list[Notebook], days: int = 7, now: datetime | None = None) -> None:
    now = now or datetime.now()
    today = now.date()
    since = (today - timedelta(days=days - 1)).isoformat()

    # ---------- 回顾 ----------
    events: dict[str, list[tuple[str, str, Text, str]]] = defaultdict(list)
    for source, archived in ((books, False), (archive, True)):
        for nb in source:
            for it in nb.items:
                num = "" if archived else f"{it.id}."
                if it.created and it.created[:10] >= since:
                    verb = Text("● 记录", style="blue") if it.kind == NOTE else Text("＋ 新建", style="cyan")
                    events[it.created[:10]].append((it.created[11:16], num, verb, f"{it.text}  [{nb.name}]"))
                if it.kind != NOTE and it.done_at and it.done_at[:10] >= since:
                    events[it.done_at[:10]].append((it.done_at[11:16], num, Text("✔ 完成", style="green"), f"{it.text}  [{nb.name}]"))

    console.print()
    console.print(Text(f"  回顾 · 最近 {days} 天", style="bold underline"))
    if not events:
        console.print("    [dim]这几天没有记录[/]")
    for day in sorted(events, reverse=True):
        console.print(_day_title(date.fromisoformat(day), today))
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="dim", min_width=6, justify="right")
        grid.add_column(style="dim", justify="right", min_width=3)
        grid.add_column()
        grid.add_column(overflow="fold")
        for clock, num, verb, text in sorted(events[day], key=lambda e: e[0]):
            grid.add_row(clock, num, verb, text)
        console.print(Padding(grid, (0, 0, 0, 3)))

    # ---------- 前瞻 ----------
    console.print()
    console.print(Text("  即将到期", style="bold underline"))
    upcoming = [(nb, it) for nb in books for it in nb.items if it.is_open and it.due]
    if not upcoming:
        console.print("    [dim]没有带截止时间的未完成任务[/]")
    groups: dict[str, list] = defaultdict(list)
    for nb, it in sorted(upcoming, key=lambda p: due_datetime(p[1].due)):
        when = due_datetime(it.due)
        key = "overdue" if when < now else when.date().isoformat()
        groups[key].append((nb, it))
    for key, pairs in groups.items():
        if key == "overdue":
            console.print(Text("  ⚠ 已逾期", style="bold red"))
        else:
            console.print(_day_title(date.fromisoformat(key), today))
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="dim", justify="right", min_width=6)
        grid.add_column(overflow="fold")
        grid.add_column(no_wrap=True)
        for nb, it in pairs:
            body = Text(it.text, style="bold" if it.pri > 1 else "")
            body.append(f"  [{nb.name}]", style="dim")
            grid.add_row(f"{it.id}.", body, due_text(it, now))
        console.print(Padding(grid, (0, 0, 0, 3)))
    console.print()
