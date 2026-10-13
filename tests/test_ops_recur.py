from datetime import datetime

import pytest

from jk.model import RECUR, Item, Notebook
from jk.ops import PlanError, apply, dedupe, validate
from jk.store import find_item


def books():
    return [
        Notebook("周期", [Item(1, "跑步", kind=RECUR, every="weekly:1@08:00")]),
        Notebook("作业", [Item(2, "作业 a")]),
    ]


def run(ops, bs=None):
    bs = bs or books()
    return bs, apply(validate(ops, bs), bs)


def test_add_recur_forced_into_recur_book():
    bs, ch = run([{"op": "add", "kind": "recur", "notebook": "课程", "text": "上数值分析课", "every": "weekly:4,2@16:00", "due": "2026-10-14"}])
    nb, item = find_item(bs, 3)
    assert nb.name == "周期" and item.every == "weekly:2,4@16:00" and item.due is None
    assert ch[0].detail == "[周期] 每周二、四 16:00"


def test_update_recur_rule_and_text():
    bs, ch = run([{"op": "update", "id": 1, "every": "weekdays@07:30", "text": "晨跑"}])
    item = find_item(bs, 1)[1]
    assert item.every == "weekdays@07:30" and item.text == "晨跑"
    assert "每周一 08:00 → 工作日 07:30" in ch[0].detail


@pytest.mark.parametrize("ops,msg", [
    ([{"op": "add", "kind": "recur", "text": "跑步"}], "every"),
    ([{"op": "add", "kind": "recur", "text": "跑步", "every": "yearly"}], "every"),
    ([{"op": "add", "kind": "habit", "text": "x", "notebook": "作业"}], "kind"),
    ([{"op": "add", "notebook": "周期", "text": "普通任务"}], "只放周期"),
    ([{"op": "update", "id": 1, "state": "done"}], "只能改 text 和 every"),
    ([{"op": "update", "id": 1, "due": "2026-10-14"}], "只能改 text 和 every"),
    ([{"op": "update", "id": 2, "every": "daily"}], "不是周期"),
    ([{"op": "update", "id": 2, "kind": "recur"}], "不能把任务"),
    ([{"op": "update", "id": 2, "notebook": "周期"}], "只放周期"),
    ([{"op": "rename_notebook", "from": "周期", "to": "习惯"}], "程序管理"),
    ([{"op": "rename_notebook", "from": "作业", "to": "周期"}], "程序管理"),
])
def test_recur_rules_enforced(ops, msg):
    with pytest.raises(PlanError, match=msg):
        validate(ops, books())


def test_delete_recur():
    bs, ch = run([{"op": "delete", "id": 1}])
    assert find_item(bs, 1) is None and ch[0].kind == "delete"


def test_dedupe_recur_same_rule_only():
    bs = books()
    same = validate([{"op": "add", "kind": "recur", "text": "跑步", "every": "weekly:1@8:00"}], bs)
    kept, skipped = dedupe(same, bs, [], datetime(2026, 10, 13))
    assert kept == [] and skipped[0].text == "1. 跑步"
    other = validate([{"op": "add", "kind": "recur", "text": "跑步", "every": "weekly:3@08:00"}], bs)
    kept, _ = dedupe(other, bs, [], datetime(2026, 10, 13))
    assert len(kept) == 1
