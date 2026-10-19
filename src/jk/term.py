"""教学周：只记录「第 1 周从哪个周一开始」，当前是第几周由日期算出来，跨天跨月都不会错。

设置方式：对 AI 说「现在是第 8 周」，AI 输出 set_week 操作，程序按今天倒推第 1 周的周一；
也可以说「第一周从 9 月 1 日开始」，程序会归到那一周的周一。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import Config
from .state import read, update

MAX_WEEK = 30


class TermError(ValueError):
    """设置不合法；消息会回传给 AI。"""


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True)
class Term:
    week1_start: date  # 第 1 周的周一

    def week(self, today: date) -> int | None:
        """今天是第几周；还没开学返回 None。"""
        offset = (today - self.week1_start).days
        return offset // 7 + 1 if offset >= 0 else None

    def start_of(self, week: int) -> date:
        return self.week1_start + timedelta(weeks=week - 1)


def load(cfg: Config) -> Term | None:
    raw = read(cfg).get("term") or {}
    try:
        return Term(date.fromisoformat(raw["week1_start"]))
    except (KeyError, TypeError, ValueError):
        return None


def parse_op(op: dict, now: datetime) -> dict:
    """校验 AI 的 set_week 操作，返回要保存的 {week1_start, week}；不合法抛 TermError。"""
    start = op.get("week1_start")
    week = op.get("week")
    if start:
        try:
            week1_start = monday(date.fromisoformat(str(start)))
        except ValueError:
            raise TermError(f"week1_start 必须是 YYYY-MM-DD：{start!r}") from None
        week = Term(week1_start).week(now.date())
        if week is None:
            raise TermError("week1_start 在未来，请检查日期")
    elif week is not None:
        try:
            week = int(week)
        except (TypeError, ValueError):
            raise TermError(f"week 必须是整数：{week!r}") from None
        if not 1 <= week <= MAX_WEEK:
            raise TermError(f"week 必须在 1-{MAX_WEEK} 之间：{week}")
        week1_start = monday(now.date()) - timedelta(weeks=week - 1)
    else:
        raise TermError("set_week 需要 week 或 week1_start")
    return {"week1_start": week1_start.isoformat(), "week": week}


def save(cfg: Config, values: dict) -> Term:
    update(cfg, term={"week1_start": values["week1_start"]})
    return Term(date.fromisoformat(values["week1_start"]))
