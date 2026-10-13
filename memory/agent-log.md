# agent-log

## 状态
STATE: jk-v0.1.0 | L2-F | 首版完成 | confirm=已问 | gates=pytest 53 passed | last_errpath=—
- 待办：用真实 DeepSeek Key 跑一轮 `jk a` 实测并据此调提示词。

## 决策（2026-10-13，用户确认）
- 命令名 jk = Journal Keeper（tb 被 taskbook 占用）；不导入 taskbook 数据。
- AI：DeepSeek OpenAI 兼容接口，默认 deepseek-flash（deepseek-chat 已于 2026-07 下线）；配置明文 ~/.jk/.env。
- 存储：~/.jk，Markdown，AI 自动分本；直接改 + jk undo；对不上号反问给选项。
- 功能：截止/逾期、优先级、进行中、次日归档、时间线（回顾+前瞻）；快捷命令只留 jk c / jk undo。
- 提交不加 AI 署名（Nexus 规范 commit-message-convention 禁止）。

## 教训
（暂无）
