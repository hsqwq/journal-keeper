"""与 DeepSeek（OpenAI 兼容接口）对话，把一句口语变成改动清单。协议见 docs/ai-protocol.md。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .attach import Attachment
from .config import Config
from .model import NOTE, Notebook
from .ops import ARCHIVE_LOOKBACK_DAYS, PlanError, validate, validate_skipped
from .render import WEEKDAYS

MAX_ROUNDS = 6  # 反问 + 纠错的总轮数上限，防止无限对话
RECENT_ARCHIVE_DAYS = ARCHIVE_LOOKBACK_DAYS

SYSTEM_PROMPT = """\
你是 jk（Journal Keeper）的记事本管家。用户用中文口语给你一句话，你把它变成对记事本的结构化改动，让所有记事本始终条理清晰、一眼能看懂。
用户有语言表达障碍：话可能不完整、有错字、语序乱，请尽力理解真实意图。

你只能输出一个 json 对象，格式固定：
{"reply": "给用户的一句话", "ops": [ ...操作... ], "skipped": [], "ask": null}

需要反问时：
{"reply": "", "ops": [], "ask": {"question": "是哪一个？", "options": ["2. 作业 a", "5. 作业 b"]}}

## 操作（ops 里的元素）
- 新增：{"op": "add", "notebook": "作业", "kind": "task", "text": "完成作业 a", "due": "2026-10-14T15:00", "priority": 1}
  kind 为 task（要做的事）或 note（信息、想法、记录）；due 可为 null；priority 默认 1；可选 "state": "doing"/"done"。
  只有用户明确要求「再加一个一样的」时才写 "allow_duplicate": true，否则程序会拦下和已有条目重复的新增。
- 修改：{"op": "update", "id": 2, ...只写要改的字段...}
  可改字段：text、due（写 null 表示去掉截止）、priority、state（todo/doing/done）、notebook（移到别的记事本）、kind。
- 删除：{"op": "delete", "id": 3}（仅当用户明确要删除/不要了/取消这件事；「做完了」是 state=done，不是删除）
- 记事本改名或合并：{"op": "rename_notebook", "from": "旧名", "to": "新名"}（新名已存在即合并）

## 规则
1. 时间：以「当前时间」和「日历」为准换算相对时间。due 用 YYYY-MM-DDTHH:MM；只知道日期就用 YYYY-MM-DD。
   只说钟点没说日期 → 取最近的将来时刻。1~6 点没说上午/凌晨 → 按下午。「今晚」没钟点 → 当天 YYYY-MM-DD。
2. text：简洁，以动词开头，像待办清单；不要包含截止时间（放进 due）、不要「任务」「提醒我」这类废词；专有名词照抄（例如「作业 a」）。
3. 分本：优先放进已有、合适的记事本；都不合适才新建，名字用 2~4 个字的类别名（如 作业、工作、生活、购物、想法）。实在判断不了放「收件箱」。
4. priority：默认 1；用户说重要 → 2；紧急/很急/马上 → 3。
5. state：开始做/正在做 → doing；做完了/完成了/交了 → done。
6. 指代：用户可能用编号（「任务2」「2号」「#2」「第二个」指编号 2）或内容指代条目。
   只有一个明显匹配 → 直接执行；有多个可能或一个都对不上 → 用 ask 反问，ops 留空。
   options 2~5 个，每个都是一句完整、可以直接执行的回答，候选条目写成「编号. 内容」；对不上时可以给「新建：…」选项。
7. 只改用户要求的内容，不要顺手改别的条目。用户说「整理/归类/合并」时，才可以批量移动、改名、合并记事本、润色文字。
8. 用户只是提问（如「明天要交什么」）→ ops 为空，在 reply 里回答，提到条目时带编号。
9. reply：一句口语短句，说明你做了什么或回答问题；不要逐条复述改动（程序会显示）。
10. 不要编造用户没说的截止时间、优先级或内容。一句话里有多件事就输出多条操作。
11. 用户可能附上「粘贴的文字」或图片（通知、课表、聊天截图等）：读懂其中的文字，按用户的话处理；用户没说要做什么时，
    就把里面每一件要做的事和截止时间提取成任务（一件事一条 add），值得留存的信息记成笔记；已存在的同一件事不要重复添加，必要时 update。
    文字里没写年份时按日历推断最近的将来日期；看不清或没有可提取的内容就在 reply 里说明，ops 留空。
12. 去重：新增前先对照所有已有条目和最近归档，判断是不是同一件事（说法不同也算，例如「实验报告三」和「实验报告 3 请于周五上传」）。
    - 是同一件事且有新信息（截止时间变了、补了地点或要求）→ 用 update 改原条目，不要 add。
    - 是同一件事且没有新信息 → 不要 add，写进 skipped：{"id": 原编号, "reason": "已有，截止时间相同"}。reason 只写客观依据，不要编造记录时间。
    - 和最近归档里已完成的同一件事 → 不要 add，在 reply 里说一声。
    - 截止时间不同的同名事（如每周的周报）是不同的事，可以 add。
