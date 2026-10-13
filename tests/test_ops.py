import pytest

from jk.model import DONE, NOTE, Item, Notebook
from jk.ops import PlanError, apply, validate
from jk.store import find_item


def books():
    return [
        Notebook("作业", [Item(1, "数值分析作业"), Item(2, "作业 a", due="2026-10-14T15:00")]),
        Notebook("想法", [Item(3, "做个界面", kind=NOTE)]),
    ]


def run(ops, bs=None):
    bs = bs or books()
    return bs, apply(validate(ops, bs), bs)


def test_add_task_uses_smallest_free_id_and_new_notebook():
    bs, changes = run([{"op": "add", "notebook": "工作", "text": "交报销单", "due": "2026-10-15 09:00:30", "priority": 2}])
    nb, item = find_item(bs, 4)
    assert nb.name == "工作" and item.due == "2026-10-15T09:00" and item.pri == 2 and item.created
    assert changes[0].kind == "add" and "截止 2026-10-15 09:00" in changes[0].detail


def test_note_ignores_due():
    bs, _ = run([{"op": "add", "notebook": "想法", "kind": "note", "text": "x", "due": "2026-10-15"}])
    assert find_item(bs, 4)[1].due is None


def test_mark_done_and_undone():
    bs, ch = run([{"op": "update", "id": 2, "state": "done"}])
    item = find_item(bs, 2)[1]
    assert item.state == DONE and item.done_at and ch[0].kind == "done"
    _, ch = run([{"op": "update", "id": 2, "state": "todo"}], bs)
    assert item.done_at is None and ch[0].kind == "undone"


def test_update_fields_and_move():
    bs, ch = run([{"op": "update", "id": 1, "text": "数值作业", "due": None, "notebook": "课程"}])
    nb, item = find_item(bs, 1)
    assert nb.name == "课程" and item.text == "数值作业"
    assert "移到 [课程]" in ch[0].detail


def test_clear_due():
    bs, _ = run([{"op": "update", "id": 2, "due": None}])
    assert find_item(bs, 2)[1].due is None


def test_delete_and_rename_merge():
    bs, ch = run([{"op": "delete", "id": 3}, {"op": "rename_notebook", "from": "想法", "to": "作业"}])
    assert find_item(bs, 3) is None
    bs, ch = run([{"op": "rename_notebook", "from": "想法", "to": "作业"}])
    assert find_item(bs, 3)[0].name == "作业" and "合并" in ch[0].text


@pytest.mark.parametrize("ops,msg", [
    ([{"op": "update", "id": 9, "state": "done"}], "不存在"),
    ([{"op": "delete", "id": 1}, {"op": "delete", "id": 1}], "不存在"),
    ([{"op": "add", "notebook": "作业", "text": ""}], "不能为空"),
    ([{"op": "add", "notebook": "", "text": "x"}], "记事本名"),
    ([{"op": "add", "notebook": "作业", "text": "x", "due": "明天"}], "due"),
    ([{"op": "add", "notebook": "作业", "text": "x", "priority": 5}], "priority"),
    ([{"op": "update", "id": 1}], "没有要改"),
    ([{"op": "update", "id": 1, "state": "finished"}], "state"),
    ([{"op": "drop_table"}], "未知操作"),
    ("not a list", "数组"),
])
def test_invalid_plans_rejected(ops, msg):
    with pytest.raises(PlanError, match=msg):
        validate(ops, books())


def test_invalid_plan_changes_nothing():
    bs = books()
    with pytest.raises(PlanError):
        validate([{"op": "update", "id": 1, "state": "done"}, {"op": "delete", "id": 99}], bs)
    assert find_item(bs, 1)[1].state != DONE
