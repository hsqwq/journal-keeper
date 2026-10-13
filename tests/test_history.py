from jk import history
from jk.model import Item, Notebook


def test_undo_restores_previous_state(store):
    store.save([Notebook(name="作业", items=[Item(id=1, text="旧")])])
    history.snapshot(store, "改成新")
    store.save([Notebook(name="作业", items=[Item(id=1, text="新")]), Notebook(name="新本", items=[Item(id=2, text="y")])])
    assert history.undo(store) == "改成新"
    books = store.load()
    assert [(nb.name, nb.items[0].text) for nb in books] == [("作业", "旧")]
    assert history.undo(store) is None


def test_undo_from_empty_removes_created_files(store):
    history.snapshot(store, "首次添加")
    store.save([Notebook(name="作业", items=[Item(id=1, text="x")])])
    history.undo(store)
    assert store.load() == []


def test_prune_keeps_limit(store, monkeypatch):
    monkeypatch.setattr(history, "KEEP", 3)
    for i in range(5):
        history.snapshot(store, f"op{i}")
    labels = []
    while (label := history.undo(store)) is not None:
        labels.append(label)
    assert labels == ["op4", "op3", "op2"]