"""


@dataclass
class Exchange:
    """一次 jk a 的结果。"""

    reply: str = ""
    ops: list[dict] = field(default_factory=list)
    ask: dict | None = None
    skipped: list[dict] = field(default_factory=list)


def build_context(books: list[Notebook], archive: list[Notebook], now: datetime) -> str:
    calendar = []
    for offset in range(-1, 8):
        d = now.date() + timedelta(days=offset)
        tag = {-1: " 昨天", 0: " 今天", 1: " 明天", 2: " 后天"}.get(offset, "")
        calendar.append(f"{d.isoformat()} 周{WEEKDAYS[d.weekday()]}{tag}")
    notebooks = []
    for nb in books:
        items = []
        for it in nb.items:
            row: dict = {"id": it.id, "kind": it.kind, "text": it.text}
            if it.kind != NOTE:
                row["state"] = it.state
                if it.due:
                    row["due"] = it.due
                if it.pri != 1:
                    row["priority"] = it.pri
            items.append(row)
        notebooks.append({"name": nb.name, "items": items})
    since = (now.date() - timedelta(days=RECENT_ARCHIVE_DAYS)).isoformat()
    archived = [
        {"notebook": nb.name, "text": it.text, "done": it.done_at}
        for nb in archive
        for it in nb.items
        if it.done_at and it.done_at[:10] >= since
    ]
    data = {
        "当前时间": f"{now:%Y-%m-%d %H:%M} 周{WEEKDAYS[now.weekday()]}",
        "日历": calendar,
        "记事本": notebooks,
        "最近归档（只读，无编号，不可修改）": archived,
    }
    return json.dumps(data, ensure_ascii=False)


def parse_response(raw: str, books: list[Notebook]) -> Exchange:
    """解析并校验 AI 输出；不合法抛 PlanError（消息会回传给 AI）。"""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    if not raw:
        raise PlanError("输出为空")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlanError(f"不是合法 json：{exc}") from None
    if not isinstance(data, dict):
        raise PlanError("顶层必须是 json 对象")
    ask = data.get("ask")
    if ask:
        options = ask.get("options") if isinstance(ask, dict) else None
        if not isinstance(ask, dict) or not ask.get("question") or not isinstance(options, list) or not options:
            raise PlanError("ask 必须包含 question 和非空 options 数组")
        return Exchange(reply=str(data.get("reply") or ""), ask={"question": str(ask["question"]), "options": [str(o) for o in options][:9]})
    return Exchange(
        reply=str(data.get("reply") or ""),
        ops=validate(data.get("ops") or [], books),
        skipped=validate_skipped(data.get("skipped"), books),
    )


def user_content(context: str, instruction: str, attachments: list[Attachment]) -> str | list[dict]:
    """首条用户消息；有图片时按多模态格式拼成内容块数组。"""
    text = f"记事本现状：\n{context}\n\n用户的话：{instruction or '（没有说明）'}"
    for att in attachments:
        if att.kind == "text":
            text += f"\n\n用户粘贴的文字（{att.source}）：\n<<<\n{att.text}\n>>>"
    images = [att for att in attachments if att.kind == "image"]
    if not images:
        return text
    text += f"\n\n用户附上了 {len(images)} 张图片，见下方。"
    parts: list[dict] = [{"type": "text", "text": text}]
    for att in images:
        parts.append({"type": "text", "text": f"[{att.source}]"})
        parts.append({"type": "image_url", "image_url": {"url": att.data_url()}})
    return parts


class AIError(RuntimeError):
    """给用户看的错误（网络、Key、模型名等）。"""


class Client:
    def __init__(self, cfg: Config):
        if not cfg.api_key:
            raise AIError(f"还没配置 API Key：请在 {cfg.env_file} 里填写 JK_API_KEY=")
        from openai import OpenAI

        self.cfg = cfg
        self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout, max_retries=2)

    def complete(self, messages: list[dict]) -> str:
        import openai

        params = dict(model=self.cfg.model, messages=messages, temperature=0.2, max_tokens=4096,
                      response_format={"type": "json_object"})
        try:
            try:
                resp = self._client.chat.completions.create(**params)
            except openai.BadRequestError:
                # 部分模型/接口在多模态时不接受 JSON 模式：去掉再试一次，输出仍由 parse_response 校验
                if not _has_image(messages):
                    raise
                params.pop("response_format")
                resp = self._client.chat.completions.create(**params)
        except openai.AuthenticationError:
            raise AIError(f"API Key 无效，请检查 {self.cfg.env_file} 里的 JK_API_KEY") from None
        except openai.NotFoundError:
            raise AIError(f"找不到模型或地址：JK_MODEL={self.cfg.model}，JK_BASE_URL={self.cfg.base_url}") from None
        except openai.APITimeoutError:
            raise AIError(f"AI 超过 {self.cfg.timeout:.0f} 秒没回应，请稍后再试") from None
        except openai.APIConnectionError:
            raise AIError(f"连不上 {self.cfg.base_url}，请检查网络") from None
        except openai.APIStatusError as exc:
            raise AIError(f"AI 服务报错（HTTP {exc.status_code}）：{exc.message}") from None
        return resp.choices[0].message.content or ""


def _has_image(messages: list[dict]) -> bool:
    return any(isinstance(m["content"], list) for m in messages)


class Conversation:
    """一次 jk a 的多轮对话：反问 → 用户回答 → 再问 AI；输出不合法时让 AI 自己改正。"""

    def __init__(self, client, books: list[Notebook], archive: list[Notebook], instruction: str, now: datetime,
                 attachments: list[Attachment] = ()):
        self.client = client
        self.books = books
        self.rounds = 0
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content(build_context(books, archive, now), instruction, list(attachments))},
        ]

    def step(self) -> Exchange:
        last_error = ""
        while self.rounds < MAX_ROUNDS:
            self.rounds += 1
            raw = self.client.complete(self.messages)
            try:
                result = parse_response(raw, self.books)
            except PlanError as exc:
                last_error = str(exc)
                if raw.strip():
                    self.messages.append({"role": "assistant", "content": raw})
                self.messages.append({"role": "user", "content": f"你的输出有错误：{exc}。请改正后重新输出完整的 json。"})
                continue
            self.messages.append({"role": "assistant", "content": raw})
            return result
        raise AIError(f"AI 多次输出不合格，已放弃，没有任何改动（最后的错误：{last_error}）")

    def answer(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"我的回答：{text}"})
