from datetime import datetime

from jk.model import DONE, NOTE, UCLOUD_BOOK, Item, Notebook
from jk.store import find_item
from jk.sync import item_text, sync

NOW = datetime(2026, 10, 15, 12, 0)


def todo(id, title, course="编译原理与技术", end="2026-10-31 23:59", type="作业"):
    return {"id": id, "title": title, "course": course, "end_time": end, "type": type}


def ucloud(books):
    return next(nb for nb in books if nb.name == UCLOUD_BOOK)


def test_item_text():
    assert item_text(todo("1", "第二次作业")) == "〔编译原理与技术〕第二次作业"
    assert item_text(todo("1", "期中测验", course="", type="测验")) == "测验：期中测验"
    assert item_text(todo("1", "  ")) == "〔编译原理与技术〕（无标题）"


def test_first_sync_adds_with_src_and_due():
    books = [Notebook("作业", [Item(1, "买猫粮")])]
    changes = sync(books, [], [todo("A", "第二次作业")], NOW)
    _, item = find_item(books, 2)
    assert item.src == "ucloud:A" and item.due == "2026-10-31T23:59" and item.created == "2026-10-15T12:00"
    assert ucloud(books).items == [item]
    assert changes[0].kind == "add" and "2026-10-31 23:59" in changes[0].detail


def test_second_sync_no_changes_and_updates():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    assert sync(books, [], [todo("A", "第二次作业")], NOW) == []
    changes = sync(books, [], [todo("A", "第二次作业（延期）", end="2026-11-02 23:59")], NOW)
    item = ucloud(books).items[0]
    assert item.text == "〔编译原理与技术〕第二次作业（延期）" and item.due == "2026-11-02T23:59"
    assert changes[0].kind == "update" and "截止 2026-10-31 23:59 → 2026-11-02 23:59" in changes[0].detail


def test_gone_from_platform_marks_done_once():
    books = []
    sync(books, [], [todo("A", "第二次作业"), todo("B", "第三次作业")], NOW)
    changes = sync(books, [], [todo("B", "第三次作业")], NOW)
    a = next(it for it in ucloud(books).items if it.src == "ucloud:A")
    assert a.state == DONE and a.done_at == "2026-10-15T12:00"
    assert [c.kind for c in changes] == ["done"] and "已提交" in changes[0].detail
    assert sync(books, [], [todo("B", "第三次作业")], NOW) == []


def test_locally_done_stays_done():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    item = ucloud(books).items[0]
    item.state, item.done_at = DONE, "2026-10-15T11:00"
    assert sync(books, [], [todo("A", "第二次作业")], NOW) == []
    assert item.state == DONE


def test_archived_not_readded():
    archive = [Notebook(UCLOUD_BOOK, [Item(3, "x", state=DONE, done_at="2026-10-13T10:00", src="ucloud:A")])]
    books = []
    assert sync(books, archive, [todo("A", "第二次作业")], NOW) == []


def test_claims_handwritten_item_keeps_id_and_state():
    books = [Notebook("作业", [
        Item(4, "第二次作业", due="2026-10-31T23:59", created="2026-10-10T09:00"),
        Item(5, "第三次作业——语法分析器", state=DONE, done_at="2026-10-14T20:00"),
        Item(6, "第二次作业", kind=NOTE),
    ])]
    changes = sync(books, [], [todo("A", "第二次作业"), todo("B", "第三次作业——语法分析器", end="2026-11-08 23:59")], NOW)
    nb, a = find_item(books, 4)
    assert nb.name == UCLOUD_BOOK and a.src == "ucloud:A" and a.created == "2026-10-10T09:00"
    nb, b = find_item(books, 5)
    assert nb.name == UCLOUD_BOOK and b.state == DONE and b.due == "2026-11-08T23:59"
    assert find_item(books, 6)[0].name == "作业"  # 笔记不认领
    assert all(c.kind == "update" and "认领" in c.detail for c in changes)


def test_claim_requires_same_day():
    books = [Notebook("作业", [Item(4, "第二次作业", due="2026-10-20")])]
    sync(books, [], [todo("A", "第二次作业")], NOW)
    assert find_item(books, 4)[0].name == "作业"


def test_moved_out_item_is_put_back():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    item = ucloud(books).items.pop()
    books.append(Notebook("作业", [item]))
    changes = sync(books, [], [todo("A", "第二次作业")], NOW)
    assert find_item(books, item.id)[0].name == UCLOUD_BOOK and "放回" in changes[0].detail


def test_bad_or_missing_fields():
    books = []
    changes = sync(books, [], [{"id": "", "title": "x"}, todo("C", "y", end="garbage"), todo("C", "dup")], NOW)
    assert len(changes) == 1 and ucloud(books).items[0].due is None
