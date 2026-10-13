# agent-log

## 状态
STATE: jk-v0.4.0 | L2-F | 周期类型 + 格式 v2 | confirm=已问 | gates=pytest 149 passed + 真实 AI 6 场景实测 | last_errpath=—
- 待办：用真实 DeepSeek Key 跑一轮 `jk a` 实测并据此调提示词。

## 决策（2026-10-13，用户确认）
- 命令名 jk = Journal Keeper（tb 被 taskbook 占用）；不导入 taskbook 数据。
- AI：DeepSeek OpenAI 兼容接口，默认 deepseek-flash（deepseek-chat 已于 2026-07 下线）；配置明文 ~/.jk/.env。
- 存储：~/.jk，Markdown，AI 自动分本；直接改 + jk undo；对不上号反问给选项。
- 功能：截止/逾期、优先级、进行中、次日归档、时间线（回顾+前瞻）；快捷命令只留 jk c / jk undo。
- 提交不加 AI 署名（Nexus 规范 commit-message-convention 禁止）。

## 教训
- 2026-10-13 18:15 冒烟测试 `jk p` 读到剪贴板里的 API Key 并发给了 DeepSeek（只读本机未落盘）。根因：发送前无密钥检查、测试直接用真实剪贴板。已加 looks_secret 拦截；以后冒烟测试用临时 JK_HOME 和假剪贴板。

## 决策（2026-10-13 周期类型，用户确认）
- 周期不打卡、不统计；规则支持每天/工作日/每周几/每月几号；单独「周期」分组置顶（存 notebooks/周期.md）。
- 因旧版会丢 every=，数据格式升 v2（v1→v2 自动备份+重写文件头）。
