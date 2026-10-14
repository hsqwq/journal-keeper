# 开发

## 环境

```sh
cd ~/Projects/jk
uv sync              # 装依赖
uv run pytest -q     # 跑测试
uv run jk            # 不安装直接运行
JK_HOME=/tmp/jk-test uv run jk   # 用临时数据目录试，不碰真实数据
```

`uv tool install -e .` 是可编辑安装：改代码立刻生效。

## 模块

| 文件 | 职责 |
| --- | --- |
| `cli.py` | 命令分发与交互 |
| `config.py` | 读 `.env`、旧键名兼容 |
| `model.py` | 条目 / 记事本与 Markdown 互转 |
| `store.py` | 读写数据目录、补编号 |
| `history.py` | 快照与撤销 |
| `archive.py` | 自动归档 |
| `ops.py` | AI 改动清单的校验与执行 |
| `ai.py` | 提示词、调用 DeepSeek、反问与纠错循环、多模态消息 |
| `attach.py` | 读剪贴板、图片识别、疑似密钥检测 |
| `compose.py` | `jk a` 输入框（prompt_toolkit），粘贴占位符 |
| `complete.py` | zsh Tab 补全：`jk __complete` 输出候选项，`jk completion zsh` 输出补全脚本 |
| `theme.py` | 配色（固定十六进制颜色，禁止用 magenta/cyan/dim 等调色板名，测试会检查） |
| `render.py` | 列表视图 |
| `timeline.py` | 时间线视图 |
| `migrate.py` | 数据格式版本与迁移（`MIGRATIONS` 里登记每一级升级） |
| `recur.py` | 周期规则解析、下次时间、给人看的描述 |

## 更新 README 截图

改了界面后运行 `uv run python tools/gen-demo.py`，会重新生成 `docs/images/*.png`。
数据是脚本里写死的虚构示例，时间固定为 2026-10-14 09:30，所以结果可重复。
需要 firefox、ImageMagick，以及字体 Noto Sans Mono CJK SC、Adwaita Mono。

## 改数据格式的步骤

1. `model.FORMAT_VERSION` +1。
2. 在 `migrate.MIGRATIONS` 加 `{旧版本: 升级函数}`，函数直接改 `$JK_HOME` 下的文件。
3. 加测试：旧数据能升级、升级后能正常读写。
4. 更新 `docs/data-format.md` 和 `CHANGELOG.md`。

## 改配置键名

在 `config.ALIASES` 加 `旧键: 新键`，并更新 `ENV_TEMPLATE` 与 README。不要删旧键。

## 提交

每个小功能一个提交，格式 `<type>(<scope>): <中文说明>`，scope 用模块名。
