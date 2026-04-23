# RFC：WeChat 数据库解析技术设计

## 1. 架构概览

```
┌──────────────────────────────────────────────────────────┐
│ CLI                                                     │
│ wechat_db_parser.cli                                    │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│ wechat_db_parser                                         │
│ exporter, datasource, parser, contacts, model           │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│ SQLite                                                   │
│ MSG*.db, PublicMsg.db, FTSContact.db                    │
└──────────────────────────────────────────────────────────┘
```

## 2. CLI 设计

统一入口是 `wechat-db-export`，下挂两个子命令：

- `conversations`：导出 `MSG*.db` 中的会话消息
- `official-articles`：导出 `PublicMsg.db` 中的公众号文章卡片

两个子命令共用日期解析与错误处理逻辑。

## 3. 核心模块

### 3.1 `datasource.py`

- `MessageDataSource`：发现 `MSG*.db`，支持列出会话和并行读取消息
- `PublicArticleDataSource`：定位 `PublicMsg.db`，读取 `PublicMsg` 中的 type 49 / subtype `{0, 5}` 文章卡片，并结合 `PublicNameToID` 解析公众号信息

### 3.2 `parser.py`

- `parse_bytes_extra()`：解析 BytesExtra protobuf
- `decode_message_content()`：统一的消息内容解码入口
- type 49 消息走 LZ4 解压 + appmsg XML 抽取，提取 `title`、`url`、`description`

### 3.3 `exporter.py`

- `export_conversations()`：导出会话 CSV
- `export_public_articles()`：导出公众号文章 CSV

## 4. 数据模型

### 4.1 `Message`

用于会话导出，包含时间、会话、发送者、类型、内容和 extras。

### 4.2 `OfficialAccountArticle`

用于公众号文章导出，包含：

- `timestamp`
- `account_id`
- `account_name`
- `title`
- `url`
- `summary`
- `msg_type`
- `sub_type`

## 5. PublicMsg 处理范围

- 当前实现只依赖已验证的两张表：`PublicMsg`、`PublicNameToID`
- 当前只导出已观察到的文章 subtype：`0` 和 `5`
- 解析逻辑复用现有 type-49 appmsg 解码能力，不引入第二套解析器

## 6. 可扩展方向

1. 支持更多 `PublicMsg` schema 变体
2. 扩展更多公众号 subtype 的分类规则
3. 增加 JSON / Parquet 等导出格式
