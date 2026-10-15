"""配置：数据目录由环境变量 JK_HOME 决定（默认 ~/.jk），其余配置读 $JK_HOME/.env。

优先级：真实环境变量 > .env 文件 > 默认值。旧键名通过 ALIASES 继续生效（向后兼容）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULTS = {
    "JK_API_KEY": "",
    "JK_BASE_URL": "https://api.deepseek.com",
    "JK_MODEL": "deepseek-flash",
    "JK_ARCHIVE_AFTER_DAYS": "1",
    "JK_TIMEOUT": "60",
    "UCLOUD_USERNAME": "",
    "UCLOUD_PASSWORD": "",
}

# 旧键名 / 通用键名 → 当前键名。以后改名只在这里加一行，旧 .env 不用动。
ALIASES = {
    "DEEPSEEK_API_KEY": "JK_API_KEY",
    "DEEPSEEK_BASE_URL": "JK_BASE_URL",
}

ENV_TEMPLATE = """\
# jk 配置文件（明文）。改完保存即可，无需重启。
# DeepSeek API Key，在 https://platform.deepseek.com/api_keys 创建
JK_API_KEY=
# 请求地址（OpenAI 兼容接口）
JK_BASE_URL=https://api.deepseek.com
# 模型名
JK_MODEL=deepseek-flash
# 完成的任务过几天自动归档（1 = 第二天）
JK_ARCHIVE_AFTER_DAYS=1
# AI 请求超时（秒）
JK_TIMEOUT=60
# 北邮教学云平台账号（jk u 同步待办用；只发给学校统一认证，不会发给 AI）
UCLOUD_USERNAME=
UCLOUD_PASSWORD=
"""


@dataclass
class Config:
    home: Path
    api_key: str
    base_url: str
    model: str
    archive_after_days: int
    timeout: float
    ucloud_username: str = ""
    ucloud_password: str = ""

    @property
    def env_file(self) -> Path:
        return self.home / ".env"


def data_home() -> Path:
    return Path(os.environ.get("JK_HOME", "~/.jk")).expanduser()


def ensure_env_file(home: Path) -> bool:
    """首次运行生成 .env 模板（权限 600）；返回是否新建。"""
    path = home / ".env"
    if path.exists():
        return False
    home.mkdir(parents=True, exist_ok=True)
    path.write_text(ENV_TEMPLATE, encoding="utf-8")
    path.chmod(0o600)
    return True


def _int(value: str, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def load_config() -> Config:
    home = data_home()
    merged = dict(DEFAULTS)
    sources = [dotenv_values(home / ".env") if (home / ".env").exists() else {}, os.environ]
    for source in sources:
        # 同一来源里新键名优先于旧键名：先应用旧键名，再让新键名覆盖
        for old, new in ALIASES.items():
            if source.get(old):
                merged[new] = source[old]
        for key in DEFAULTS:
            if source.get(key):
                merged[key] = source[key]
    return Config(
        home=home,
        api_key=merged["JK_API_KEY"].strip(),
        base_url=merged["JK_BASE_URL"].strip(),
        model=merged["JK_MODEL"].strip(),
        archive_after_days=_int(merged["JK_ARCHIVE_AFTER_DAYS"], 1),
        timeout=float(_int(merged["JK_TIMEOUT"], 60) or 60),
        ucloud_username=merged["UCLOUD_USERNAME"].strip(),
        ucloud_password=merged["UCLOUD_PASSWORD"],  # 密码原样使用，不去空格（引号 dotenv 已处理）
    )
