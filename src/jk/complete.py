"""Tab 补全（zsh）。

zsh 脚本只负责调用 `jk __complete <命令> [已输入的参数…]`，候选项由这里按当前数据算出来，
每行一个 `值:说明`。补全时绝不能报错或打印别的东西，所以任何异常都吞掉、输出空。
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .model import NOTE, RECUR
from .store import Store

ZSH_SCRIPT = r"""# jk（Journal Keeper）的 zsh 补全。由 jk 自动生成和更新，不要手改。
_jk() {
  local -a items
  if (( CURRENT == 2 )); then
    items=("${(@f)$(jk __complete 2>/dev/null)}")
    _describe -V -t commands 'jk 命令 / 记事本' items
  else
    items=("${(@f)$(jk __complete "${(@)words[2,CURRENT-1]}" 2>/dev/null)}")
    (( ${#items[@]} )) && [[ -n "${items[1]}" ]] && _describe -V -t values 'jk' items
  fi
}
compdef _jk jk
"""

COMMANDS = (
    ("a", "交给 AI 处理（不带参数打开输入框）"),
    ("c", "标记完成 / 取消完成"),
    ("t", "时间线"),
    ("s", "搜索"),
    ("u", "同步教学云平台待办"),
    ("undo", "撤销上一次改动"),
    ("h", "帮助"),
)


def _esc(value: str) -> str:
    """_describe 用冒号分隔值和说明，值里的冒号要转义。"""
    return value.replace("\\", "\\\\").replace(":", "\\:")


def candidates(cfg: Config, words: list[str]) -> list[str]:
    """words = 命令行里 jk 后面已经输完的词（不含正在输的那个）。"""
    books = Store(cfg.home).load()
    names = [nb.name for nb in books]
    if not words:
        return [f"{name}:{_esc(desc)}" for name, desc in COMMANDS] + [f"{_esc(n)}:记事本" for n in names]
    cmd, typed = words[0], set(words[1:])
    if cmd == "c":
        items = [it for nb in books for it in nb.items if it.kind not in (NOTE, RECUR)]
        items.sort(key=lambda it: (it.state == "done", it.id))
        return [
            f"{it.id}:{'✔ ' if it.state == 'done' else ''}{it.text}"
            for it in items
            if str(it.id) not in typed
        ]
    if cmd in names or not any(cmd == c for c, _ in COMMANDS):
        return [f"{_esc(n)}:记事本" for n in names if n not in words]
    return []


def run(cfg: Config, words: list[str]) -> int:
    try:
        lines = candidates(cfg, words)
    except Exception:  # noqa: BLE001 —— 补全时任何错误都只能静默
        return 0
    print("\n".join(lines))
    return 0


def script_path(cfg: Config) -> Path:
    return cfg.home / "completion.zsh"


def refresh_script(cfg: Config) -> None:
    """已安装过补全（文件存在）就保持内容最新，jk 升级后不用手动重装。"""
    path = script_path(cfg)
    try:
        if path.exists() and path.read_text(encoding="utf-8") != ZSH_SCRIPT:
            path.write_text(ZSH_SCRIPT, encoding="utf-8")
    except OSError:
        pass
