"""命令行入口：jk / jk a / jk c / jk t / jk undo / jk h。"""

from __future__ import annotations

import sys

from rich.markup import escape

from . import __version__, history, migrate
from .attach import AttachError, image_from_path, looks_secret
from .compose import compose
from .ai import AIError, Client, Conversation
from .archive import auto_archive
from .config import Config, ensure_env_file, load_config
from .model import DONE, NOTE, RECUR, TODO, fmt_dt, now_minute
from .ops import apply, dedupe, skipped_changes
from .render import render_list
from .store import Store, find_item
from .theme import make_console
from .timeline import render_timeline

console = make_console()
err = make_console(stderr=True)

HELP = """\
[bold]jk[/] — Journal Keeper · AI 帮你整理的终端记事本

[bold underline]常用命令[/]
  [bold]jk[/]                看全部记事本
  [bold]jk a[/] 一句话       交给 AI：新增、完成、修改、删除、提问都行
  [bold]jk a[/]              打开输入框，可以粘贴大段文字和截图
  [bold]jk c[/] 2 3          把 2 号、3 号标成完成（再输一次就取消）
  [bold]jk t[/] [天数]       时间线：最近做了什么 + 快到期的（默认 7 天）
  [bold]jk undo[/]           撤销上一次改动（可以连续撤销）
  [bold]jk h[/]              显示这个帮助

[bold underline]跟 AI 说话的例子[/]
  jk a 有个任务，周五下午三点截止，要交项目周报
  jk a 任务2做完了
  jk a 复习期中开始做了
  jk a 回客户邮件很急，改到今晚
  jk a 记一下：健身房周日闭馆
  jk a 每周一早上八点跑步
  jk a 每周二、四下午四点打羽毛球
  jk a 明天要交什么
  jk a 这是课程通知 ~/图片/通知.png
  [jk.muted]AI 没听懂时会给编号选项，输数字选择；直接回车取消。[/]

[bold underline]输入框按键[/]（敲 jk a 回车后）
  [bold]Ctrl+Shift+V[/]  粘贴文字      [bold]Ctrl+V[/]  粘贴截图
  [bold]回车[/]          发送          [bold]Ctrl+C[/]  取消

[bold underline]图标[/]
  [jk.todo]☐[/] 待办   [jk.doing]…[/] 进行中   [jk.done]✔[/] 完成   [jk.note]●[/] 笔记   [jk.recur]↻[/] 周期   [jk.pri2]![/] 重要   [jk.pri3]!![/] 紧急
  [jk.add]＋[/] 新增   [jk.update]✎[/] 修改   [jk.delete]✖[/] 删除   [jk.dup]≈[/] 已存在，没有重复添加

[bold underline]文件[/]
  记事本  {home}/notebooks/
  配置    {home}/.env  [jk.muted]（在这里填 JK_API_KEY）[/]
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
        err.print("[jk.error]请给出编号[/]，例：jk c 2 3")
        return 2
    try:
        ids = [int(a.lstrip("#")) for a in args]
    except ValueError:
        err.print("[jk.error]编号必须是数字[/]，例：jk c 2 3")
        return 2
    store, books = open_store(cfg)
    found = {i: find_item(books, i) for i in ids}
    missing = [str(i) for i, hit in found.items() if hit is None]
    notes = [str(i) for i, hit in found.items() if hit and hit[1].kind == NOTE]
    recurs = [str(i) for i, hit in found.items() if hit and hit[1].kind == RECUR]
    if missing or notes or recurs:
        if missing:
            err.print(f"[jk.error]找不到编号[/] {' '.join(missing)}")
        if notes:
            err.print(f"[jk.error]这些是笔记，不能标完成[/] {' '.join(notes)}")
        if recurs:
            err.print(f"[jk.error]这些是周期条目，不用标完成，到时间会自动跳到下一次[/] {' '.join(recurs)}")
        return 1
    history.snapshot(store, f"jk c {' '.join(args)}")
    now = fmt_dt(now_minute())
    for _, item in found.values():
        if item.state == DONE:
            item.state, item.done_at = TODO, None
            console.print(f"  [jk.todo]☐ 取消完成[/] {item.id}. {escape(item.text)}")
        else:
            item.state, item.done_at = DONE, now
            console.print(f"  [jk.done]✔ 完成[/] {item.id}. {escape(item.text)}")
    store.save(books)
    render_list(console, books)
    return 0


CHANGE_STYLE = {
    "add": ("＋ 新增", "jk.add"),
    "done": ("✔ 完成", "jk.done"),
    "undone": ("☐ 取消完成", "jk.todo"),
    "update": ("✎ 修改", "jk.update"),
    "delete": ("✖ 删除", "jk.delete"),
    "rename": ("⇄ 记事本", "jk.note"),
    "dup": ("≈ 已存在", "jk.dup"),
}


def print_changes(changes) -> None:
    for ch in changes:
        label, style = CHANGE_STYLE[ch.kind]
        line = f"  [{style}]{label}[/] {escape(ch.text)}"
        if ch.detail:
            line += f"  [jk.muted]{escape(ch.detail)}[/]"
        console.print(line)


def ask_user(question: str, options: list[str]) -> str | None:
    """显示反问与编号选项；返回用户的回答，直接回车返回 None（取消）。"""
    console.print(f"\n  [jk.ask]?[/] {escape(question)}")
    for n, opt in enumerate(options, 1):
        console.print(f"    [bold]{n})[/] {escape(opt)}")
    console.print("  [jk.muted]输入编号，或直接打字回答；直接回车取消[/]")
    reply = console.input("  > ").strip()
    if not reply:
        return None
    if reply.isdigit() and 1 <= int(reply) <= len(options):
        return options[int(reply) - 1]
    return reply


def cmd_ai(cfg: Config, args: list[str]) -> int:
    attachments, words = [], []
    try:
        for arg in args:  # 参数里存在的图片文件当附件
            image = image_from_path(arg)
            (attachments if image else words).append(image or arg)
    except AttachError as exc:
        err.print(f"[jk.error]✖[/] {escape(str(exc))}")
        return 1
    instruction = " ".join(words).strip()
    if instruction or attachments:
        return run_ai(cfg, instruction, attachments)
    if not sys.stdin.isatty():
        err.print("[jk.error]请写上要做的事[/]，例：jk a 明天三点前交作业 a")
        return 2
    composed = compose(cfg.home / "pastes")
    if composed is None:
        return 0
    instruction, attachments, composer = composed
    try:
        return run_ai(cfg, instruction, attachments)
    finally:
        composer.cleanup()  # 发送结束就删掉粘贴文件


def run_ai(cfg: Config, instruction: str, attachments: list) -> int:
    for att in attachments:
        console.print(f"  [jk.muted]已读取{escape(att.describe())}[/]")
    texts = [instruction] + [att.text for att in attachments if att.kind == "text"]
    secret = looks_secret("\n".join(texts))
    if secret:
        err.print(f"  [jk.error]![/] 内容里好像有{secret}，发给 AI 会泄露。")
        if not sys.stdin.isatty() or console.input("  确定还要发送吗？输入 y 发送，其他键取消 > ").strip().lower() != "y":
            console.print("  已取消，什么都没发送。")
            return 1
    store, books = open_store(cfg)
    archive = store.load_archive()
    try:
        conv = Conversation(Client(cfg), books, archive, instruction, now_minute(), attachments)
        while True:
            busy = "AI 正在看图…" if any(a.kind == "image" for a in attachments) else "AI 思考中…"
            with console.status(f"[jk.muted]{busy}[/]", spinner="dots"):
                result = conv.step()
            if not result.ask:
                break
            if not sys.stdin.isatty():
                err.print(f"[jk.doing]AI 需要你确认[/]：{result.ask['question']} {' / '.join(result.ask['options'])}")
                err.print("请把话说得更具体一些再试一次。")
                return 3
            answer = ask_user(result.ask["question"], result.ask["options"])
            if answer is None:
                console.print("  已取消，没有改动。")
                return 0
            conv.answer(answer)
    except AIError as exc:
        err.print(f"[jk.error]✖[/] {escape(str(exc))}")
        return 1
    skipped = skipped_changes(result.skipped, books)
    ops, dups = dedupe(result.ops, books, archive, now_minute())
    changes = []
    if ops:
        label = " ".join([instruction] + [f"[{att.describe()}]" for att in attachments]).strip()
        history.snapshot(store, f"jk a {label}")
        changes = apply(ops, books)
        store.save(books)
    console.print()
    if result.reply:
        console.print(f"  [bold]{escape(result.reply)}[/]")
    print_changes(changes + skipped + dups)
    if changes:
        console.print("  [jk.muted]改错了？用 jk undo 撤销[/]")
        render_list(console, books)
    return 0


def cmd_undo(cfg: Config, args: list[str]) -> int:
    label = history.undo(Store(cfg.home))
    if label is None:
        console.print("  没有可以撤销的改动。")
        return 0
    console.print(f"  [jk.doing]↶ 已撤销[/]：{label}")
    return cmd_list(cfg, [])


def cmd_timeline(cfg: Config, args: list[str]) -> int:
    days = 7
    if args:
        if not args[0].isdigit() or int(args[0]) < 1:
            err.print("[jk.error]天数必须是正整数[/]，例：jk t 14")
            return 2
        days = int(args[0])
    store, books = open_store(cfg)
    render_timeline(console, books, store.load_archive(), days)
    return 0


def cmd_help(cfg: Config, args: list[str]) -> int:
    console.print(HELP.format(home=cfg.home))
    return 0


COMMANDS = {
    "a": cmd_ai,
    "c": cmd_check,
    "t": cmd_timeline,
    "undo": cmd_undo,
    "h": cmd_help,
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
    try:
        return _run(cfg, argv)
    except KeyboardInterrupt:
        err.print("\n  已取消，没有改动。")
        return 130
    except OSError as exc:
        where = exc.filename or cfg.home
        reason = exc.strerror or str(exc)
        err.print(f"[jk.error]✖[/] 读写文件失败：{escape(str(where))}（{escape(reason)}）")
        err.print(f"  请检查数据目录 {escape(str(cfg.home))} 是否存在、有没有写入权限；也可以用 JK_HOME 换一个目录。")
        return 1


def _run(cfg: Config, argv: list[str]) -> int:
    if ensure_env_file(cfg.home):
        console.print(f"  [jk.muted]已生成配置文件 {cfg.env_file}，用 AI 前请填入 JK_API_KEY。[/]")
    try:
        for msg in migrate.ensure(cfg.home):
            console.print(f"  [jk.doing]{escape(msg)}[/]")
    except migrate.FormatError as exc:
        err.print(f"[jk.error]✖[/] {escape(str(exc))}")
        return 1
    if not argv:
        return cmd_list(cfg, [])
    handler = COMMANDS.get(argv[0])
    if handler is None:
        err.print(f"[jk.error]不认识的命令[/] {escape(argv[0])}。想让 AI 处理请用：jk a {escape(' '.join(argv))}；查看帮助：jk h")
        return 2
    return handler(cfg, argv[1:])
