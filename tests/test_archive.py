from datetime import date

from jk.archive import auto_archive
from jk.model import DONE, NOTE, Item, Notebook


def make(store):
    nb = Notebook(name="作业", items=[
        Item(id=1, text="昨天做完", state=DONE, done_at="2026-10-12T20:00"),
        Item(id=2, text="今天做完", state=DONE, done_at="2026-10-13T09:00"),
        Item(id=3, text="没做完"),
        Item(id=4, text="笔记", kind=NOTE),
    ])
    store.save([nb])
    return store.load()


def test_archive_next_day(store):
    books = make(store)
    assert auto_archive(store, books, 1, today=date(2026, 10, 13)) == 1
    assert [it.id for it in store.load()[0].items] == [2, 3, 4]
    arch = store.load_archive()
    assert arch[0].name == "作业" and arch[0].items[0].text == "昨天做完"
    # 再跑一次不会重复归档
    assert auto_archive(store, store.load(), 1, today=date(2026, 10, 13)) == 0


def test_archive_appends_and_can_be_disabled(store):
    books = make(store)
    assert auto_archive(store, books, 0, today=date(2026, 10, 20)) == 0
    auto_archive(store, books, 1, today=date(2026, 10, 13))
    auto_archive(store, store.load(), 1, today=date(2026, 10, 14))
    assert [it.text for it in store.load_archive()[0].items] == ["昨天做完", "今天做完"]
