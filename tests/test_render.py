from datetime import datetime

from jk.theme import make_console

from jk.model import DOING, DONE, NOTE, Item, Notebook
from jk.render import due_text, render_list, sort_key

NOW = datetime(2026, 10, 13, 18, 0)


def test_due_text_variants():
    assert str(due_text(Item(1, "x", due="2026-10-14T15:00"), NOW)) == "明天 15:00 · 还剩 21小时"
    assert str(due_text(Item(1, "x", due="2026-10-12"), NOW)) == "昨天 · 已逾期 18小时"
    assert str(due_text(Item(1, "x", due="2026-10-16"), NOW)).startswith("周五")
    assert str(due_text(Item(1, "x", due="2026-10-14", state=DONE), NOW)) == "明天"
    assert str(due_text(Item(1, "x"), NOW)) == ""


def test_sort_order():
    items = [
        Item(1, "done", state=DONE, done_at="2026-10-13T09:00"),
        Item(2, "note", kind=NOTE),
        Item(3, "plain"),
        Item(4, "urgent", pri=3),
        Item(5, "soon", due="2026-10-14"),
        Item(6, "doing", state=DOING),
    ]
    assert [i.text for i in sorted(items, key=sort_key)] == ["urgent", "doing", "soon", "plain", "note", "done"]


def test_render_list_output():
    console = make_console(record=True, width=80)
    render_list(console, [Notebook("作业", [Item(2, "作业 a", due="2026-10-14T15:00", pri=2), Item(1, "数值", state=DONE)])], NOW)
    out = console.export_text()
    assert "作业 [1/2]" in out and "2. ☐ 作业 a !" in out and "50% 完成" in out


def test_render_empty_hint():
    console = make_console(record=True, width=80)
    render_list(console, [], NOW)
    assert "jk a" in console.export_text()
