import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from jk import cli, compose as compose_mod
from jk.attach import Attachment
from jk.compose import Composer, compose

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
PASTE = "\x1b[200~{}\x1b[201~"  # 终端的括号粘贴序列（Ctrl+Shift+V 发出的就是它）
CTRL_V = "\x16"


def run(tmp_path, keys):
    with create_pipe_input() as inp:
        inp.send_text(keys)
        return compose(tmp_path / "pastes", input=inp, output=DummyOutput())


def test_short_paste_inline(tmp_path):
    text, atts, c = run(tmp_path, "交 " + PASTE.format("作业 a") + "\r")
    assert text == "交 作业 a" and atts == []
    c.cleanup()


def test_long_paste_becomes_placeholder_and_file(tmp_path):
    body = "周五交实验报告\n下周一交作业 b\n"
    text, atts, c = run(tmp_path, "这是通知 " + PASTE.format(body) + "\r")
    assert text == "这是通知 [粘贴文字 #1 · 2行]"
    assert atts[0].kind == "text" and "下周一交作业 b" in atts[0].text and atts[0].source == "粘贴文字 #1 · 2行"
    folder = c.folder
    assert (folder / "1.txt").read_text() == body
    c.cleanup()
    assert not folder.exists()


def test_ctrl_v_image(tmp_path, monkeypatch):
    monkeypatch.setattr(compose_mod, "read_clipboard", lambda: Attachment(kind="image", data=PNG, mime="image/png", source="剪贴板"))
    text, atts, c = run(tmp_path, "看图 " + CTRL_V + "\r")
    assert text == "看图 [图片 #1]"
    assert atts[0].kind == "image" and atts[0].source == "图片 #1" and (c.folder / "1.png").exists()
    c.cleanup()


def test_deleted_placeholder_not_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(compose_mod, "read_clipboard", lambda: Attachment(kind="image", data=PNG, mime="image/png", source="剪贴板"))
    backspaces = "\x7f" * len("[图片 #1]")
    text, atts, c = run(tmp_path, "x " + CTRL_V + backspaces + "\r")
    assert atts == [] and "[图片" not in text
    c.cleanup()


def test_cancel_cleans_up(tmp_path):
    assert run(tmp_path, PASTE.format("a\nb") + "\x03") is None
    assert not any((tmp_path / "pastes").iterdir())


def test_stale_folders_removed(tmp_path):
    import os
    old = tmp_path / "pastes" / "old"
    old.mkdir(parents=True)
    os.utime(old, (0, 0))
    run(tmp_path, "\x03")
    assert not old.exists()


def test_jk_a_without_args_uses_box_and_deletes_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("JK_API_KEY", "test")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    composer = Composer(tmp_path / "home" / "pastes")
    tag = composer.add_text("周五交实验报告\n下周一交作业 b")
    monkeypatch.setattr(cli, "compose", lambda root: (f"通知 {tag}", composer.collect(f"通知 {tag}"), composer))
    seen = []

    class Fake:
        def complete(self, messages):
            seen.append(messages)
            return '{"reply": "好", "ops": []}'

    monkeypatch.setattr(cli, "Client", lambda cfg: Fake())
    assert cli.main(["a"]) == 0
    assert "下周一交作业 b" in seen[0][1]["content"]
    assert not composer.folder.exists()
