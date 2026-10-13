"""配色：全部用固定的十六进制颜色，不用终端调色板的 magenta / cyan 等名字。

原因：终端主题会改写调色板（例如有的主题把 magenta 显示成深蓝），固定颜色才能保证在深色背景下都看得清。
要改颜色只改这里的 PALETTE。
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

PALETTE = {
    "muted": "#b4bcc8",        # 编号、时间、记事本名等辅助信息（浅灰）
    "todo": "#ff9ecf",         # 待办 ☐（粉）
    "doing": "#ffe066",        # 进行中 …（黄）
    "done": "#7cff8d",         # 已完成 ✔（绿）
    "done_text": "#b4bcc8 strike",  # 已完成条目的文字
    "note": "bold #ffffff",    # 笔记 ●（亮白）
    "recur": "bold #ffb86c",   # 周期 ↻（橙）
    "pri2": "bold #ffe066",    # 重要 !
    "pri3": "bold #ff739e",    # 紧急 !!
    "overdue": "bold #ff739e", # 已逾期
    "soon": "#ffe066",         # 24 小时内到期
    "later": "#9ff2e8",        # 更晚到期（浅青绿，不是蓝）
    "add": "#9ff2e8",          # ＋ 新增
    "update": "#ffe066",       # ✎ 修改
    "delete": "#ff739e",       # ✖ 删除
    "dup": "#d8c8a8",          # ≈ 已存在（浅卡其）
    "error": "bold #ff739e",   # 错误
    "ask": "bold #ffe066",     # AI 反问
}

THEME = Theme({f"jk.{name}": style for name, style in PALETTE.items()})


def make_console(**kwargs) -> Console:
    return Console(theme=THEME, highlight=False, **kwargs)
