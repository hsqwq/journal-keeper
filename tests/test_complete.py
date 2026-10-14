import shutil
import subprocess

import pytest

from jk import cli, complete
from jk.config import load_config
from jk.model import DONE, NOTE, RECUR, Item, Notebook
from jk.store import Store


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    Store(tmp_path).save([
        Notebook("周期", [Item(9, "晨跑", kind=RECUR, every="daily")]),
        Notebook("课程", [Item(2, "复习线代"), Item(1, "交报告", state=DONE), Item(3, "想法", kind=NOTE)]),
        Notebook("a:b", [Item(4, "名字带冒号")]),
    ])
    return load_config()


def test_top_level_commands_and_notebooks(cfg):
    out = complete.candidates(cfg, [])
    assert out[0] == "a:交给 AI 处理（不带参数打开输入框）"
    assert "课程:记事本" in out and "a\\:b:记事本" in out


def test_c_lists_tasks_open_first_and_skips_typed(cfg):
    assert complete.candidates(cfg, ["c"]) == ["2:复习线代", "4:名字带冒号", "1:✔ 交报告"]
    assert complete.candidates(cfg, ["c", "2"]) == ["4:名字带冒号", "1:✔ 交报告"]


def test_notebook_names_after_notebook(cfg):
    assert sorted(complete.candidates(cfg, ["课程"])) == sorted(["周期:记事本", "a\\:b:记事本"])
    assert complete.candidates(cfg, ["t"]) == []


def test_complete_never_prints_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JK_HOME", str(tmp_path / "no" / "such"))
    monkeypatch.setattr(complete, "candidates", lambda *a: 1 / 0)
    assert cli.main(["__complete", "c"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_completion_script_and_auto_refresh(cfg, capsys):
    assert cli.main(["completion", "zsh"]) == 0
    assert "compdef _jk jk" in capsys.readouterr().out
    assert cli.main(["completion", "bash"]) == 2
    path = complete.script_path(cfg)
    path.write_text("old")
    cli.main(["h"])
    assert path.read_text() == complete.ZSH_SCRIPT


@pytest.mark.skipif(not shutil.which("zsh"), reason="需要 zsh")
def test_zsh_script_is_valid():
    result = subprocess.run(["zsh", "-n", "-c", complete.ZSH_SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
