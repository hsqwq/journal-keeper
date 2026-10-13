import json

import pytest

from jk import migrate, model
from jk.model import Item, Notebook


def test_fresh_home_gets_version(tmp_path):
    assert migrate.ensure(tmp_path) == []
    assert json.loads((tmp_path / "jk.json").read_text()) == {"format": model.FORMAT_VERSION}


def test_newer_data_refused(tmp_path, store):
    store.save([Notebook("作业", [Item(1, "x")])])
    path = store.notebooks_dir / "作业.md"
    path.write_text(path.read_text().replace("jk_format: 1", "jk_format: 99"))
    with pytest.raises(migrate.FormatError, match="v99"):
        migrate.ensure(store.home)


def test_upgrade_backs_up_then_migrates(store, monkeypatch):
    store.save([Notebook("作业", [Item(1, "x")])])
    migrate.write_version(store.home, 1)
    (store.home / "history" / "snap").mkdir(parents=True)

    def v1_to_v2(home):
        for path in (home / "notebooks").glob("*.md"):
            path.write_text(path.read_text().replace("jk_format: 1", "jk_format: 2"))

    monkeypatch.setattr(model, "FORMAT_VERSION", 2)
    monkeypatch.setattr(migrate, "MIGRATIONS", {1: v1_to_v2})
    msgs = migrate.ensure(store.home)
    assert "v1 → v2" in msgs[0]
    assert migrate.read_version(store.home) == 2
    backups = list((store.home / "backups").iterdir())
    assert "jk_format: 1" in (backups[0] / "notebooks" / "作业.md").read_text()
    assert (backups[0] / "history" / "snap").is_dir() and not (store.home / "history").exists()
    assert "jk_format: 2" in (store.notebooks_dir / "作业.md").read_text()
    assert migrate.ensure(store.home) == []  # 幂等


def test_missing_migration_stops(store, monkeypatch):
    migrate.write_version(store.home, 1)
    (store.home / "history" / "snap").mkdir(parents=True)
    monkeypatch.setattr(model, "FORMAT_VERSION", 2)
    monkeypatch.setattr(migrate, "MIGRATIONS", {})
    with pytest.raises(migrate.FormatError, match="缺少"):
        migrate.ensure(store.home)
    assert migrate.read_version(store.home) == 1
    assert (store.home / "history" / "snap").is_dir() and not (store.home / "backups").exists()


def test_corrupt_version_file(tmp_path):
    (tmp_path / "jk.json").write_text("{bad")
    with pytest.raises(migrate.FormatError, match="损坏"):
        migrate.ensure(tmp_path)
