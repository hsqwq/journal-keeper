from datetime import datetime

from jk.model import DONE, NOTE, UCLOUD_BOOK, Item, Notebook
from jk.store import find_item
from jk.sync import item_text, sync

NOW = datetime(2026, 10, 15, 12, 0)


def todo(id, title, course="编译原理与技术", end="2026-10-31 23:59", type="作业"):
    return {"id": id, "title": title, "course": course, "end_time": end, "type": type}


def ucloud_book(books):
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
    assert ucloud_book(books).items == [item]
    assert changes[0].kind == "add" and "2026-10-31 23:59" in changes[0].detail


def test_second_sync_no_changes_and_updates():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    assert sync(books, [], [todo("A", "第二次作业")], NOW) == []
    changes = sync(books, [], [todo("A", "第二次作业（延期）", end="2026-11-02 23:59")], NOW)
    item = ucloud_book(books).items[0]
    assert item.text == "〔编译原理与技术〕第二次作业（延期）" and item.due == "2026-11-02T23:59"
    assert changes[0].kind == "update" and "截止 2026-10-31 23:59 → 2026-11-02 23:59" in changes[0].detail


def test_gone_from_platform_marks_done_once():
    books = []
    sync(books, [], [todo("A", "第二次作业"), todo("B", "第三次作业")], NOW)
    changes = sync(books, [], [todo("B", "第三次作业")], NOW)
    a = next(it for it in ucloud_book(books).items if it.src == "ucloud:A")
    assert a.state == DONE and a.done_at == "2026-10-15T12:00"
    assert [c.kind for c in changes] == ["done"] and "已提交" in changes[0].detail
    assert sync(books, [], [todo("B", "第三次作业")], NOW) == []


def test_locally_done_but_still_on_platform_is_reopened():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    item = ucloud_book(books).items[0]
    item.state, item.done_at = DONE, "2026-10-15T11:00"
    changes = sync(books, [], [todo("A", "第二次作业")], NOW)
    assert item.state == "todo" and item.done_at is None
    assert [c.kind for c in changes] == ["undone"] and "平台上还没提交" in changes[0].detail
    assert sync(books, [], [todo("A", "第二次作业")], NOW) == []


def test_archived_but_still_on_platform_comes_back_with_new_id():
    archive = [Notebook(UCLOUD_BOOK, [Item(3, "x", state=DONE, done_at="2026-10-13T10:00", src="ucloud:A")])]
    books = [Notebook("生活", [Item(3, "买猫粮")])]  # 编号 3 已经被别的条目用了
    changes = sync(books, archive, [todo("A", "第二次作业")], NOW)
    nb, item = find_item(books, 1)
    assert nb.name == UCLOUD_BOOK and item.src == "ucloud:A" and item.state == "todo"
    assert item.text == "〔编译原理与技术〕第二次作业" and archive[0].items == []
    assert changes[0].kind == "undone" and "从归档拿回" in changes[0].detail


def test_claims_handwritten_item_keeps_id_and_state():
    books = [Notebook("作业", [
        Item(4, "第二次作业", due="2026-10-31T23:59", created="2026-10-10T09:00"),
        Item(5, "第三次作业——语法分析器", state=DONE, done_at="2026-10-14T20:00"),
        Item(6, "第二次作业", kind=NOTE),
    ])]
    changes = sync(books, [], [todo("A", "第二次作业"), todo("B", "第三次作业——语法分析器", end="2026-11-08 23:59")], NOW)
    nb, a = find_item(books, 4)
    assert nb.name == UCLOUD_BOOK and a.src == "ucloud:A" and a.created == "2026-10-10T09:00"
    nb, b = find_item(books, 5)  # jk 里标了完成、平台上还挂着 → 认领并改回未完成
    assert nb.name == UCLOUD_BOOK and b.state == "todo" and b.due == "2026-11-08T23:59"
    assert find_item(books, 6)[0].name == "作业"  # 笔记不认领
    assert [c.kind for c in changes] == ["update", "undone"] and all("认领" in c.detail for c in changes)


def test_claim_requires_same_day():
    books = [Notebook("作业", [Item(4, "第二次作业", due="2026-10-20")])]
    sync(books, [], [todo("A", "第二次作业")], NOW)
    assert find_item(books, 4)[0].name == "作业"


