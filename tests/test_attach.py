import pytest

from jk import attach
from jk.attach import AttachError, image_from_path, image_mime, make_text, read_clipboard

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def test_image_mime():
    assert image_mime(PNG) == "image/png"
    assert image_mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert image_mime(b"RIFF\0\0\0\0WEBPVP8 ") == "image/webp"
    assert image_mime(b"hello") is None


def test_image_from_path(tmp_path):
    img = tmp_path / "shot.dat"  # 扩展名不重要，按内容识别
    img.write_bytes(PNG)
    att = image_from_path(str(img))
    assert att.mime == "image/png" and att.data_url().startswith("data:image/png;base64,")
    assert "PNG" in att.describe()
    (tmp_path / "a.txt").write_text("作业")
    assert image_from_path(str(tmp_path / "a.txt")) is None
    assert image_from_path("作业a") is None


def test_image_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(attach, "MAX_IMAGE_BYTES", 10)
    (tmp_path / "x.png").write_bytes(PNG)
    with pytest.raises(AttachError, match="太大"):
        image_from_path(str(tmp_path / "x.png"))


def test_text_truncated(monkeypatch):
    monkeypatch.setattr(attach, "MAX_TEXT_CHARS", 5)
    assert make_text("  一二三四五六七  ", "剪贴板").text.startswith("一二三四五\n")


def fake_clipboard(monkeypatch, contents: dict[str, bytes]):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(attach.shutil, "which", lambda name: "/usr/bin/" + name)

    def run(cmd):
        if "--list-types" in cmd:
            return "\n".join(contents).encode()
        return contents[cmd[-1]]

    monkeypatch.setattr(attach, "_run", run)


def test_clipboard_prefers_image(monkeypatch):
    fake_clipboard(monkeypatch, {"text/plain;charset=utf-8": b"hi", "image/png": PNG})
    assert read_clipboard().kind == "image"


def test_clipboard_text(monkeypatch):
    fake_clipboard(monkeypatch, {"text/plain;charset=utf-8": "周五交作业".encode()})
    att = read_clipboard()
    assert att.kind == "text" and att.text == "周五交作业"


def test_clipboard_copied_file(monkeypatch, tmp_path):
    (tmp_path / "截 图.png").write_bytes(PNG)
    fake_clipboard(monkeypatch, {"text/uri-list": f"file://{tmp_path}/%E6%88%AA%20%E5%9B%BE.png".encode()})
    assert read_clipboard().kind == "image"


def test_clipboard_empty_and_missing_tool(monkeypatch):
    fake_clipboard(monkeypatch, {"text/plain": b"  "})
    with pytest.raises(AttachError, match="空"):
        read_clipboard()
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(AttachError, match="安装"):
        read_clipboard()


@pytest.mark.parametrize("text", [
    "sk-" + "a1b2c3d4" * 4,
    "ghp_" + "A1b2" * 6,
    "AKIA" + "ABCDEFGH12345678",
    "数据库密码：hunter2",
    "token = abc",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "x9" * 15,
])
def test_looks_secret_hits(text):
    assert attach.looks_secret(text)


@pytest.mark.parametrize("text", [
    "周五下午三点前交实验报告，地点 A-302",
    "作业 a 截止 2026-10-14T15:00",
    "见 https://example.com/course/2026/homework_assignment_week_07_final",
    "数值分析作业 第 7 章 习题 1-24",
])
def test_looks_secret_misses_normal_text(text):
    assert attach.looks_secret(text) is None
