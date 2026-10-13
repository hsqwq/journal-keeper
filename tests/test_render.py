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


def test_recur_group_on_top_with_next_time():
    from jk.model import RECUR

    console = make_console(record=True, width=100)
    books = [
        Notebook("作业", [Item(2, "作业 a")]),
        Notebook("周期", [
            Item(7, "上数值分析课", kind=RECUR, every="weekly:2,4@16:00"),
            Item(6, "跑步", kind=RECUR, every="weekly:1@08:00"),
            Item(8, "喝水", kind=RECUR, every="daily"),
        ]),
    ]
    render_list(console, books, NOW)  # NOW = 周二 18:00
    out = console.export_text()
    assert out.index("周期 [3 项]") < out.index("作业 [0/1]")
    assert "↻ 上数值分析课" in out and "每周二、四 16:00 · 下次 后天 16:00（还剩 46小时）" in out
    assert "每周一 08:00 · 下次 周一 08:00（还剩 5天）" in out
    assert "每天 · 下次 今天" in out
    assert out.index("喝水") < out.index("上数值分析课") < out.index("跑步")  # 按下次时间排序
    assert "0% 完成" in out and "3 周期" in out


def _ends(out: str, needles: list[str]) -> set[int]:
    from rich.cells import cell_len

    ends = set()
    for line in out.splitlines():
        for n in needles:
            if line.rstrip().endswith(n):
                ends.add(cell_len(line.rstrip()))
    return ends


def test_times_right_aligned_across_notebooks():
    from jk.model import RECUR

    console = make_console(record=True, width=100)
    books = [
        Notebook("周期", [Item(13, "开组会", kind=RECUR, every="weekly:3@08:00")]),
        Notebook("作业", [Item(4, "大数据与信息技术伦理案例", due="2026-10-26T17:00"), Item(1, "交作业 a", state=DONE, due="2026-10-14T15:00")]),
        Notebook("运动", [Item(12, "室内体育测试", due="2026-10-24T08:00")]),
    ]
    render_list(console, books, NOW)
    out = console.export_text()
    ends = _ends(out, ["小时）", "还剩 13天", "15:00", "还剩 10天"])
    assert len(ends) == 1  # 所有时间的右边缘在同一列
    longest = next(line for line in out.splitlines() if "大数据" in line)
    assert longest.split("大数据与信息技术伦理案例")[1].startswith(" " * 4)  # 最长一条和时间之间也至少隔 GAP 格


def test_narrow_terminal_keeps_icons():
    from jk.model import RECUR

    console = make_console(record=True, width=50)
    render_list(console, [Notebook("周期", [Item(13, "开组会", kind=RECUR, every="weekly:3@08:00")])], NOW)
    out = console.export_text()
    assert "13. ↻ 开组会" in out
    assert all(len(line) <= 50 for line in out.splitlines())
