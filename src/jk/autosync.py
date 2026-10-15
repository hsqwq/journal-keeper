"""每天第一次运行 jk 时自动同步云邮（jk u），只显示一行结果，然后照常执行命令。

- 「今天已成功同步」记在 $JK_HOME/state.json，不属于数据格式（删掉只会让当天多同步一次）。
- 失败（断网、要验证码…）后 RETRY_AFTER 内不再自动重试，免得每次都卡住、也免得频繁登录触发验证码。
- 整个过程最多等 TIMEOUT 秒；超时就放弃这一次，不影响后面的命令。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import ucloud
from .config import Config
from .store import atomic_write

TIMEOUT = 10  # 秒
RETRY_AFTER = timedelta(hours=1)


def _state_path(cfg: Config) -> Path:
    return cfg.home / "state.json"


def read_state(cfg: Config) -> dict:
    try:
        data = json.loads(_state_path(cfg).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(cfg: Config, **fields) -> None:
    state = read_state(cfg)
    state.update(fields)
    try:
        atomic_write(_state_path(cfg), json.dumps(state, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 记不下来最多是多同步一次


def record_success(cfg: Config, now: datetime) -> None:
    _write_state(cfg, ucloud_synced_on=now.date().isoformat(), ucloud_failed_at=None)


def record_failure(cfg: Config, now: datetime) -> None:
    _write_state(cfg, ucloud_failed_at=now.isoformat(timespec="seconds"))


def due(cfg: Config, now: datetime) -> bool:
    """今天还没成功同步过、且不在失败冷却期内，才自动同步。没配账号或关掉了就不同步。"""
    if not cfg.ucloud_auto or not cfg.ucloud_username or not cfg.ucloud_password:
        return False
    state = read_state(cfg)
    if state.get("ucloud_synced_on") == now.date().isoformat():
        return False
    failed = state.get("ucloud_failed_at")
    if failed:
        try:
            if now - datetime.fromisoformat(failed) < RETRY_AFTER:
                return False
        except ValueError:
            pass
    return True


def fetch_with_timeout(cfg: Config) -> list[dict]:
    """在后台线程里取数据，最多等 TIMEOUT 秒；超时抛 UcloudError（线程设为 daemon，不拖住程序退出）。"""
    result: dict = {}

    def work():
        try:
            result["todos"] = ucloud.fetch_todos(cfg.ucloud_username, cfg.ucloud_password)
        except Exception as exc:  # noqa: BLE001 —— 交给主线程统一处理
            result["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(TIMEOUT)
    if thread.is_alive():
        raise ucloud.UcloudError(f"超过 {TIMEOUT} 秒没响应")
    if "error" in result:
        error = result["error"]
        raise error if isinstance(error, ucloud.UcloudError) else ucloud.UcloudError(str(error))
    return result["todos"]


def summarize(changes) -> str:
    """新增 1、完成 2、改动 1。"""
    names = {"add": "新增", "done": "完成", "undone": "改回未完成", "update": "改动"}
    counts: dict[str, int] = {}
    for ch in changes:
        label = names.get(ch.kind, "改动")
        counts[label] = counts.get(label, 0) + 1
    return "、".join(f"{label} {n}" for label, n in counts.items())
