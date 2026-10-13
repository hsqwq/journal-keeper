from datetime import datetime

import pytest

from jk.model import DONE, NOTE, Item, Notebook
from jk.ops import dedupe, similar, skipped_changes, validate, validate_skipped

NOW = datetime(2026, 10, 13, 18, 0)


@pytest.mark.parametrize("a,b", [
    ("提交实验报告三", "提交实验报告三"),
    ("交作业 a", "交作业a"),
    ("交作业Ａ", "交作业a"),  # 全角
    ("预约导师面谈", "预约导师面谈。"),
    ("完成英语阅读作业", "完成英语阅读的作业"),
])
def test_similar_hits(a, b):
    assert similar(a, b)


@pytest.mark.parametrize("a,b", [
    ("交数值分析作业 4", "交数值分析作业 5"),  # 数字不同
    ("完成作业 a", "完成作业 b"),
    ("交实验报告", "预约导师面谈"),
    ("", "x"),
])
def test_similar_misses(a, b):
    assert not similar(a, b)


def books():
    return [Notebook("作业", [
        Item(1, "提交实验报告三", due="2026-10-16T18:00"),
        Item(2, "交周报", due="2026-10-13"),
        Item(3, "图书馆周六不开门", kind=NOTE),
    ])]


def archive():
    return [Notebook("作业", [
        Item(9, "交数值分析作业 3", state=DONE, due="2026-10-10", done_at="2026-10-10T20:00"),
        Item(8, "很久以前的事", state=DONE, done_at="2026-08-01T20:00"),
    ])]


def run(ops):
    bs = books()
    return dedupe(validate(ops, bs), bs, archive(), NOW)


def add(text, **kw):
    return {"op": "add", "notebook": "作业", "text": text, **kw}


def test_duplicate_of_active_item_skipped():
    kept, skipped = run([add("提交实验报告三", due="2026-10-16"), add("交实验报告四")])
    assert [op["text"] for op in kept] == ["交实验报告四"]
    assert skipped[0].kind == "dup" and skipped[0].text == "1. 提交实验报告三"


def test_different_due_is_not_duplicate():
    kept, skipped = run([add("交周报", due="2026-10-20")])
    assert len(kept) == 1 and skipped == []


def test_duplicate_of_recent_archive_skipped_but_old_archive_ignored():
    kept, skipped = run([add("交数值分析作业 3"), add("很久以前的事")])
    assert [op["text"] for op in kept] == ["很久以前的事"]
    assert "已于 2026-10-10 完成" in skipped[0].detail


def test_duplicate_within_same_batch():
    kept, skipped = run([add("买牛奶"), add("买牛奶。")])
    assert len(kept) == 1 and "同一次" in skipped[0].detail


def test_note_and_task_not_mixed_and_allow_duplicate():
    kept, _ = run([add("图书馆周六不开门")])  # 已有的是笔记，这是任务
    assert len(kept) == 1
    kept, skipped = run([add("提交实验报告三", allow_duplicate=True)])
    assert len(kept) == 1 and skipped == []


def test_updates_pass_through():
    kept, skipped = run([{"op": "update", "id": 1, "due": "2026-10-17"}])
    assert kept[0]["op"] == "update" and skipped == []


def test_ai_skipped_validation_and_display():
    raw = [{"id": 1, "reason": "已经记过了"}, {"id": 99}, {"id": "x"}, "bad", {"id": 1}]
    clean = validate_skipped(raw, books())
    assert clean == [{"id": 1, "reason": "已经记过了"}]
    ch = skipped_changes(clean, books())
    assert ch[0].text == "1. 提交实验报告三" and ch[0].detail == "已经记过了"
    assert validate_skipped("nope", books()) == []
