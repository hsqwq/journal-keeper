import time
from datetime import datetime, timedelta

import pytest

from jk import autosync, cli, ucloud
from jk.config import load_config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    monkeypatch.setenv("JK_UCLOUD_AUTO", "1")
    monkeypatch.setenv("UCLOUD_USERNAME", "2023000000")
    monkeypatch.setenv("UCLOUD_PASSWORD", "pw")
    return tmp_path


def todo(id, title):
    return {"id": id, "title": title, "course": "编译原理与技术", "end_time": "2026-10-31 23:59", "type": "作业"}


def fake_fetch(monkeypatch, result):
    calls = []

    def fetch(user, pw):
        calls.append(1)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(ucloud, "fetch_todos", fetch)
    return calls


def test_first_run_of_day_syncs_once(home, monkeypatch, capsys):
    calls = fake_fetch(monkeypatch, [todo("A", "第二次作业")])
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "已自动同步云邮：新增 1" in out and "云邮 [0/1]" in out  # 先一行提示，再照常显示列表
    assert out.index("已自动同步云邮") < out.index("云邮 [0/1]")
    cli.main([])
    assert len(calls) == 1 and "自动同步" not in capsys.readouterr().out


def test_no_changes_message(home, monkeypatch, capsys):
    fake_fetch(monkeypatch, [])
    cli.main(["h"])
    assert "没有变化（平台上 0 项待办）" in capsys.readouterr().out


def test_failure_retries_after_an_hour(home, monkeypatch, capsys):
    calls = fake_fetch(monkeypatch, ucloud.UcloudError("连不上教学云平台"))
    assert cli.main([]) == 0  # 失败不影响命令本身
    assert "云邮自动同步失败" in capsys.readouterr().err
    cli.main([])
    assert len(calls) == 1  # 冷却期内不重试
    cfg = load_config()
    later = datetime.now() + timedelta(hours=1, minutes=1)
    assert autosync.due(cfg, later)


def test_undo_and_u_do_not_trigger(home, monkeypatch, capsys):
    calls = fake_fetch(monkeypatch, [todo("A", "第二次作业")])
    cli.main(["undo"])
    assert calls == []
    cli.main(["u"])  # 手动同步成功后，今天不再自动同步
    cli.main([])
    assert len(calls) == 1


def test_disabled_or_no_account(home, monkeypatch):
    calls = fake_fetch(monkeypatch, [])
    monkeypatch.setenv("JK_UCLOUD_AUTO", "0")
    cli.main([])
    monkeypatch.setenv("JK_UCLOUD_AUTO", "1")
    monkeypatch.setenv("UCLOUD_PASSWORD", "")
    cli.main([])
    assert calls == []


def test_completion_never_syncs(home, monkeypatch, capsys):
    calls = fake_fetch(monkeypatch, [])
    cli.main(["__complete"])
    assert calls == []


def test_timeout(home, monkeypatch):
    monkeypatch.setattr(autosync, "TIMEOUT", 0.2)
    monkeypatch.setattr(ucloud, "fetch_todos", lambda u, p: time.sleep(2))
    start = time.monotonic()
    with pytest.raises(ucloud.UcloudError, match="没响应"):
        autosync.fetch_with_timeout(load_config())
    assert time.monotonic() - start < 1


def test_corrupt_state_file_is_ignored(home):
    (home / "state.json").write_text("{bad")
    assert autosync.due(load_config(), datetime.now())
