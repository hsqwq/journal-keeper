import json

import pytest

from jk import migrate, model
from jk.model import Item, Notebook

V = model.FORMAT_VERSION


def test_fresh_home_gets_version(tmp_path):
    assert migrate.ensure(tmp_path) == []
    assert json.loads((tmp_path / "jk.json").read_text()) == {"format": V}


def test_newer_data_refused(store):
    store.save([Notebook("作业", [Item(1, "x")])])
    path = store.notebooks_dir / "作业.md"
    path.write_text(path.read_text().replace(f"jk_format: {V}", "jk_format: 99"))
    with pytest.raises(migrate.FormatError, match="v99"):
        migrate.ensure(store.home)


def test_upgrade_backs_up_then_migrates(store, monkeypatch):
    store.save([Notebook("作业", [Item(1, "x")])])
    migrate.write_version(store.home, V)
    (store.home / "history" / "snap").mkdir(parents=True)

    def step(home):
        for path in (home / "notebooks").glob("*.md"):
            path.write_text(path.read_text().replace(f"jk_format: {V}", f"jk_format: {V + 1}"))

    monkeypatch.setattr(model, "FORMAT_VERSION", V + 1)
    monkeypatch.setattr(migrate, "MIGRATIONS", {V: step})
    msgs = migrate.ensure(store.home)
    assert f"v{V} → v{V + 1}" in msgs[0]
    assert migrate.read_version(store.home) == V + 1
    backup = next((store.home / "backups").iterdir())
    assert f"jk_format: {V}" in (backup / "notebooks" / "作业.md").read_text()
    assert (backup / "history" / "snap").is_dir() and not (store.home / "history").exists()
    assert f"jk_format: {V + 1}" in (store.notebooks_dir / "作业.md").read_text()
    assert migrate.ensure(store.home) == []  # 幂等


def test_missing_migration_stops(store, monkeypatch):
    migrate.write_version(store.home, V)
    (store.home / "history" / "snap").mkdir(parents=True)
    monkeypatch.setattr(model, "FORMAT_VERSION", V + 1)
    monkeypatch.setattr(migrate, "MIGRATIONS", {})
    with pytest.raises(migrate.FormatError, match="缺少"):
        migrate.ensure(store.home)
    assert migrate.read_version(store.home) == V
    assert (store.home / "history" / "snap").is_dir() and not (store.home / "backups").exists()


def test_corrupt_version_file(tmp_path):
    (tmp_path / "jk.json").write_text("{bad")
    with pytest.raises(migrate.FormatError, match="损坏"):
        migrate.ensure(tmp_path)


# ---------- 真实的 v1 → v2 ----------

V1_NOTEBOOK = """---
jk_format: 1
title: 作业
created: 2026-10-12
---

# 作业

- [ ] 作业 a <!-- jk id=2 due=2026-10-14T15:00 pri=2 created=2026-10-13T10:00 -->
- [x] 数值分析作业 <!-- jk id=1 created=2026-10-12T10:00 done=2026-10-13T09:00 -->
- 一个想法 <!-- jk id=3 created=2026-10-13T11:00 -->

手写的一段话
"""


def test_real_v1_data_upgrades_without_loss(store):
    store.notebooks_dir.mkdir(parents=True)
    (store.notebooks_dir / "作业.md").write_text(V1_NOTEBOOK, encoding="utf-8")
    store.archive_dir.mkdir(parents=True)
    (store.archive_dir / "作业.md").write_text(V1_NOTEBOOK, encoding="utf-8")
    migrate.write_version(store.home, 1)
    msgs = migrate.ensure(store.home)
    assert "v1 → v2" in msgs[0]
    text = (store.notebooks_dir / "作业.md").read_text()
    assert "jk_format: 2" in text and "手写的一段话" in text
    books = store.load()
    items = {it.id: it for it in books[0].items}
    assert items[2].due == "2026-10-14T15:00" and items[2].pri == 2
    assert items[1].done_at == "2026-10-13T09:00" and items[3].kind == "note"
    assert "jk_format: 2" in (store.archive_dir / "作业.md").read_text()
    backup = next((store.home / "backups").iterdir())
    assert (backup / "notebooks" / "作业.md").read_text() == V1_NOTEBOOK


def test_v1_data_without_version_file(store):
    """早期没有 jk.json 的数据：按文件头里的 v1 识别并升级。"""
    store.notebooks_dir.mkdir(parents=True)
    (store.notebooks_dir / "作业.md").write_text(V1_NOTEBOOK, encoding="utf-8")
    assert "v1 → v2" in migrate.ensure(store.home)[0]
