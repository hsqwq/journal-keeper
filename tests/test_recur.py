from datetime import datetime

import pytest

from jk.recur import describe, next_occurrence, occurrences, parse_rule

# 2026-10-13 是周二
NOW = datetime(2026, 10, 13, 18, 0)


@pytest.mark.parametrize("text,canon,human", [
    ("daily@7:00", "daily@07:00", "每天 07:00"),
    ("weekdays@08:00", "weekdays@08:00", "工作日 08:00"),
    ("weekly:3,1@16:00", "weekly:1,3@16:00", "每周一、三 16:00"),
    ("weekly:1,2,3,4,5@8:00", "weekdays@08:00", "工作日 08:00"),
    ("weekly:1,2,3,4,5,6,7", "daily", "每天"),
    ("monthly:15", "monthly:15", "每月 15 号"),
    (" Weekly : 2 @ 16:00 ", "weekly:2@16:00", "每周二 16:00"),
])
def test_parse_and_describe(text, canon, human):
    rule = parse_rule(text)
    assert str(rule) == canon and describe(rule) == human
    assert parse_rule(str(rule)) == rule


@pytest.mark.parametrize("bad", ["", "yearly", "weekly", "weekly:8", "monthly:0", "monthly:32", "daily@25:00", "daily:1", "weekly:x"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_next_occurrence_weekly():
    rule = parse_rule("weekly:1@08:00")
    assert next_occurrence(rule, NOW) == datetime(2026, 10, 19, 8, 0)


def test_today_passed_skips_to_next():
    rule = parse_rule("weekly:2@16:00")  # 今天周二 16:00 已过
    assert next_occurrence(rule, NOW) == datetime(2026, 10, 20, 16, 0)
    assert next_occurrence(rule, datetime(2026, 10, 13, 15, 59)) == datetime(2026, 10, 13, 16, 0)


def test_all_day_counts_until_end_of_day():
    assert next_occurrence(parse_rule("daily"), NOW) == datetime(2026, 10, 13)


def test_weekdays_skip_weekend():
    days = [d.day for d in occurrences(parse_rule("weekdays@08:00"), datetime(2026, 10, 16, 9), datetime(2026, 10, 21))]
    assert days == [19, 20]


def test_monthly_end_of_month_fallback():
    rule = parse_rule("monthly:31")
    assert next_occurrence(rule, datetime(2026, 11, 1)) == datetime(2026, 11, 30)
    assert next_occurrence(rule, datetime(2026, 2, 1)) == datetime(2026, 2, 28)
    assert next_occurrence(parse_rule("monthly:15"), NOW) == datetime(2026, 10, 15)


def test_occurrences_window():
    found = occurrences(parse_rule("weekly:2,4@16:00"), NOW, datetime(2026, 10, 20, 23, 59))
    assert found == [datetime(2026, 10, 15, 16), datetime(2026, 10, 20, 16)]
