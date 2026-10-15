"""AI 改动清单的校验与执行。

AI 只能返回下面四种操作，程序逐条校验，全部合法才执行（要么全改、要么不改）：
  add / update / delete / rename_notebook
协议细节见 docs/ai-protocol.md。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from .model import DONE, KINDS, NOTE, PROGRAM_BOOKS, RECUR, RECUR_BOOK, STATES, UCLOUD_BOOK, TASK, Item, Notebook, clean_text, fmt_dt, now_minute, parse_due
from .recur import describe, parse_rule
from .store import find_item, get_notebook, next_free_id

MAX_NAME = 20
ARCHIVE_LOOKBACK_DAYS = 30  # AI 能看到、去重会对比的归档范围
SIMILAR = 0.85  # 文字相似度阈值（0~1）


class PlanError(ValueError):
    """AI 返回的内容不合法。消息会回传给 AI 让它改正。"""


@dataclass
class Change:
    """一条给人看的改动说明。"""

    kind: str  # add / update / done / undone / delete / rename
    text: str
    detail: str = ""


def _name(value) -> str:
    name = clean_text(value or "")
    if not name or len(name) > MAX_NAME or name.startswith("."):
        raise PlanError(f"记事本名不合法：{value!r}（1-{MAX_NAME} 字）")
    return name


def _pri(value) -> int:
    try:
        pri = int(value)
    except (TypeError, ValueError):
        raise PlanError(f"priority 必须是 1/2/3：{value!r}") from None
    if pri not in (1, 2, 3):
        raise PlanError(f"priority 必须是 1/2/3：{value!r}")
    return pri


def _due(value) -> str | None:
    try:
        return parse_due(value)
    except (TypeError, ValueError):
        raise PlanError(f"due 格式不对：{value!r}（用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM）") from None


def _every(value) -> str:
    try:
        return str(parse_rule(value))
    except ValueError as exc:
        raise PlanError(f"every 不对：{exc}") from None


def _kind(value) -> str:
    if value not in KINDS:
        raise PlanError(f"kind 只能是 task / note / recur：{value!r}")
    return value


def _text(value) -> str:
    text = clean_text(value or "")
    if not text:
        raise PlanError("text 不能为空")
    return text


def validate(ops, books: list[Notebook]) -> list[dict]:
    """校验并规范化；不修改 books。"""
    if not isinstance(ops, list):
        raise PlanError("ops 必须是数组")
    kinds = {it.id: it.kind for nb in books for it in nb.items}
    ids = set(kinds)
    names = {nb.name for nb in books}
    deleted: set[int] = set()
    out = []
    for n, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            raise PlanError(f"第 {n} 条操作不是对象")
        kind = op.get("op")
        if kind == "add":
            item_kind = _kind(op.get("kind", TASK))
            if item_kind == RECUR:
                out.append({
                    "op": "add", "notebook": RECUR_BOOK, "kind": RECUR, "text": _text(op.get("text")),
                    "every": _every(op.get("every")), "due": None, "priority": 1, "state": "todo",
                    "allow_duplicate": op.get("allow_duplicate") is True,
                })
                continue
            notebook = _name(op.get("notebook"))
            if notebook == RECUR_BOOK:
                raise PlanError(f"「{RECUR_BOOK}」记事本只放周期条目（kind=recur）")
            if notebook == UCLOUD_BOOK:
                raise PlanError(f"「{UCLOUD_BOOK}」记事本只放 jk u 从教学云平台同步来的待办，请放进别的记事本")
            state = op.get("state", "todo")
            if state not in STATES:
                raise PlanError(f"state 只能是 {'/'.join(STATES)}：{state!r}")
            out.append({
                "op": "add",
                "notebook": notebook,
                "kind": item_kind,
                "text": _text(op.get("text")),
                "due": _due(op.get("due")) if item_kind == TASK else None,
                "priority": _pri(op.get("priority", 1)),
                "state": state if item_kind == TASK else "todo",
                "allow_duplicate": op.get("allow_duplicate") is True,
            })
        elif kind in ("update", "delete"):
            try:
                item_id = int(op.get("id"))
            except (TypeError, ValueError):
                raise PlanError(f"第 {n} 条操作缺少有效 id") from None
            if item_id not in ids or item_id in deleted:
                raise PlanError(f"编号 {item_id} 不存在")
            if kind == "delete":
                deleted.add(item_id)
                out.append({"op": "delete", "id": item_id})
                continue
            clean: dict = {"op": "update", "id": item_id}
            if kinds[item_id] == RECUR:
                extra = sorted(set(op) - {"op", "id", "text", "every"})
                if extra:
                    raise PlanError(f"编号 {item_id} 是周期条目，只能改 text 和 every，不能改 {'/'.join(extra)}；不要了就 delete")
                if "text" in op:
                    clean["text"] = _text(op["text"])
                if "every" in op:
                    clean["every"] = _every(op["every"])
                if len(clean) == 2:
                    raise PlanError(f"编号 {item_id} 的 update 没有要改的字段")
                out.append(clean)
                continue
            if "every" in op:
                raise PlanError(f"编号 {item_id} 不是周期条目，不能设 every；要变成周期请 delete 后用 kind=recur 重新 add")
            if "text" in op:
                clean["text"] = _text(op["text"])
            if "due" in op:
                clean["due"] = _due(op["due"])
            if "priority" in op:
                clean["priority"] = _pri(op["priority"])
            if "state" in op:
                if op["state"] not in STATES:
                    raise PlanError(f"state 只能是 {'/'.join(STATES)}：{op['state']!r}")
                clean["state"] = op["state"]
            if "notebook" in op:
                clean["notebook"] = _name(op["notebook"])
                if clean["notebook"] in PROGRAM_BOOKS:
                    raise PlanError(f"「{clean['notebook']}」记事本由程序管理，不能把条目移进去")
            if "kind" in op:
                if _kind(op["kind"]) == RECUR:
                    raise PlanError("不能把任务或笔记改成周期；请 delete 后用 kind=recur 重新 add")
                clean["kind"] = op["kind"]
            if len(clean) == 2:
                raise PlanError(f"编号 {item_id} 的 update 没有要改的字段")
            out.append(clean)
        elif kind == "rename_notebook":
            old = op.get("from")
            if old not in names:
                raise PlanError(f"记事本 {old!r} 不存在")
            new = _name(op.get("to"))
            for name in (old, new):
                if name in PROGRAM_BOOKS:
                    raise PlanError(f"「{name}」记事本由程序管理，不能改名或合并")
            names.discard(old)
            names.add(new)
            out.append({"op": "rename_notebook", "from": old, "to": new})
        else:
            raise PlanError(f"未知操作 {kind!r}（只允许 add/update/delete/rename_notebook）")
    return out


def _describe_due(due: str | None) -> str:
    return due.replace("T", " ") if due else "无"


def apply(ops: list[dict], books: list[Notebook]) -> list[Change]:
    """在 books 上执行已校验的操作，返回改动说明。"""
    now = fmt_dt(now_minute())
    used = {it.id for nb in books for it in nb.items}
    changes: list[Change] = []
    for op in ops:
        kind = op["op"]
        if kind == "add":
            item = Item(
                id=next_free_id(used),
                text=op["text"],
                kind=op["kind"],
                state=op["state"],
                due=op["due"],
                pri=op["priority"],
                created=now,
                done_at=now if op["state"] == DONE else None,
                every=op.get("every"),
            )
            used.add(item.id)
            get_notebook(books, op["notebook"]).items.append(item)
            extra = [f"[{op['notebook']}]"]
            if item.every:
                extra.append(describe(parse_rule(item.every)))
            if item.due:
                extra.append(f"截止 {_describe_due(item.due)}")
            changes.append(Change("add", f"{item.id}. {item.text}", " ".join(extra)))
        elif kind == "delete":
            nb, item = find_item(books, op["id"])
            nb.items.remove(item)
            changes.append(Change("delete", f"{item.id}. {item.text}"))
        elif kind == "update":
            nb, item = find_item(books, op["id"])
            notes = []
            if "text" in op and op["text"] != item.text:
                notes.append(f"内容「{item.text}」→「{op['text']}」")
                item.text = op["text"]
            if "every" in op and op["every"] != item.every:
                notes.append(f"{describe(parse_rule(item.every))} → {describe(parse_rule(op['every']))}")
                item.every = op["every"]
            if "due" in op and op["due"] != item.due:
                notes.append(f"截止 {_describe_due(item.due)} → {_describe_due(op['due'])}")
                item.due = op["due"]
            if "priority" in op and op["priority"] != item.pri:
                notes.append(f"优先级 {item.pri} → {op['priority']}")
                item.pri = op["priority"]
            if "kind" in op and op["kind"] != item.kind:
                notes.append("改为笔记" if op["kind"] == NOTE else "改为任务")
                item.kind = op["kind"]
            if "notebook" in op and op["notebook"] != nb.name:
                notes.append(f"移到 [{op['notebook']}]")
                nb.items.remove(item)
                get_notebook(books, op["notebook"]).items.append(item)
            state_change = None
            if "state" in op and op["state"] != item.state:
                if op["state"] == DONE:
                    state_change, item.done_at = "done", now
                elif item.state == DONE:
                    state_change, item.done_at = "undone", None
                else:
                    notes.append("开始进行" if op["state"] == "doing" else "改回待办")
                item.state = op["state"]
            if state_change:
                changes.append(Change(state_change, f"{item.id}. {item.text}", "；".join(notes)))
            elif notes:
                changes.append(Change("update", f"{item.id}. {item.text}", "；".join(notes)))
        elif kind == "rename_notebook":
            src = get_notebook(books, op["from"], create=False)
            dst = get_notebook(books, op["to"], create=False)
            if dst and dst is not src:  # 改成已有名字 = 合并
                dst.items.extend(src.items)
                src.items = []
                dst.extra.extend(src.extra)
                src.extra = []
                changes.append(Change("rename", f"[{op['from']}] 合并到 [{op['to']}]"))
            else:
                src.name = op["to"]
                changes.append(Change("rename", f"[{op['from']}] 改名为 [{op['to']}]"))
    return changes


# ---------- 去重 ----------

def normalize(text: str) -> str:
    """去掉空格和标点、统一全半角与大小写，只留文字和数字。"""
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(ch for ch in text if ch.isalnum())


def similar(a: str, b: str) -> bool:
    """保守判断两句话是不是同一件事。

    数字和英文字母必须完全一致（「作业4」和「作业5」不是同一件事），其余文字相似度 >= SIMILAR。
    换了说法的重复交给 AI 判断，这里只拦明显的。
    """
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if re.findall(r"[0-9a-z]+", a) != re.findall(r"[0-9a-z]+", b):
        return False
    return SequenceMatcher(None, a, b).ratio() >= SIMILAR


def _when(item_or_op) -> str | None:
    """去重比较用的时间键：任务是截止日期，周期是规则。"""
    every = item_or_op.get("every") if isinstance(item_or_op, dict) else item_or_op.every
    due = item_or_op.get("due") if isinstance(item_or_op, dict) else item_or_op.due
    return f"R:{every}" if every else due


def _same_due(a: str | None, b: str | None) -> bool:
    """截止时间一样，或者有一方没写，才算同一件事；截止不同（例如每周的周报）不算重复。周期要求规则完全一样。"""
    if (a or "").startswith("R:") or (b or "").startswith("R:"):
        return a == b
    return a is None or b is None or a[:10] == b[:10]


def dedupe(ops: list[dict], books: list[Notebook], archive: list[Notebook], now: datetime) -> tuple[list[dict], list[Change]]:
    """程序兜底去重：拦下和已有条目、近期归档、或同一批里前面条目重复的 add。返回（剩下的操作，跳过说明）。"""
    since = (now.date() - timedelta(days=ARCHIVE_LOOKBACK_DAYS)).isoformat()
    existing = [(it.kind, it.text, _when(it), f"{it.id}. {it.text}", "") for nb in books for it in nb.items]
    existing += [
        (it.kind, it.text, _when(it), it.text, f"已于 {it.done_at[:10]} 完成并归档")
        for nb in archive
        for it in nb.items
        if it.done_at and it.done_at[:10] >= since
    ]
    kept, skipped = [], []
    for op in ops:
        if op["op"] != "add" or op.get("allow_duplicate"):
            kept.append(op)
            continue
        match = next(
            (e for e in existing if e[0] == op["kind"] and similar(e[1], op["text"]) and _same_due(e[2], _when(op))),
            None,
        )
        if match:
            reason = match[4] or f"和「{op['text']}」重复，没有再添加"
            skipped.append(Change("dup", match[3], reason))
            continue
        kept.append(op)
        existing.append((op["kind"], op["text"], _when(op), op["text"], "同一次里重复出现"))
    return kept, skipped


def skipped_changes(skipped: list[dict], books: list[Notebook]) -> list[Change]:
    """AI 自己报告的「已存在、没添加」。"""
    result = []
    for entry in skipped:
        hit = find_item(books, entry["id"])
        if hit:
            result.append(Change("dup", f"{hit[1].id}. {hit[1].text}", entry.get("reason", "")))
    return result


def validate_skipped(raw, books: list[Notebook]) -> list[dict]:
    """skipped 只是说明，不合法的条目直接丢掉，不让 AI 重来。"""
    if not isinstance(raw, list):
        return []
    ids = {it.id for nb in books for it in nb.items}
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            item_id = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id in ids and item_id not in {e["id"] for e in out}:
            out.append({"id": item_id, "reason": clean_text(entry.get("reason") or "")})
    return out
