"""周期规则：每天 / 工作日 / 每周几（可多天）/ 每月几号，可带钟点。

规则字符串（存进 Markdown 的 every= 和 AI 协议里都用它）：
    daily@07:00        每天 07:00
    weekdays@08:00     工作日（周一到周五）08:00
    weekly:1,3@16:00   每周一、三 16:00（1=周一 … 7=周日）
    monthly:15         每月 15 号（全天）
不写 @HH:MM 表示全天。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAYS = "一二三四五六日"
SEARCH_DAYS = 62  # 找下一次最多往后看两个月（每月 31 号也够用）


@dataclass(frozen=True)
class Rule:
    freq: str  # daily / weekdays / weekly / monthly
    days: tuple[int, ...] = ()  # weekly: 1-7；monthly: 1-31
    at: str | None = None  # "HH:MM"，None = 全天

    def __str__(self) -> str:
        head = self.freq
        if self.freq in ("weekly", "monthly"):
            head += ":" + ",".join(str(d) for d in self.days)
        return head + (f"@{self.at}" if self.at else "")


def parse_rule(text: str) -> Rule:
    """解析并规范化；不合法抛 ValueError（消息给 AI 看）。"""
    raw = str(text or "").strip().lower().replace(" ", "")
    head, _, at = raw.partition("@")
    if at:
        try:
            hour, minute = (int(x) for x in at.split(":"))
            at = time(hour, minute).strftime("%H:%M")
        except ValueError:
            raise ValueError(f"钟点格式不对：{at!r}（用 HH:MM）") from None
    freq, _, days_text = head.partition(":")
    days: tuple[int, ...] = ()
    if freq in ("weekly", "monthly"):
        try:
            days = tuple(sorted({int(d) for d in days_text.split(",") if d}))
        except ValueError:
            raise ValueError(f"日期列表不对：{days_text!r}") from None
        limit = 7 if freq == "weekly" else 31
        if not days or any(d < 1 or d > limit for d in days):
            raise ValueError(f"{freq} 需要 1-{limit} 之间的数字，例：{freq}:1")
        if freq == "weekly" and days == (1, 2, 3, 4, 5):
            freq, days = "weekdays", ()
        elif freq == "weekly" and len(days) == 7:
            freq, days = "daily", ()
    elif freq not in ("daily", "weekdays") or days_text:
        raise ValueError(
            f"规则不认识：{text!r}（只支持 daily / weekdays / weekly:1,3 / monthly:15，可加 @HH:MM）"
        )
    return Rule(freq, days, at or None)


def matches(rule: Rule, d: date) -> bool:
    if rule.freq == "daily":
        return True
    if rule.freq == "weekdays":
        return d.weekday() < 5
    if rule.freq == "weekly":
        return d.isoweekday() in rule.days
    # monthly：本月没有这一天（如 2 月 30 号）就落在月底
    last = calendar.monthrange(d.year, d.month)[1]
    return d.day in rule.days or (d.day == last and any(day > last for day in rule.days))


def _moment(rule: Rule, d: date) -> datetime:
    """这一天的发生时刻；全天的按当天 23:59 算「还没过去」。"""
    return datetime.combine(d, time.fromisoformat(rule.at or "23:59"))


def occurrences(rule: Rule, now: datetime, until: datetime) -> list[datetime]:
    """now 之后（含正在进行的当天全天事件）到 until 之间的每一次；全天事件返回当天 00:00。"""
    result = []
    d = now.date()
    while datetime.combine(d, time.min) <= until:
        start = datetime.combine(d, time.fromisoformat(rule.at)) if rule.at else datetime.combine(d, time.min)
        if matches(rule, d) and _moment(rule, d) >= now and start <= until:
            result.append(start)
        d += timedelta(days=1)
    return result


def next_occurrence(rule: Rule, now: datetime) -> datetime | None:
    found = occurrences(rule, now, now + timedelta(days=SEARCH_DAYS))
    return found[0] if found else None


def describe(rule: Rule) -> str:
    """给人看的规则：每周一、三 16:00 / 工作日 08:00 / 每月 15 号。"""
    if rule.freq == "daily":
        text = "每天"
    elif rule.freq == "weekdays":
        text = "工作日"
    elif rule.freq == "weekly":
        text = "每周" + "、".join(WEEKDAYS[d - 1] for d in rule.days)
    else:
        text = "每月 " + "、".join(str(d) for d in rule.days) + " 号"
    return f"{text} {rule.at}" if rule.at else text
