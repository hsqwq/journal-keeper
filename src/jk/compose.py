"""交互输入框（jk a 不带参数时）：像 Claude Code 一样粘贴文字和图片。

- Ctrl+Shift+V（终端自带粘贴）：短文字直接插入；长文字存进 pastes/，输入框里显示 [粘贴文字 #1 · 20行]。
- Ctrl+V：jk 自己读剪贴板，图片显示 [图片 #1]，文字同上。
- 回车发送；删掉占位符 = 不发送那一项。粘贴文件在发送结束后删除。
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from .attach import EXT, AttachError, Attachment, make_image, make_text, read_clipboard

INLINE_MAX_CHARS = 200  # 不超过这个长度、且只有一行的粘贴直接插入
STALE_SECONDS = 24 * 3600  # 异常退出残留的粘贴目录，超过一天自动清掉


@dataclass
class Composer:
    pastes_root: Path
    counter: int = 0
    files: dict[str, Path] = field(default_factory=dict)  # 占位符 → 文件
    folder: Path | None = None

    def _folder(self) -> Path:
        if self.folder is None:
            self.folder = self.pastes_root / f"{time.strftime('%Y%m%d-%H%M%S')}-{id(self) % 10000}"
            self.folder.mkdir(parents=True)
        return self.folder

    def add_text(self, text: str) -> str:
        """返回要插入输入框的内容：短文字原样，长文字换成占位符。"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if "\n" not in text.strip() and len(text) <= INLINE_MAX_CHARS:
            return text
        self.counter += 1
        lines = text.strip().count("\n") + 1
        tag = f"[粘贴文字 #{self.counter} · {lines}行]"
        path = self._folder() / f"{self.counter}.txt"
        path.write_text(text, encoding="utf-8")
        self.files[tag] = path
        return tag

    def add_attachment(self, att: Attachment) -> str:
        if att.kind == "text":
            return self.add_text(att.text)
        self.counter += 1
        tag = f"[图片 #{self.counter}]"
        path = self._folder() / f"{self.counter}.{EXT[att.mime]}"
        path.write_bytes(att.data)
        self.files[tag] = path
        return tag

    def collect(self, text: str) -> list[Attachment]:
        """按输入框里还留着的占位符，从粘贴目录读回附件（顺序同出现顺序）。"""
        present = sorted((text.find(tag), tag) for tag in self.files if tag in text)
        result = []
        for _, tag in present:
            path = self.files[tag]
            if tag.startswith("[图片"):
                result.append(make_image(path.read_bytes(), tag.strip("[]")))
            else:
                result.append(make_text(path.read_text(encoding="utf-8"), tag.strip("[]")))
        return result

    def cleanup(self) -> None:
        if self.folder and self.folder.exists():
            shutil.rmtree(self.folder)


def clean_stale(pastes_root: Path) -> None:
    if not pastes_root.is_dir():
        return
    cutoff = time.time() - STALE_SECONDS
    for folder in pastes_root.iterdir():
        if folder.is_dir() and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)


def build_bindings(composer: Composer) -> KeyBindings:
    kb = KeyBindings()

    @kb.add(Keys.BracketedPaste, eager=True)
    def _(event):
        event.current_buffer.insert_text(composer.add_text(event.data))

    @kb.add("c-v", eager=True)
    def _(event):
        try:
            att = read_clipboard()
        except AttachError as exc:
            message = str(exc)
            run_in_terminal(lambda: print(f"  ✖ {message}"))
            return
        event.current_buffer.insert_text(composer.add_attachment(att))

    return kb


TOOLBAR = HTML(" <b>回车</b> 发送 · <b>Ctrl+Shift+V</b> 粘文字 · <b>Ctrl+V</b> 粘图片/文字 · <b>Ctrl+C</b> 取消")


def compose(pastes_root: Path, **session_kwargs) -> tuple[str, list[Attachment], Composer] | None:
    """弹输入框；取消返回 None。调用方用完后必须 composer.cleanup()。"""
    clean_stale(pastes_root)
    composer = Composer(pastes_root)
    session = PromptSession(key_bindings=build_bindings(composer), bottom_toolbar=TOOLBAR, **session_kwargs)
    try:
        text = session.prompt("  想做什么？> ")
    except (KeyboardInterrupt, EOFError):
        composer.cleanup()
        return None
    text = text.strip()
    if not text:
        composer.cleanup()
        return None
    # 指令里保留占位符，AI 能看出每段内容对应哪句话
    return text, composer.collect(text), composer

