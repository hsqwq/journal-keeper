from datetime import date, datetime

import pytest

from jk import term
from jk.config import load_config
from jk.term import Term, TermError, monday, parse_op

NOW = datetime(2026, 10, 19, 9, 30)  # 周一


def cfg_for(tmp_path, monkeypatch):
    monkeypatch.setenv("JK_HOME", str(tmp_path))
    return load_config()


def test_monday_and_week():
    assert monday(date(2026, 10, 19)) == date(2026, 10, 19)
    assert monday(date(2026, 10, 25)) == date(2026, 10, 19)
    t = Term(date(2026, 8, 31))
    assert t.week(date(2026, 8, 31)) == 1
    assert t.week(date(2026, 9, 6)) == 1  # 周日仍算第 1 周
    assert t.week(date(2026, 9, 7)) == 2
    assert t.week(date(2026, 10, 19)) == 8
    assert t.week(date(2026, 8, 30)) is None  # 还没开学
    assert t.start_of(8) == date(2026, 10, 19)


def test_parse_op_from_week():
    assert parse_op({"week": 8}, NOW) == {"week1_start": "2026-08-31", "week": 8}
    assert parse_op({"week": "1"}, NOW)["week1_start"] == "2026-10-19"


def test_parse_op_explicit_start_snaps_to_monday():
    values = parse_op({"week1_start": "2026-09-01"}, NOW)  # 周二 → 归到周一 8/31
    assert values == {"week1_start": "2026-08-31", "week": 8}


def test_parse_op_rejects():
    for bad, msg in (({}, "需要"), ({"week": 0}, "1-30"), ({"week": 31}, "1-30"),
                     ({"week": "八"}, "整数"), ({"week1_start": "9月1日"}, "YYYY-MM-DD"),
                     ({"week1_start": "2027-01-01"}, "未来")):
        with pytest.raises(TermError, match=msg):
            parse_op(bad, NOW)


def test_save_and_load(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path, monkeypatch)
    assert term.load(cfg) is None
    term.save(cfg, {"week1_start": "2026-08-31", "week": 8})
    loaded = term.load(cfg)
    assert loaded == Term(date(2026, 8, 31))
    assert loaded.week(NOW.date()) == 8


def test_corrupt_state_is_ignored(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path, monkeypatch)
    (tmp_path / "state.json").write_text('{"term": {"week1_start": "bad"}}')
    assert term.load(cfg) is None
