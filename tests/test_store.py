from jk.model import Item, Notebook, parse_item, parse_notebook, DOING, DONE, NOTE
from jk.store import find_item


def test_item_roundtrip():
    it = Item(id=2, text="完成作业 a", due="2026-10-14T15:00", pri=2, created="2026-10-13T10:00")
    back = parse_item(it.to_line())
    assert back == it


def test_parse_states_and_note():
    assert parse_item("- [/] 写报告 <!-- jk id=3 -->").state == DOING
    assert parse_item("- [x] 写报告 <!-- jk id=3 -->").state == DONE
    note = parse_item("- 一个想法 <!-- jk id=4 -->")
    assert note.kind == NOTE and note.text == "一个想法"


def test_bad_due_is_dropped_not_crash():
    assert parse_item("- [ ] x <!-- jk id=1 due=garbage -->").due is None


def test_text_cannot_break_comment():
    it = Item(id=1, text="a <!-- b --> c")
    assert parse_item(it.to_line()).text == "a <!- b -> c"


def test_unknown_lines_preserved():
    nb = parse_notebook("---\ntitle: 作业\n---\n# 作业\n\n随便写的一段话\n- [ ] x <!-- jk id=1 -->\n", "f")
    assert nb.extra == ["随便写的一段话"]
    assert "随便写的一段话" in nb.to_markdown()


def test_load_assigns_ids_to_handwritten_items(store):
    store.notebooks_dir.mkdir(parents=True)
    (store.notebooks_dir / "手写.md").write_text(
        "- [ ] 手写任务\n- [x] 已做 <!-- jk id=1 -->\n- 重复编号 <!-- jk id=1 -->\n", encoding="utf-8"
    )
    books = store.load()
    ids = sorted(it.id for it in books[0].items)
    assert ids == [1, 2, 3]
    _, done = find_item(books, 1)
    assert done.done_at  # 手写 [x] 自动补完成时间
    assert all(it.created for it in books[0].items)
    # 修复后已落盘，再读一次结果不变
    assert sorted(it.id for it in store.load()[0].items) == ids


def test_save_removes_empty_and_renamed(store):
    a = Notebook(name="作业", items=[Item(id=1, text="x")])
    b = Notebook(name="空", items=[])
    store.save([a, b])
    assert [p.name for p in store.notebooks_dir.iterdir()] == ["作业.md"]
    a.name = "课程作业"
    store.save([a])
    assert [p.name for p in store.notebooks_dir.iterdir()] == ["课程作业.md"]
