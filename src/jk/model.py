"""数据模型与 Markdown 序列化。

一个记事本 = 一个 Markdown 文件，每个条目占一行：

    - [ ] 完成作业 a <!-- jk id=2 due=2026-10-14T15:00 pri=2 created=2026-10-13T10:00 -->

`[ ]` 待办、`[/]` 进行中、`[x]` 已完成；没有方框的是笔记。
格式细节见 docs/data-format.md。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

FORMAT_VERSION = 1

TASK, NOTE = "task", "note"
TODO, DOING, DONE = "todo", "doing", "done"
STATES = (TODO, DOING, DONE)
BOX = {TODO: " ", DOING: "/", DONE: "x"}
BOX_STATE = {" ": TODO, "/": DOING, "x": DONE, "X": DONE}

_ITEM_RE = re.compile(
    r"^- (?:\[(?P<box>[ xX/])\] )?(?P<text>.*?)\s*(?:<!--\s*jk\b(?P<meta>[^>]*?)-->)?\s*$"
)


def now_minute() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse_due(value: str | None) -> str | None:
    """校验并规范截止时间；接受 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM（秒会被丢弃）。"""
    if value is None or value == "":
        return None
    value = str(value).strip().replace(" ", "T")
    if len(value) == 10:
        return date.fromisoformat(value).isoformat()
    return fmt_dt(datetime.fromisoformat(value))


def due_datetime(due: str) -> datetime:
    """只有日期的截止时间按当天 23:59 计算。"""
    if len(due) == 10:
        return datetime.fromisoformat(due + "T23:59")
    return datetime.fromisoformat(due)


def clean_text(text: str) -> str:
    return " ".join(str(text).replace("<!--", "<!-").replace("-->", "->").split())


@dataclass
class Item:
    id: int
    text: str
    kind: str = TASK
    state: str = TODO
    due: str | None = None
    pri: int = 1
    created: str = ""
    done_at: str | None = None

    @property
    def is_task(self) -> bool:
        return self.kind == TASK

    @property
    def is_open(self) -> bool:
        return self.kind == TASK and self.state != DONE

    def to_line(self) -> str:
        meta = [f"id={self.id}"]
        if self.due:
            meta.append(f"due={self.due}")
        if self.pri != 1:
            meta.append(f"pri={self.pri}")
        if self.created:
            meta.append(f"created={self.created}")
        if self.done_at:
            meta.append(f"done={self.done_at}")
        box = f"[{BOX[self.state]}] " if self.is_task else ""
        return f"- {box}{clean_text(self.text)} <!-- jk {' '.join(meta)} -->"


def parse_item(line: str) -> Item | None:
    """解析一行；不是列表项返回 None。无 jk 注释的列表项（手写的）id 记为 0，保存时补发。"""
    m = _ITEM_RE.match(line.rstrip("\n"))
    if not m or not m.group("text"):
        return None
    meta: dict[str, str] = {}
    for token in (m.group("meta") or "").split():
        if "=" in token:
            k, v = token.split("=", 1)
            meta[k] = v
    box = m.group("box")
    item = Item(
        id=int(meta.get("id", 0) or 0),
        text=clean_text(m.group("text")),
        kind=TASK if box is not None else NOTE,
        state=BOX_STATE[box] if box is not None else TODO,
        pri=min(3, max(1, int(meta.get("pri", 1)))),
        created=meta.get("created", ""),
        done_at=meta.get("done"),
    )
    try:
        item.due = parse_due(meta.get("due"))
    except ValueError:
        item.due = None
    return item


@dataclass
class Notebook:
    name: str
    items: list[Item] = field(default_factory=list)
    created: str = ""
    extra: list[str] = field(default_factory=list)  # 认不出的行原样保留，绝不丢弃
    fmt: int = FORMAT_VERSION

    def to_markdown(self) -> str:
        lines = [
            "---",
            f"jk_format: {FORMAT_VERSION}",
            f"title: {self.name}",
            f"created: {self.created}",
            "---",
            "",
            f"# {self.name}",
            "",
        ]
        lines += [it.to_line() for it in self.items]
        if self.extra:
            lines += ["", *self.extra]
        return "\n".join(lines) + "\n"


def parse_notebook(text: str, fallback_name: str) -> Notebook:
    lines = text.splitlines()
    front: dict[str, str] = {}
    body = lines
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                for raw in lines[1:idx]:
                    if ":" in raw:
                        k, v = raw.split(":", 1)
                        front[k.strip()] = v.strip()
                body = lines[idx + 1 :]
                break
    name = front.get("title") or fallback_name
    nb = Notebook(name=name, created=front.get("created", ""), fmt=int(front.get("jk_format", FORMAT_VERSION)))
    for raw in body:
        stripped = raw.strip()
        if not stripped or stripped == f"# {name}":
            continue
        item = parse_item(stripped)
        if item:
            nb.items.append(item)
        else:
            nb.extra.append(raw)
    return nb
