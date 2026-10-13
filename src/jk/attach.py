"""附件：读剪贴板（文字 / 图片）与图片文件，交给 AI 一起看。"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # DeepSeek 上限 32 MiB，留余量
MAX_TEXT_CHARS = 20000

# 按文件头识别格式（DeepSeek 同样按内容识别，不看扩展名）
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class AttachError(RuntimeError):
    """给用户看的错误。"""


@dataclass
class Attachment:
    kind: str  # text / image
    text: str = ""
    data: bytes = b""
    mime: str = ""
    source: str = ""  # 来源说明，给用户看

    def describe(self) -> str:
        if self.kind == "text":
            return f"{self.source}：文字 {len(self.text)} 字"
        size = len(self.data) / 1024
        unit = f"{size:.0f} KB" if size < 1024 else f"{size / 1024:.1f} MB"
        return f"{self.source}：图片（{self.mime.split('/')[1].upper()}，{unit}）"

    def data_url(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode()}"


def image_mime(data: bytes) -> str | None:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def make_image(data: bytes, source: str) -> Attachment:
    mime = image_mime(data)
    if mime is None:
        raise AttachError(f"{source} 不是支持的图片（只支持 PNG / JPEG / GIF / WebP）")
    if len(data) > MAX_IMAGE_BYTES:
        raise AttachError(f"{source} 太大（超过 {MAX_IMAGE_BYTES // 1024 // 1024} MB）")
    return Attachment(kind="image", data=data, mime=mime, source=source)


def image_from_path(arg: str) -> Attachment | None:
    """参数是一个存在的图片文件 → 返回附件；否则返回 None（当普通文字处理）。"""
    path = Path(arg).expanduser()
    try:
        if not path.is_file():
            return None
        with path.open("rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if image_mime(head) is None:
        return None
    return make_image(path.read_bytes(), path.name)


def make_text(text: str, source: str) -> Attachment:
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n……（后面太长，已截断）"
    return Attachment(kind="text", text=text, source=source)


# ---------- 剪贴板 ----------

def _run(cmd: list[str]) -> bytes:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return b""


def _backend() -> tuple[list[str], Callable[[str], bytes]] | None:
    """返回（列出类型的命令，按类型取内容的函数）。Wayland 用 wl-paste，X11 用 xclip。"""
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return ["wl-paste", "--list-types"], lambda t: _run(["wl-paste", "--no-newline", "--type", t])
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        base = ["xclip", "-selection", "clipboard", "-o"]
        return [*base, "-t", "TARGETS"], lambda t: _run([*base, "-t", t])
    return None


def read_clipboard() -> Attachment:
    backend = _backend()
    if backend is None:
        raise AttachError("读不了剪贴板：请安装 wl-clipboard（Wayland）或 xclip（X11）")
    list_cmd, fetch = backend
    types = [t.strip() for t in _run(list_cmd).decode(errors="ignore").splitlines() if t.strip()]

    images = [t for t in types if t.startswith("image/")]
    if images:
        preferred = "image/png" if "image/png" in images else images[0]
        return make_image(fetch(preferred), "剪贴板")

    # 在文件管理器里复制的图片文件
    if "text/uri-list" in types:
        for line in fetch("text/uri-list").decode(errors="ignore").splitlines():
            uri = urlparse(line.strip())
            if uri.scheme == "file":
                attachment = image_from_path(unquote(uri.path))
                if attachment:
                    return attachment

    for t in ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "STRING"):
        if t in types:
            text = fetch(t).decode("utf-8", errors="replace")
            if text.strip():
                return make_text(text, "剪贴板")
    raise AttachError("剪贴板是空的：先复制一段文字或截一张图")


# ---------- 防误发密钥 ----------

_SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}"), "API Key"),
    (re.compile(r"\b(?:ghp|gho|github_pat|glpat|xox[abp])[_-][A-Za-z0-9_\-]{16,}"), "访问令牌"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "云服务密钥"),
    (re.compile(r"(?i)(?:\b(?:password|passwd|api[_ ]?key|secret|token)|密码|口令)\s*[:=：]\s*\S+"), "密码"),
)
_LONG_TOKEN = re.compile(r"(?<![\w/.:%-])[A-Za-z0-9_\-]{24,}(?![\w/.%-])")


def looks_secret(text: str) -> str | None:
    """文字里像密钥 / 密码 → 返回类型名；否则 None。宁可多问一句，也不把密钥发出去。"""
    for pattern, name in _SECRET_PATTERNS:
        if pattern.search(text):
            return name
    for token in _LONG_TOKEN.findall(text):
        if re.search(r"\d", token) and re.search(r"[A-Za-z]", token):
            return "疑似密钥的长串字符"
    return None
