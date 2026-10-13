"""数据格式版本与自动迁移（向后兼容）。

- $JK_HOME/jk.json 记录数据格式版本 {"format": N}。
- 启动时版本落后 → 先把数据整体备份到 backups/，再按 MIGRATIONS 逐级升级。
- 版本比程序新（用旧版 jk 打开新数据）→ 拒绝运行，避免旧程序写坏新数据。

以后改格式：FORMAT_VERSION +1，并在 MIGRATIONS 登记「旧版本号 → 升级函数」，同时补测试和 docs/data-format.md。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import model
from .store import atomic_write

# 旧版本号 → 把数据目录从该版本升到下一版本的函数
MIGRATIONS: dict[int, Callable[[Path], None]] = {}

_BACKUP_ITEMS = ("notebooks", "archive", "jk.json", ".env")


class FormatError(RuntimeError):
    pass


def current_version() -> int:
    return model.FORMAT_VERSION


def read_version(home: Path) -> int | None:
    path = home / "jk.json"
    if not path.exists():
        return None
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("format", 1))
    except (ValueError, AttributeError):
        raise FormatError(f"{path} 已损坏，请检查或从 backups/ 恢复") from None


def write_version(home: Path, version: int) -> None:
    atomic_write(home / "jk.json", json.dumps({"format": version}) + "\n")


def _newest_file_format(home: Path) -> int:
    newest = 0
    for sub in ("notebooks", "archive"):
        for path in (home / sub).glob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines()[:5]:
                if line.startswith("jk_format:"):
                    try:
                        newest = max(newest, int(line.split(":", 1)[1]))
                    except ValueError:
                        pass
    return newest


def backup(home: Path, label: str) -> Path:
    dest = home / "backups" / f"{datetime.now():%Y%m%d-%H%M%S}-{label}"
    dest.mkdir(parents=True)
    for name in _BACKUP_ITEMS:
        src = home / name
        if src.is_dir():
            shutil.copytree(src, dest / name)
        elif src.is_file():
            shutil.copy2(src, dest / name)
    return dest


def ensure(home: Path) -> list[str]:
    """检查并升级数据格式；返回给用户看的提示。"""
    target = current_version()
    found = read_version(home)
    if found is None:
        # 首次运行，或早期没有 jk.json 的数据：按文件里的版本号算，没有就是当前版本
        found = _newest_file_format(home) or target
    newest = max(found, _newest_file_format(home))
    if newest > target:
        raise FormatError(f"数据格式是 v{newest}，比当前 jk 支持的 v{target} 新，请先升级 jk")
    messages = []
    if found < target:
        missing = [v for v in range(found, target) if v not in MIGRATIONS]
        if missing:
            raise FormatError(f"缺少 v{missing[0]} → v{missing[0] + 1} 的迁移，数据未改动")
        dest = backup(home, f"v{found}")
        messages.append(f"数据格式 v{found} → v{target}，已先备份到 {dest}")
        # 旧快照是旧格式，撤销到迁移之前没有意义：整体移进备份
        if (home / "history").is_dir():
            shutil.move(home / "history", dest / "history")
        for version in range(found, target):
            MIGRATIONS[version](home)
            write_version(home, version + 1)
    elif read_version(home) is None:
        home.mkdir(parents=True, exist_ok=True)
        write_version(home, target)
    return messages
