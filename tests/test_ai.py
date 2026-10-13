import json
from datetime import datetime

import pytest

from jk import ai, cli
from jk.ai import AIError, Conversation, build_context, parse_response
from jk.model import DONE, Item, Notebook
from jk.ops import PlanError

NOW = datetime(2026, 10, 13, 18, 0)


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages):
        self.seen.append([dict(m) for m in messages])
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def books():
    return [Notebook("作业", [Item(1, "作业 a"), Item(2, "作业 b")])]


def test_context_has_calendar_and_items():
    ctx = json.loads(build_context(books(), [Notebook("作业", [Item(1, "旧", state=DONE, done_at="2026-10-12T10:00")])], NOW))
    assert ctx["当前时间"] == "2026-10-13 18:00 周二"
    assert "2026-10-14 周三 明天" in ctx["日历"]
    assert ctx["记事本"][0]["items"][0] == {"id": 1, "kind": "task", "text": "作业 a", "state": "todo"}
    assert ctx["最近归档（只读，无编号，不可修改）"][0]["text"] == "旧"


def test_parse_response_variants():
    assert parse_response('```json\n{"reply":"好","ops":[]}\n```', books()).reply == "好"
    ex = parse_response('{"ask":{"question":"哪个？","options":["1. 作业 a","2. 作业 b"]}}', books())
    assert ex.ask["options"] == ["1. 作业 a", "2. 作业 b"]
    for bad in ("", "nope", "[]", '{"ask":{"question":"q","options":[]}}', '{"ops":[{"op":"delete","id":9}]}'):
        with pytest.raises(PlanError):
            parse_response(bad, books())


def test_conversation_self_corrects():
    client = FakeClient("", {"ops": [{"op": "delete", "id": 9}]}, {"reply": "好", "ops": [{"op": "delete", "id": 1}]})
    result = Conversation(client, books(), [], "删掉作业 a", NOW).step()
    assert result.ops == [{"op": "delete", "id": 1}]
    assert "编号 9 不存在" in client.seen[-1][-1]["content"]


def test_conversation_gives_up(monkeypatch):
    monkeypatch.setattr(ai, "MAX_ROUNDS", 2)
    with pytest.raises(AIError, match="没有任何改动"):
        Conversation(FakeClient("x", "y"), books(), [], "?", NOW).step()


# ---------- jk a 端到端（假 AI） ----------

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("JK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("JK_API_KEY", "test")
    return tmp_path / "home"


def use_fake(monkeypatch, *replies):
    fake = FakeClient(*replies)
    monkeypatch.setattr(cli, "Client", lambda cfg: fake)
    return fake


def test_jk_a_adds_task_and_undo(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"reply": "记下了", "ops": [{"op": "add", "notebook": "作业", "text": "完成作业 a", "due": "2026-10-14T15:00"}]})
    assert cli.main(["a", "明天三点前交作业a"]) == 0
    out = capsys.readouterr().out
    assert "记下了" in out and "＋ 新增" in out and "完成作业 a" in out
    assert "完成作业 a" in (env / "notebooks" / "作业.md").read_text()
    assert cli.main(["undo"]) == 0
    assert not (env / "notebooks" / "作业.md").exists()


def test_jk_a_asks_and_user_picks(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"reply": "", "ops": [{"op": "add", "notebook": "作业", "text": "作业 a"}, {"op": "add", "notebook": "作业", "text": "作业 b"}]})
    cli.main(["a", "两个作业"])
    fake = use_fake(
        monkeypatch,
        {"ask": {"question": "哪个？", "options": ["1. 作业 a", "2. 作业 b"]}},
        {"reply": "好", "ops": [{"op": "update", "id": 2, "state": "done"}]},
    )
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.console, "input", lambda prompt="": "2")
    assert cli.main(["a", "作业做完了"]) == 0
    assert fake.seen[-1][-1]["content"] == "我的回答：2. 作业 b"
    assert "- [x] 作业 b" in (env / "notebooks" / "作业.md").read_text()


def test_jk_a_ask_cancel_changes_nothing(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"ask": {"question": "哪个？", "options": ["a", "b"]}})
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.console, "input", lambda prompt="": "")
    assert cli.main(["a", "x"]) == 0
    assert "已取消" in capsys.readouterr().out
    assert not (env / "history").exists()


def test_jk_a_question_only_no_snapshot(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"reply": "明天没有要交的", "ops": []})
    assert cli.main(["a", "明天要交什么"]) == 0
    assert "明天没有要交的" in capsys.readouterr().out
    assert not (env / "history").exists()


def test_jk_a_without_key(env, monkeypatch, capsys):
    monkeypatch.delenv("JK_API_KEY")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert cli.main(["a", "x"]) == 1
    assert "JK_API_KEY" in capsys.readouterr().err
