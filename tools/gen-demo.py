"""生成 README 用的演示截图（docs/images/*.png）。

数据全部虚构、时间固定，所以每次生成结果一样；改了界面后重跑一次即可：

    uv run python tools/gen-demo.py

做法：rich 导出带颜色的 HTML → 无头 Firefox 截图。
不用 rich 自带的 SVG 导出：它按固定字宽排字，中文会互相重叠。
需要：firefox、ImageMagick（magick，用来裁掉空白）、字体 Noto Sans Mono CJK SC（中文正好占两个英文字宽），
符号 ↻ ☐ ✎ 由 Adwaita Mono / Noto Sans Symbols 2 补字。
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from jk import cli
from jk.model import DOING, DONE, NOTE, RECUR, Item, Notebook
from jk.ops import Change, apply, validate
from jk.render import render_list
from jk.theme import make_console
from jk.timeline import render_timeline

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
WIDTH = 72
NOW = datetime(2026, 10, 14, 9, 30)  # 周三上午
T = "2026-10-14T08:00"


def demo_books() -> list[Notebook]:
    return [
        Notebook("周期", [
            Item(9, "晨跑", kind=RECUR, every="weekly:1,3,5@07:00", created=T),
            Item(10, "英语角", kind=RECUR, every="weekly:4@19:30", created=T),
            Item(11, "交房租", kind=RECUR, every="monthly:15", created=T),
        ]),
        Notebook("课程", [
            Item(1, "提交操作系统实验报告", due="2026-10-16T18:00", pri=2, created="2026-10-12T20:10"),
            Item(2, "复习线性代数期中", state=DOING, due="2026-10-21", created="2026-10-11T09:00"),
            Item(3, "读完《设计模式》第 3 章", created="2026-10-13T22:00"),
            Item(4, "交课程设计开题报告", state=DONE, created="2026-10-10T10:00", done_at="2026-10-13T16:20"),
        ]),
        Notebook("工作", [
            Item(5, "回复客户的报价邮件", due="2026-10-13T17:00", pri=3, created="2026-10-12T09:15"),
            Item(6, "准备季度汇报 PPT", due="2026-10-15T14:00", created="2026-10-13T11:00"),
            Item(7, "整理周会纪要", state=DONE, created="2026-10-13T10:00", done_at="2026-10-14T09:10"),
        ]),
        Notebook("生活", [
            Item(8, "买猫粮", created="2026-10-14T08:40"),
            Item(12, "健身房周日闭馆", kind=NOTE, created="2026-10-12T19:00"),
        ]),
    ]


BG, FG = "#101418", "#e0e2e8"  # 深色终端背景（与作者的 kitty 主题一致）
PAGE = """<!doctype html><meta charset="utf-8"><style>
body {{ margin: 0; background: transparent; }}
.win {{ display: inline-block; margin: 16px; background: {bg}; border-radius: 10px;
        box-shadow: 0 6px 20px rgba(0,0,0,.35); overflow: hidden; }}
.bar {{ height: 30px; background: #1d232a; display: flex; align-items: center; padding: 0 12px; gap: 8px;
        color: #8b949e; font: 13px sans-serif; }}
.dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.g {{ display: inline-block; width: 1ch; text-align: center; overflow: hidden; vertical-align: bottom;
      font-family: "Adwaita Mono", "Noto Sans Symbols 2", monospace; }}
pre {{ margin: 0; padding: 12px 18px 16px; color: {fg};
       font: 15px/1.45 "Noto Sans Mono CJK SC", "Adwaita Mono", "Noto Sans Symbols 2", monospace; }}
</style><div class="win"><div class="bar">
<span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span>
<span class="dot" style="background:#28c840"></span><span style="margin-left:8px">{title}</span></div>
<pre>{body}</pre></div>"""


NARROW_SYMBOLS = "☐…✔●↻✎≈⇄✖⚠"


def save(console, name: str, title: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    body = console.export_html(inline_styles=True, code_format="{code}")
    # 这些符号在终端里占 1 格，但网页字体里的字形宽窄不一：固定成 1 个字符宽，右侧时间才能对齐
    for ch in NARROW_SYMBOLS:
        body = body.replace(ch, f'<span class="g">{ch}</span>')
    target = OUT / f"{name}.png"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(PAGE.format(bg=BG, fg=FG, title=title, body=body), encoding="utf-8")
        shot = Path(tmp) / "shot.png"
        subprocess.run(
            ["firefox", "--headless", "--window-size=900,1400", "--screenshot", str(shot), page.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        # 裁掉截图右侧和下方的空白，只留窗口和阴影
        subprocess.run(["magick", str(shot), "-trim", "+repage", "-bordercolor", "white", "-border", "8", str(target)], check=True)
    print(f"写入 docs/images/{name}.png")


def prompt(console, command: str) -> None:
    console.print(f"[bold]$[/] {command}")


def demo_list() -> None:
    console = make_console(record=True, width=WIDTH, file=io.StringIO())
    prompt(console, "jk")
    render_list(console, demo_books(), NOW)
    save(console, "list", "jk")


def demo_timeline() -> None:
    console = make_console(record=True, width=WIDTH, file=io.StringIO())
    prompt(console, "jk t 3")
    render_timeline(console, demo_books(), [], 3, NOW)
    save(console, "timeline", "jk t")


def demo_ai() -> None:
    """jk a 的三种典型交互：一句话新增、截图去重、听不懂时反问。改动用真实的 apply 算出来。"""
    console = make_console(record=True, width=WIDTH, file=io.StringIO())
    cli.console = console  # print_changes / ask_user 用的是 cli 模块里的 console
    books = demo_books()

    def show(reply: str, ops: list[dict], extra: list[Change] = ()) -> None:
        changes = apply(validate(ops, books), books)
        console.print(f"  [bold]{reply}[/]")
        cli.print_changes(changes + list(extra))
        console.print()

    prompt(console, "jk a 周六下午两点前买好妈妈的生日礼物，挺重要的")
    show("记下了，周六 14:00 前买礼物，放进「生活」。", [
        {"op": "add", "notebook": "生活", "text": "买妈妈的生日礼物", "due": "2026-10-17T14:00", "priority": 2},
    ])

    prompt(console, "jk a 这是课程群通知 [图片 #1]")
    console.print("  [jk.muted]已读取图片 #1：图片（PNG，86 KB）[/]")
    show("线代期中改到下周四了；实验报告已经记过；新加了一个小测。", [
        {"op": "update", "id": 2, "due": "2026-10-22"},
        {"op": "add", "notebook": "课程", "text": "参加数据结构随堂小测", "due": "2026-10-20T10:00"},
    ], [Change("dup", "1. 提交操作系统实验报告", "已有，截止时间相同")])

    prompt(console, "jk a 每周下午四点打羽毛球")
    console.print("\n  [jk.ask]?[/] 每周几下午四点打羽毛球？")
    for n, opt in enumerate(["每周二 16:00", "每周四 16:00", "每周二、四 16:00"], 1):
        console.print(f"    [bold]{n})[/] {opt}")
    console.print("  [jk.muted]输入编号，或直接打字回答；直接回车取消[/]")
    console.print("  > 3\n")
    show("好，每周二、四下午四点打羽毛球。", [
        {"op": "add", "kind": "recur", "text": "打羽毛球", "every": "weekly:2,4@16:00"},
    ])
    save(console, "ai", "jk a")


if __name__ == "__main__":
    for tool in ("firefox", "magick"):
        if not shutil.which(tool):
            raise SystemExit(f"缺少 {tool}，无法截图")
    demo_list()
    demo_timeline()
    demo_ai()
