# PRD：WeChat 数据库解析与导出工具

## 1. 项目目标

从微信解密后的消息数据库中解析并导出聊天记录，支持会话全量导出与公众号文章导出，便于后续分析、归档或外部检索。

**约束**：纯 Python 实现，直接消费解密目录（`Msg/*.db`、`MSG*.db` 等），不依赖 Go 或其他运行时。

## 2. 核心功能

### 2.1 会话全量导出（`wechat-db-export conversations`）

- **能力**：按群聊或联系人分卷导出会话消息到 CSV
- **参数**：`--data-dir`、`--output`、`--talkers`、`--start`、`--end`、`--limit`、`--workers`
- **输出**：每个会话一个 CSV，包含 timestamp、talker、sender、message_type、content、raw_content、extras 等字段

### 2.2 公众号文章导出（`wechat-db-export official-articles`）

- **能力**：优先从 `MicroMsg.db` 的当前订阅流提取公众号更新，必要时回退到 `PublicMsg.db` 的历史文章卡片，导出为统一 CSV
- **参数**：`--data-dir`、`--output`、`--accounts`、`--start`、`--end`、`--limit`
- **数据源**：当前主源是 `MicroMsg.db / BizSessionNewFeeds`，并用 `BizProfileV2` 补充账号信息；旧数据回退到 `PublicMsg` + `PublicNameToID`
- **输出字段**：`timestamp`、`account_name`、`account_id`、`title`、`url`、`summary`
- **过滤能力**：支持按公众号名称或账号 ID 筛选

## 3. 输出格式

### 3.1 会话 CSV

| 字段 | 说明 |
|------|------|
| timestamp | ISO8601 时间 |
| talker_display / talker_id | 会话显示名 / ID |
| sender_display / sender_id | 发送者显示名 / ID |
| message_type / message_subtype | 消息类型 |
| content | 解析后的文本 |
| raw_content | 原始 XML/JSON |
| extras | JSON，含 url、title、媒体路径等 |

### 3.2 公众号文章 CSV

| 字段 | 说明 |
|------|------|
| timestamp | 文章卡片消息时间 |
| account_name / account_id | 公众号名称 / 账号 ID |
| title | 文章标题 |
| url | 文章链接。当前订阅流模式下为 best-effort 提取 |
| summary | 摘要或 description。当前订阅流模式下可能为空 |

## 4. 使用场景

1. 历史会话归档
2. 按会话导出供后续分析
3. 公众号当前更新监控与历史文章卡片收集
4. 面向 AI 或搜索系统的结构化预处理

## 5. 非目标

- 媒体文件导出
- 朋友圈导出
- GUI 或 Web 界面
- 未验证的数据库版本支持
