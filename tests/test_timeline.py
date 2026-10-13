from datetime import datetime

from jk.theme import make_console

from jk.model import DONE, NOTE, Item, Notebook
from jk.timeline import render_timeline

NOW = datetime(2026, 10, 13, 18, 0)


def output(books, archive, days=7):
    console = make_console(record=True, width=100)
    render_timeline(console, books, archive, days, NOW)
    return console.export_text()


def test_review_and_upcoming():
    books = [Notebook("作业", [
        Item(1, "作业 a", due="2026-10-14T15:00", created="2026-10-13T10:00"),
        Item(2, "交报销单", due="2026-10-12", created="2026-10-01T10:00"),
        Item(3, "想法", kind=NOTE, created="2026-10-12T09:00"),
    ])]
    archive = [Notebook("作业", [Item(9, "数值作业", state=DONE, created="2026-10-10T08:00", done_at="2026-10-12T20:00")])]
    out = output(books, archive)
    assert "10-13 周二 今天" in out and "＋ 新建" in out and "作业 a  [作业]" in out
    assert "✔ 完成" in out and "数值作业" in out and "● 记录" in out
    assert out.index("10-13 周二 今天") < out.index("10-12 周一 昨天")  # 回顾倒序
    assert "⚠ 已逾期" in out and "交报销单" in out
    assert out.index("已逾期") < out.index("10-14 周三 明天")  # 前瞻顺序
    assert "交报销单" not in out.split("即将到期")[0]  # 10-01 新建，超出 7 天不在回顾里


def test_empty():
    out = output([], [])
    assert "这几天没有记录" in out and "没有带截止时间" in out


def test_recur_expanded_in_upcoming():
    from jk.model import RECUR

    books = [
        Notebook("周期", [
            Item(6, "跑步", kind=RECUR, every="weekly:1@08:00"),
            Item(7, "上课", kind=RECUR, every="weekly:2,4@16:00"),
            Item(8, "喝水", kind=RECUR, every="daily"),
        ]),
        Notebook("作业", [Item(2, "交报销单", due="2026-10-12")]),
    ]
    out = output(books, [], days=7)  # 周二 18:00 起 7 天：到下周一
    upcoming = out.split("即将到期")[1]
    assert upcoming.count("↻ 上课") == 1  # 本周四；今天 16:00 已过，下周二超出窗口
    assert upcoming.count("↻ 跑步") == 1 and "08:00" in upcoming
    assert upcoming.count("↻ 喝水") == 7 and "全天" in upcoming
    overdue = upcoming.split("⚠ 已逾期")[1].split("10-13")[0]
    assert "交报销单" in overdue and "喝水" not in overdue  # 今天的全天周期不算逾期


def test_recur_row_only_icon_is_colored():
    from jk.model import RECUR
    from jk.theme import THEME

    console = make_console(record=True, width=100)
    render_timeline(console, [Notebook("周期", [Item(6, "跑步", kind=RECUR, every="daily")])], [], 1, NOW)
    html = console.export_html(inline_styles=True)
    orange = THEME.styles["jk.recur"].color.triplet.hex
    # 橙色只出现在 ↻ 上，「跑步」不应该被染成橙色
    assert f'color: {orange}' in html
    import re

    orange_spans = re.findall(rf'<span style="[^"]*{orange}[^"]*">([^<]*)</span>', html)
    assert orange_spans and all("跑步" not in text for text in orange_spans)
