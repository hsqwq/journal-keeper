"""时间线：上半回顾最近几天新建/完成了什么，下半按截止日排出接下来要交的。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from .model import NOTE, RECUR, Notebook, due_datetime
from .recur import describe, occurrences, parse_rule
from rich.cells import cell_len

from .render import WEEKDAYS, column_widths, day_label, due_text, make_grid


def _day_title(d: date, today: date) -> Text:
    title = Text(f"  {d.month:02d}-{d.day:02d} 周{WEEKDAYS[d.weekday()]}", style="bold")
    if abs((d - today).days) <= 2:  # 前天 ~ 后天 额外标出
        title.append(f" {day_label(d, today)}", style="jk.later")
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
                    verb = Text("● 记录", style="jk.note") if it.kind == NOTE else Text("＋ 新建", style="jk.add")
                    events[it.created[:10]].append((it.created[11:16], num, verb, f"{it.text}  [{nb.name}]"))
                if it.kind != NOTE and it.done_at and it.done_at[:10] >= since:
                    events[it.done_at[:10]].append((it.done_at[11:16], num, Text("✔ 完成", style="jk.done"), f"{it.text}  [{nb.name}]"))

    console.print()
    console.print(Text(f"  回顾 · 最近 {days} 天", style="bold underline"))
    if not events:
        console.print("    [jk.muted]这几天没有记录[/]")
    for day in sorted(events, reverse=True):
        console.print(_day_title(date.fromisoformat(day), today))
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="jk.muted", min_width=6, justify="right")
        grid.add_column(style="jk.muted", justify="right", min_width=3)
        grid.add_column()
        grid.add_column(overflow="fold")
        for clock, num, verb, text in sorted(events[day], key=lambda e: e[0]):
            grid.add_row(clock, num, verb, text)
        console.print(Padding(grid, (0, 0, 0, 3)))

    # ---------- 前瞻 ----------
    # 带截止的未完成任务全部列出；周期条目展开成接下来 days 天里的每一次
    console.print()
    console.print(Text("  即将到期", style="bold underline"))
    entries: list[tuple[datetime, bool, Text, Text, Text]] = []  # (时刻, 已逾期, 编号, 内容, 时间)
    for nb in books:
        for it in nb.items:
            if it.is_open and it.due:
                body = Text(it.text, style="bold" if it.pri > 1 else "")
                body.append(f"  [{nb.name}]", style="jk.muted")
                when = due_datetime(it.due)
                entries.append((when, when < now, Text(f"{it.id}."), body, due_text(it, now)))
            elif it.kind == RECUR and it.every:
                rule = parse_rule(it.every)
                for moment in occurrences(rule, now, datetime.combine(today + timedelta(days=days - 1), datetime.max.time())):
                    body = Text("↻ ", style="jk.recur")
                    body.append(it.text)
                    body.append(f"  [{describe(rule)}]", style="jk.muted")
                    clock = Text(moment.strftime("%H:%M") if rule.at else "全天", style="jk.later")
                    entries.append((moment, False, Text(f"{it.id}."), body, clock))  # 周期只列将来，不会逾期
    if not entries:
        console.print("    [jk.muted]没有带截止时间的未完成任务[/]")
    groups: dict[str, list] = defaultdict(list)
    for entry in sorted(entries, key=lambda e: e[0]):
        groups["overdue" if entry[1] else entry[0].date().isoformat()].append(entry)
    all_rows = [(num, body, when) for rows in groups.values() for _, _, num, body, when in rows]
    num_w = max([cell_len(r[0].plain) for r in all_rows] + [3]) + 4  # 左边缩进 4 格，落在日期标题下面
    widths = column_widths(console, all_rows, 1, 2, num_w + 1)  # 编号列 + 编号↔内容的列间空格
    for key, rows in groups.items():
        if key == "overdue":
            console.print(Text("  ⚠ 已逾期", style="jk.overdue"))
        else:
            console.print(_day_title(date.fromisoformat(key), today))
        grid = make_grid(widths, [{"style": "jk.muted", "justify": "right", "width": num_w}])
        for _, _, num, body, when in rows:
            grid.add_row(num, body, "", when)
        console.print(grid)
    console.print()
