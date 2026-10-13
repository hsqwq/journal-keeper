"""命令行入口：jk / jk a / jk c / jk t / jk undo。"""

from __future__ import annotations

import sys

from rich.console import Console

from . import __version__, history
from .archive import auto_archive
from .config import Config, ensure_env_file, load_config
from .model import DONE, NOTE, TODO, fmt_dt, now_minute
from .render import render_list
from .store import Store, find_item

console = Console(highlight=False)
err = Console(stderr=True, highlight=False)

HELP = """\
[bold]jk[/] — Journal Keeper，AI 帮你整理的终端记事本

  [bold]jk[/]                 列出所有记事本
  [bold]jk a[/] <一句话>      交给 AI 处理，例：jk a 明天三点前交作业 a
  [bold]jk c[/] <编号…>       标记完成 / 取消完成（不走 AI），例：jk c 2 3
  [bold]jk t[/] [天数]        时间线：回顾最近几天 + 即将到期（默认 7 天）
  [bold]jk undo[/]            撤销上一次改动

  数据目录：{home}
  配置文件：{home}/.env
"""


def open_store(cfg: Config) -> tuple[Store, list]:
    store = Store(cfg.home)
    books = store.load()
    auto_archive(store, books, cfg.archive_after_days)
    return store, books


def cmd_list(cfg: Config, args: list[str]) -> int:
    _, books = open_store(cfg)
    render_list(console, books)
    return 0


def cmd_check(cfg: Config, args: list[str]) -> int:
    if not args:
        err.print("[red]请给出编号[/]，例：jk c 2 3")
        return 2
    try:
        ids = [int(a.lstrip("#")) for a in args]
    except ValueError:
        err.print("[red]编号必须是数字[/]，例：jk c 2 3")
        return 2
    store, books = open_store(cfg)
    found = {i: find_item(books, i) for i in ids}
    missing = [str(i) for i, hit in found.items() if hit is None]
    notes = [str(i) for i, hit in found.items() if hit and hit[1].kind == NOTE]
    if missing or notes:
        if missing:
            err.print(f"[red]找不到编号[/] {' '.join(missing)}")
        if notes:
            err.print(f"[red]这些是笔记，不能标完成[/] {' '.join(notes)}")
        return 1
    history.snapshot(store, f"jk c {' '.join(args)}")
    now = fmt_dt(now_minute())
    for _, item in found.values():
        if item.state == DONE:
            item.state, item.done_at = TODO, None
            console.print(f"  [magenta]☐ 取消完成[/] {item.id}. {item.text}")
        else:
            item.state, item.done_at = DONE, now
            console.print(f"  [green]✔ 完成[/] {item.id}. {item.text}")
    store.save(books)
    render_list(console, books)
    return 0


def cmd_undo(cfg: Config, args: list[str]) -> int:
    label = history.undo(Store(cfg.home))
    if label is None:
        console.print("  没有可以撤销的改动。")
        return 0
    console.print(f"  [yellow]↶ 已撤销[/]：{label}")
    return cmd_list(cfg, [])


def cmd_help(cfg: Config, args: list[str]) -> int:
    console.print(HELP.format(home=cfg.home))
    return 0


COMMANDS = {
    "c": cmd_check,
    "undo": cmd_undo,
    "help": cmd_help,
    "-h": cmd_help,
    "--help": cmd_help,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-V", "--version"):
        console.print(f"jk {__version__}")
        return 0
    cfg = load_config()
    if ensure_env_file(cfg.home):
        console.print(f"  [dim]已生成配置文件 {cfg.env_file}，用 AI 前请填入 JK_API_KEY。[/]")
    if not argv:
        return cmd_list(cfg, [])
    handler = COMMANDS.get(argv[0])
    if handler is None:
        err.print(f"[red]不认识的命令[/] {argv[0]}。想让 AI 处理请用：jk a {' '.join(argv)}")
        return 2
    try:
        return handler(cfg, argv[1:])
    except KeyboardInterrupt:
        err.print("\n  已取消，没有改动。")
        return 130
