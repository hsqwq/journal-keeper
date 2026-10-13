import stat

import pytest

from jk.config import ensure_env_file, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for key in ("JK_API_KEY", "DEEPSEEK_API_KEY", "JK_MODEL", "JK_BASE_URL", "DEEPSEEK_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JK_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_template_created_private(clean_env):
    assert ensure_env_file(clean_env)
    assert not ensure_env_file(clean_env)
    assert stat.S_IMODE((clean_env / ".env").stat().st_mode) == 0o600
    cfg = load_config()
    assert cfg.api_key == "" and cfg.model == "deepseek-flash"


def test_env_file_and_override(clean_env, monkeypatch):
    ensure_env_file(clean_env)
    (clean_env / ".env").write_text("JK_API_KEY=file-key\nJK_MODEL=deepseek-v4-pro\n")
    assert load_config().api_key == "file-key"
    monkeypatch.setenv("JK_MODEL", "x")
    assert load_config().model == "x"


def test_old_key_names_still_work(clean_env):
    clean_env.mkdir(parents=True)
    (clean_env / ".env").write_text("DEEPSEEK_API_KEY=old\n")
    assert load_config().api_key == "old"
    (clean_env / ".env").write_text("DEEPSEEK_API_KEY=old\nJK_API_KEY=new\n")
    assert load_config().api_key == "new"


def test_bad_number_falls_back(clean_env):
    clean_env.mkdir(parents=True)
    (clean_env / ".env").write_text("JK_ARCHIVE_AFTER_DAYS=abc\n")
    assert load_config().archive_after_days == 1
