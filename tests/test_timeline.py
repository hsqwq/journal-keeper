from datetime import datetime

from rich.console import Console

from jk.model import DONE, NOTE, Item, Notebook
from jk.timeline import render_timeline

NOW = datetime(2026, 10, 13, 18, 0)


def output(books, archive, days=7):
    console = Console(record=True, width=100)
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
