"""运行状态：$JK_HOME/state.json。不属于数据格式，删掉只会重做当天的自动同步、丢掉周次设置。"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .store import atomic_write


def path(cfg: Config) -> Path:
    return cfg.home / "state.json"


def read(cfg: Config) -> dict:
    try:
        data = json.loads(path(cfg).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def update(cfg: Config, **fields) -> None:
    data = read(cfg)
    data.update(fields)
    try:
        atomic_write(path(cfg), json.dumps(data, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 记不下来最多是多同步一次 / 周次设置没保存
