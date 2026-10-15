import pytest

from jk.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "jk")


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """测试默认关掉每日自动同步，避免终端里的真实账号让测试去连学校平台。"""
    monkeypatch.setenv("JK_UCLOUD_AUTO", "0")
