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
│ MSG*.db, MicroMsg.db, PublicMsg.db, FTSContact.db       │
└──────────────────────────────────────────────────────────┘
```

## 2. CLI 设计

统一入口是 `wechat-db-export`，下挂三个子命令：

- `conversations`：导出 `MSG*.db` 中的会话消息
- `official-articles`：优先导出 `MicroMsg.db` 中的当前公众号订阅流，必要时回退到 `PublicMsg.db`
- `official-articles-timeline`：解析 `BizProfileV2.RespData`，导出单个公众号最近多篇文章的时间线

两个子命令共用日期解析与错误处理逻辑。

## 3. 核心模块

### 3.1 `datasource.py`

- `MessageDataSource`：发现 `MSG*.db`，支持列出会话和并行读取消息
- `PublicArticleDataSource`：优先读取 `MicroMsg.db / BizSessionNewFeeds`，并通过 `BizProfileV2` 补充账号信息；若当前订阅流不可用，再回退到 `PublicMsg.db / PublicNameToID`
- `iter_article_timeline(...)`：直接解析 `BizProfileV2.RespData`，导出文章级别时间线

### 3.2 `parser.py`

- `parse_bytes_extra()`：解析 BytesExtra protobuf
- `decode_message_content()`：统一的消息内容解码入口
- type 49 消息走 LZ4 解压 + appmsg XML 抽取，提取 `title`、`url`、`description`
- `parse_proto_message()`：通用 protobuf 读取器，用于无 schema blob
- `parse_biz_profile_resp_data()`：从 `RespData` 中抽取文章标题、链接、时间和封面图 URL

### 3.3 `exporter.py`

- `export_conversations()`：导出会话 CSV
- `export_public_articles()`：导出公众号文章 CSV
- `export_public_article_timeline()`：导出公众号文章时间线，支持 CSV/Markdown

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

## 5. 当前公众号存储模型

### 5.1 最新订阅流：MicroMsg

- `BizSessionNewFeeds` 提供每个公众号最近一条更新
- `BizProfileV2` 提供账号 ID、订阅状态和 `RespData` blob
- 当前实现把 `BizSessionNewFeeds.Title` 视为公众号名称，把 `Desc` 视为最新文章标题，把 `UpdateTime` 视为时间戳
- `official-articles` 对 `RespData` 做保守处理：补充账号 ID，并尽量提取一个 `mp.weixin` 链接
- `official-articles-timeline` 则直接从 `RespData` 中解析最近多篇文章

### 5.2 历史 fallback：PublicMsg

- `PublicMsg` 和 `PublicNameToID` 继续保留，用于旧时间段历史卡片导出
- 这条旧链路仍然可以提供更完整的 `title / url / summary`

## 6. 可扩展方向

1. 把 `RespData` 的更多字段纳入输出，例如更完整的摘要或多图信息
2. 扩展更多公众号 subtype 或 feed 变体
3. 增加 JSON / Parquet 等导出格式
