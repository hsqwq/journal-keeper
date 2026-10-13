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


# ---------- 附件（粘贴文字 / 图片） ----------

from jk import attach  # noqa: E402
from jk.ai import user_content  # noqa: E402
from jk.attach import Attachment  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def test_user_content_text_and_image():
    text = Attachment(kind="text", text="周五交实验报告", source="剪贴板")
    assert "周五交实验报告" in user_content("{}", "", [text])
    assert "（没有说明）" in user_content("{}", "", [text])
    img = Attachment(kind="image", data=PNG, mime="image/png", source="剪贴板")
    parts = user_content("{}", "这是作业", [img])
    assert parts[0]["type"] == "text" and "1 张图片" in parts[0]["text"]
    assert parts[1]["text"] == "[剪贴板]"
    assert parts[2]["image_url"]["url"].startswith("data:image/png;base64,")


def test_jk_a_with_image_path(env, monkeypatch, tmp_path, capsys):
    img = tmp_path / "通知.png"
    img.write_bytes(PNG)
    fake = use_fake(monkeypatch, {"reply": "图里没有任务", "ops": []})
    assert cli.main(["a", "看看", str(img), "有什么作业"]) == 0
    first = fake.seen[0][1]["content"]
    assert isinstance(first, list) and "用户的话：看看 有什么作业" in first[0]["text"]


def test_json_mode_fallback_only_with_images(monkeypatch):
    import openai

    from jk.config import Config

    calls = []

    class Completions:
        def create(self, **params):
            calls.append(params)
            if "response_format" in params:
                exc = openai.BadRequestError.__new__(openai.BadRequestError)  # 绕开依赖具体 HTTP 库的构造函数
                exc.status_code, exc.message = 400, "no json mode"
                raise exc
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "{}"})()})()]})()

    cfg = Config(home=None, api_key="k", base_url="http://x", model="m", archive_after_days=1, timeout=5)
    client = ai.Client(cfg)
    client._client = type("O", (), {"chat": type("Ch", (), {"completions": Completions()})()})()
    with_image = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
    assert client.complete(with_image) == "{}"
    assert "response_format" not in calls[-1]
    with pytest.raises(AIError, match="400"):
        client.complete([{"role": "user", "content": "x"}])


def test_secret_blocked_before_sending(env, monkeypatch, capsys):
    fake = use_fake(monkeypatch)  # 没有预置回复：一旦调用 AI 就会报错
    assert cli.main(["a", "记一下", "sk-" + "a1b2c3d4" * 4]) == 1
    assert fake.seen == [] and "什么都没发送" in capsys.readouterr().out


def test_secret_sent_only_after_yes(env, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.console, "input", lambda prompt="": "y")
    fake = use_fake(monkeypatch, {"reply": "好", "ops": []})
    assert cli.main(["a", "我的密码：abc 记一下"]) == 0
    assert len(fake.seen) == 1


# ---------- 去重显示 / 帮助 / 文件错误 ----------

def test_jk_a_shows_duplicates_and_skips_snapshot(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"reply": "", "ops": [{"op": "add", "notebook": "作业", "text": "交实验报告三"}]})
    cli.main(["a", "x"])
    capsys.readouterr()
    use_fake(monkeypatch, {"reply": "图里都记过了", "skipped": [{"id": 1, "reason": "已经记过"}],
                           "ops": [{"op": "add", "notebook": "作业", "text": "交实验报告三。"}]})
    snaps_before = len(list((env / "history").iterdir()))
    assert cli.main(["a", "y"]) == 0
    out = capsys.readouterr().out
    assert out.count("≈ 已存在") == 2 and "＋ 新增" not in out
    assert len(list((env / "history").iterdir())) == snaps_before  # 没有真改动，不拍快照


def test_jk_h_chinese_help(env, capsys):
    assert cli.main(["h"]) == 0
    out = capsys.readouterr().out
    for word in ("常用命令", "跟 AI 说话的例子", "输入框按键", "图标", "jk undo", "JK_API_KEY"):
        assert word in out


def test_unwritable_home_friendly_error(tmp_path, monkeypatch, capsys):
    home = tmp_path / "ro"
    home.mkdir()
    home.chmod(0o500)
    monkeypatch.setenv("JK_HOME", str(home))
    try:
        assert cli.main([]) == 1
    finally:
        home.chmod(0o700)
    msg = capsys.readouterr().err
    assert "读写文件失败" in msg and "Traceback" not in msg


# ---------- 周期 ----------

def test_context_includes_recur_next():
    from jk.model import RECUR

    bs = [Notebook("周期", [Item(6, "跑步", kind=RECUR, every="weekly:1@08:00")])]
    row = json.loads(build_context(bs, [], NOW))["记事本"][0]["items"][0]
    assert row == {"id": 6, "kind": "recur", "text": "跑步", "every": "weekly:1@08:00", "next": "2026-10-19T08:00"}


def test_jk_a_adds_recur_and_jk_c_refuses(env, monkeypatch, capsys):
    use_fake(monkeypatch, {"reply": "好", "ops": [{"op": "add", "kind": "recur", "text": "跑步", "every": "weekly:1@08:00"}]})
    assert cli.main(["a", "每周一早上八点跑步"]) == 0
    out = capsys.readouterr().out
    assert "＋ 新增 1. 跑步" in out and "每周一 08:00" in out
    assert "- ↻ 跑步" in (env / "notebooks" / "周期.md").read_text()
    assert cli.main(["c", "1"]) == 1
    assert "周期条目" in capsys.readouterr().err
