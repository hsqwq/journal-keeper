"""终端渲染：列表视图与时间描述。"""

from __future__ import annotations

from datetime import date, datetime

from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from .model import DOING, DONE, NOTE, PROGRAM_BOOKS, RECUR, RECUR_BOOK, Item, Notebook, due_datetime
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


def recur_text(item: Item, now: datetime) -> Text:
    """每周一 08:00 · 下次 周一。钟点已经在规则里，「下次」只写哪一天，保持短小、不挤占内容列。"""
    rule = parse_rule(item.every)
    text = Text(describe(rule), style="jk.muted")
    nxt = next_occurrence(rule, now)
    if nxt is None:
        return text
    text.append(" · 下次 ", style="jk.muted")
    soon = (nxt - now).total_seconds() < 24 * 3600 if rule.at else nxt.date() == now.date()
    text.append(day_label(nxt.date(), now.date()), style="jk.soon" if soon else "jk.later")
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


def render_groups(console: Console, groups: list[tuple[Text, list[tuple]]]) -> None:
    """画若干分组（标题 + 条目行），所有分组共用列宽，右侧时间对齐。行 = (编号, 图标, 内容, 时间)。"""
    rows = [r for _, group in groups for r in group]
    num_w = max(max(cell_len(r[0].plain) for r in rows) + 2, 5)  # 左边留 2 格缩进，和分组标题对齐
    # 固定宽度：编号列 + 图标 1 格 + 编号↔图标、图标↔内容两处列间空格
    widths = column_widths(console, rows, 2, 3, num_w + 1 + 2)
    console.print()
    for header, group in groups:
        console.print(header)
        grid = make_grid(widths, [{"justify": "right", "width": num_w}, {"width": 1}])
        for num, icon, body, when in group:
            grid.add_row(num, icon, body, "", when)
        console.print(grid)
        console.print()


def sorted_items(nb: Notebook, now: datetime) -> list[Item]:
    if nb.name == RECUR_BOOK:
        return sorted(nb.items, key=lambda i: recur_key(i, now))
    return sorted(nb.items, key=sort_key)


def book_order(nb: Notebook) -> int:
    """周期、云邮放最上面，其余保持原顺序（sorted 是稳定排序）。"""
    return PROGRAM_BOOKS.index(nb.name) if nb.name in PROGRAM_BOOKS else len(PROGRAM_BOOKS)


def render_list(console: Console, books: list[Notebook], now: datetime | None = None) -> None:
    now = now or datetime.now()
    books = sorted((nb for nb in books if nb.items), key=book_order)
    if not books:
        console.print("\n  [jk.muted]还没有内容。试试：[/]jk a 明天下午三点前交作业 a\n")
        return
    render_groups(console, [(notebook_header(nb), [item_row(it, now) for it in sorted_items(nb, now)]) for nb in books])
    console.print(summary(books))
    console.print()


def matches_words(text: str, words: list[str]) -> bool:
    """每个关键词都要出现（不分大小写）。"""
    low = text.lower()
    return all(w.lower() in low for w in words)


def render_search(console: Console, books: list[Notebook], archive: list[Notebook], words: list[str],
                  now: datetime | None = None) -> int:
    """在记事本和归档里找含全部关键词的条目，关键词高亮；返回找到的条数。"""
    now = now or datetime.now()

    def mark(body: Text) -> Text:
        body.highlight_words(words, style="jk.match", case_sensitive=False)
        return body

    groups = []
    for nb in sorted(books, key=book_order):
        hits = [it for it in sorted_items(nb, now) if matches_words(it.text, words)]
        if hits:
            header = Text(f"  {nb.name}", style="bold underline")
            header.append(f" [{len(hits)} 条]", style="jk.muted")
            rows = []
            for it in hits:
                num, icon, body, when = item_row(it, now)
                rows.append((num, icon, mark(body), when))
            groups.append((header, rows))
    archived = [(nb, it) for nb in archive for it in nb.items if matches_words(it.text, words)]
    archived.sort(key=lambda p: p[1].done_at or "", reverse=True)
    if archived:
        header = Text("  已归档", style="bold underline")
        header.append(f" [{len(archived)} 条]", style="jk.muted")
        rows = []
        for nb, it in archived:
            body = mark(Text(it.text, style="jk.muted"))
            body.append(f"  [{nb.name}]", style="jk.muted")
            done = it.done_at[:10] if it.done_at else ""
            when = Text(f"{day_label(date.fromisoformat(done), now.date())} 完成" if done else "", style="jk.muted")
            rows.append((Text(""), Text("✔", style="jk.done"), body, when))
        groups.append((header, rows))
    total = sum(len(rows) for _, rows in groups)
    if not total:
        console.print(f"\n  [jk.muted]没找到含「{escape(' '.join(words))}」的条目[/]\n")
        return 0
    render_groups(console, groups)
    console.print(Text(f"  找到 {total} 条", style="bold"))
    console.print()
    return total


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
