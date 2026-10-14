from datetime import datetime

from jk import cli
from jk.model import DONE, RECUR, Item, Notebook
from jk.render import render_search
from jk.theme import make_console

NOW = datetime(2026, 10, 14, 9, 30)


def books():
    return [
        Notebook("周期", [Item(9, "晨跑", kind=RECUR, every="daily")]),
        Notebook("课程", [Item(1, "提交操作系统实验报告", due="2026-10-16T18:00"), Item(2, "复习线性代数")]),
        Notebook("课程设计", [Item(3, "写开题报告")]),
        Notebook("工作", [Item(5, "回复客户的 Report 邮件")]),
    ]


# ---------- jk 作业 ----------

def test_pick_exact_name_wins():
    assert [nb.name for nb in cli.pick_notebooks(books(), ["课程"])] == ["课程"]


def test_pick_partial_and_multiple():
    assert [nb.name for nb in cli.pick_notebooks(books(), ["课"])] == ["课程", "课程设计"]
    assert [nb.name for nb in cli.pick_notebooks(books(), ["工", "周期", "工作"])] == ["工作", "周期"]
    assert cli.pick_notebooks(books(), ["生活"]) == []


def save(env, bs):
    from jk.store import Store

    Store(env).save(bs)


def test_jk_notebook_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    save(tmp_path, books())
    assert cli.main(["工"]) == 0
    out = capsys.readouterr().out
    assert "工作 [0/1]" in out and "课程" not in out and "晨跑" not in out
    assert cli.main(["生活"]) == 2
    msg = capsys.readouterr().err
    assert "没有叫「生活」的记事本" in msg and "课程设计" in msg and "jk a 生活" in msg


def test_commands_still_win_over_notebook_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    save(tmp_path, [Notebook("h", [Item(1, "x")])])
    assert cli.main(["h"]) == 0
    assert "常用命令" in capsys.readouterr().out


# ---------- jk s ----------

def run_search(words, archive=()):
    console = make_console(record=True, width=90)
    n = render_search(console, books(), list(archive), words, NOW)
    return n, console.export_text()


def test_search_active_and_archive_grouped():
    archive = [Notebook("课程", [Item(7, "交上周的实验报告", state=DONE, done_at="2026-10-12T20:00")])]
    n, out = run_search(["报告"], archive)
    assert n == 3
    assert "课程 [1 条]" in out and "课程设计 [1 条]" in out and "已归档 [1 条]" in out
    assert "1. ☐ 提交操作系统实验报告" in out and "前天 完成" in out
    assert "复习线性代数" not in out and "找到 3 条" in out
    assert out.index("课程 [1 条]") < out.index("已归档")


def test_search_all_words_and_ignore_case():
    n, out = run_search(["report", "客户"])
    assert n == 1 and "回复客户的 Report 邮件" in out
    n, out = run_search(["报告", "线性"])
    assert n == 0 and "没找到含「报告 线性」的条目" in out


def test_search_highlights_keyword():
    console = make_console(record=True, width=90)
    render_search(console, books(), [], ["实验"], NOW)
    html = console.export_html(inline_styles=True)
    assert "background-color: #ffe066" in html and ">实验</span>" in html


def test_jk_s_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    save(tmp_path, books())
    assert cli.main(["s"]) == 2
    assert "要找的字" in capsys.readouterr().err
    assert cli.main(["s", "晨跑"]) == 0
    assert "↻ 晨跑" in capsys.readouterr().out