def test_moved_out_item_is_put_back():
    books = []
    sync(books, [], [todo("A", "第二次作业")], NOW)
    item = ucloud_book(books).items.pop()
    books.append(Notebook("作业", [item]))
    changes = sync(books, [], [todo("A", "第二次作业")], NOW)
    assert find_item(books, item.id)[0].name == UCLOUD_BOOK and "放回" in changes[0].detail


def test_bad_or_missing_fields():
    books = []
    changes = sync(books, [], [{"id": "", "title": "x"}, todo("C", "y", end="garbage"), todo("C", "dup")], NOW)
    assert len(changes) == 1 and ucloud_book(books).items[0].due is None


# ---------- jk u 命令 ----------

import pytest  # noqa: E402

from jk import cli, ucloud  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    monkeypatch.setenv("UCLOUD_USERNAME", "2023000000")
    monkeypatch.setenv("UCLOUD_PASSWORD", "pw")
    return tmp_path


def fake_fetch(monkeypatch, todos):
    calls = []

    def fetch(user, pw):
        calls.append((user, pw))
        if isinstance(todos, Exception):
            raise todos
        return todos

    monkeypatch.setattr(ucloud, "fetch_todos", fetch)
    return calls


def test_jk_u_syncs_and_undo(home, monkeypatch, capsys):
    calls = fake_fetch(monkeypatch, [todo("A", "第二次作业")])
    assert cli.main(["u"]) == 0
    out = capsys.readouterr().out
    assert calls == [("2023000000", "pw")]
    assert "同步完成" in out and "＋ 新增 1. 〔编译原理与技术〕第二次作业" in out and "云邮 [0/1]" in out
    assert "src=ucloud:A" in (home / "notebooks" / "云邮.md").read_text()
    assert cli.main(["u"]) == 0
    assert "已是最新" in capsys.readouterr().out
    assert len(list((home / "history").iterdir())) == 1  # 没变化不拍快照
    assert cli.main(["undo"]) == 0
    assert not (home / "notebooks" / "云邮.md").exists()


def test_jk_u_errors(home, monkeypatch, capsys):
    fake_fetch(monkeypatch, ucloud.UcloudError("统一认证登录失败（HTTP 401）：密码错误"))
    assert cli.main(["u"]) == 1
    assert "密码错误" in capsys.readouterr().err
    monkeypatch.setenv("UCLOUD_PASSWORD", "")
    assert cli.main(["u"]) == 2
    assert "UCLOUD_PASSWORD" in capsys.readouterr().err


def test_ucloud_book_listed_after_recur(home, monkeypatch, capsys):
    from jk.model import RECUR
    from jk.store import Store

    Store(home).save([Notebook("作业", [Item(1, "x")]), Notebook("周期", [Item(2, "跑步", kind=RECUR, every="daily")])])
    fake_fetch(monkeypatch, [todo("A", "第二次作业")])
    cli.main(["u"])
    capsys.readouterr()
    cli.main([])
    out = capsys.readouterr().out
    assert out.index("周期") < out.index("云邮") < out.index("作业 [")


def test_archived_handwritten_done_is_claimed_back():
    archive = [Notebook("作业", [Item(2, "第二次作业——词法分析器实验", state=DONE,
                                     due="2026-10-31T23:59", done_at="2026-10-12T20:00")])]
    books = []
    changes = sync(books, archive, [todo("A", "第二次作业——词法分析器实验")], NOW)
    item = ucloud_book(books).items[0]
    assert item.src == "ucloud:A" and item.state == "todo" and archive[0].items == []
    assert [c.kind for c in changes] == ["undone"] and "从归档拿回" in changes[0].detail
    assert sync(books, archive, [todo("A", "第二次作业——词法分析器实验")], NOW) == []


def test_jk_c_on_ucloud_item_warns(home, monkeypatch, capsys):
    fake_fetch(monkeypatch, [todo("A", "第二次作业")])
    cli.main(["u"])
    capsys.readouterr()
    assert cli.main(["c", "1"]) == 0
    assert "下次 jk u 会改回未完成" in capsys.readouterr().out
    cli.main(["u"])
    assert "☐ 取消完成 1." in capsys.readouterr().out
