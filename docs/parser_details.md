# 微信解密数据库解析详解

本文将完整说明 `wechat_db_parser` 项目的设计理念、关键数据表结构、消息解析流程以及扩展方向，目标是让任何工程师或 AI 助手仅凭本文即可重建当前工具并继续拓展功能。

## 1. 目录结构与输入假设

解密后的微信数据通常位于某个工作目录下，本文以 `<DATA_DIR>` 表示：

```
<DATA_DIR>/
├─ FTSContact.db        # 联系人/群成员 FTS 数据库
├─ MSG0.db ... MSGN.db  # 主消息库（Windows v3 格式）
├─ Multi/
│   ├─ MSG0.db ...
│   └─ MediaMSG*.db
└─ ...                  # 其他辅助数据库
```

工具默认会在 `<DATA_DIR>` 以及 `<DATA_DIR>/Msg` 目录中搜索 `MSG*.db`，因此可传入根解密目录或直接传入 `Msg/` 子目录。`FTSContact.db` 负责提供联系人备注、群昵称等显示信息；缺失时会回退到原始 `wxid`。

## 2. 核心模块概览

```
wechat_db_parser/
├─ datasource.py     # 读取 MSG*.db、枚举会话、迭代消息
├─ contacts.py       # 解析 FTSContact.db，提取联系人/群昵称
├─ parser.py         # BytesExtra/LZ4 解析、消息对象构建
├─ model.py          # 数据模型（消息、联系人显示名等）
├─ exporter.py       # 汇总、写出 CSV，支持并行与昵称反解
└─ cli.py            # 命令行入口
```

### 2.1 数据模型（`model.py`）

- `Message`: 统一后的消息结构，包含时间、发言者、内容、原始文本、附加元数据等。
- `ContactDisplay`: 联系人显示元数据，支持 remark/alias/nickname 优先级。
- `GroupMemberDisplay`: 群聊内成员的群昵称、别名。

### 2.2 消息解析（`parser.py`）

1. `parse_bytes_extra`：手写 protobuf 解析器，用于解码 `BytesExtra` 字段（type=1 为真实发送者，type=3/4 为媒体路径）。
2. `_decode_content`：当消息类型为 49 时使用 `lz4.block.decompress` 解压，解析 XML 并提取标题/摘要/链接。
3. `build_message`：将一条数据库记录转换为 `Message` 对象，补齐语音/图片/视频路径信息。
4. `annotate_messages`：结合联系人/群成员信息，为 `talker` 和 `sender` 填充可读的显示名。

### 2.3 数据源访问（`datasource.py`）

- `MessageDataSource`：
  - `_discover_message_dbs`：在 `<DATA_DIR>` 和 `<DATA_DIR>/Msg`、以及各自的 `Multi/` 目录中搜索 `MSG*.db`。
  - `list_talkers`：遍历所有消息库，从 `Name2ID`/`Name2ID_v1` 表中收集会话标识（群聊 ID 或微信号）。
  - `iter_messages`：针对某个 `talker` 按时间范围、上限条数读取消息，跨多个数据库聚合后排序。

### 2.4 联系人与群昵称（`contacts.py`）

- `load_contact_book`：读取 `FTSContact15_content`、`FTSContact15_MetaData` 与 `NameToId` 的组合，将 remark/alias/nickname 三者保存到 `ContactDisplay`。
- `load_group_directory`：读取 `FTSChatroom15_content` 与 `FTSChatroom15_MetaData`，得到群内成员在群里的显示名。

### 2.5 导出与 CLI（`exporter.py`、`cli.py`）

- `export_conversations`：
  - 支持并行（`ThreadPoolExecutor`）。
  - `--talkers` 参数既可写微信 ID，也可写备注/昵称，内部通过 `ContactDisplay` 反解成真实 ID。
  - 自动创建输出目录，文件命名为 `群名(微信ID)__哈希.csv`，避免重名。
  - CSV 字段：`timestamp`, `talker_display`, `talker_id`, `sender_display`, `sender_id`, `message_type`, `message_subtype`, `content`, `raw_content`, `extras(JSON)`。
- CLI (`cli.py`) 提供参数解析、时间格式兼容、错误提示。

## 3. 关键数据表说明

### 3.1 MSG*.db（Windows v3）

- `MSG` 表：每条消息记录。重要字段：
  - `StrTalker`: 会话 ID（微信号或 `@chatroom`）。
  - `IsSender`: 是否自己发送。
  - `Type`, `SubType`: 消息类型（文本=1，图片=3，语音=34，文件/链接=49 等）。
  - `StrContent`: 文本内容或 XML。
  - `CompressContent`: LZ4 压缩的 XML。
  - `BytesExtra`: protobuf，包含真实发送者（群聊）、媒体路径等。
- `Name2ID` / `Name2ID_v1`：列出当前数据库涉及的 talker。

### 3.2 FTSContact.db

- `FTSContact15_content` & `FTSContact15_MetaData` & `NameToId`: 组合用于取得联系人/群聊的 `alias`、`nickname`、`remark`。
- `FTSChatroom15_content` & `FTSChatroom15_MetaData`: 解析群成员的群昵称、群备注。

> 注意：FTS 数据库使用微信自定义 tokenizer，无法直接用 FTS 查询，但 `_content`、`_MetaData` 表是普通表，可以直接读取。

## 4. 运行流程

1. **初始化数据源**：`MessageDataSource` 构造时搜集所有 `MSG*.db` 路径。
2. **加载联系人/群昵称**：`load_contact_book` 与 `load_group_directory`。
3. **解析 `--talkers` 参数**：如果用户输入的是备注或昵称，通过联系人映射找到真实 `wxid`。
4. **遍历会话**：
   - 从所有消息库中取出指定 talker 的记录（满足时间/数量条件）。
   - 调用 `build_message` 转换结构。
   - 使用 `annotate_messages` 补齐显示名。
5. **写出 CSV**：按 talker 写入单独的文件，附带 `extras` JSON 字段。
6. **并行/进度条**：若安装 `tqdm`，会显示导出进度；`ThreadPoolExecutor` 可提升多会话导出速度。

## 5. 可扩展方向

1. **支持 v4 数据库**：`message_*.db`、`contact.db` 结构不同，需要新增 datasource 实现并根据版本切换。
2. **媒体导出**：解析 `HardLinkImage.db`、`HardLinkVideo.db`、`MediaMSG*.db`，将图片/视频复制到输出目录。
3. **索引缓存**：为大型数据库构建 FTS 或倒排索引，提供按关键词检索功能。
4. **增量更新**：比较数据库 fingerprint，仅导出新增消息。
5. **HTTP/GUI 封装**：在 CLI 基础上提供简易 Web 服务或图形界面。
6. **多格式导出**：未来可新增 JSON/Parquet/SQLite 等格式，或直接生成统计报表。

## 6. 重建步骤速览

1. 安装依赖：`pip install lz4 protobuf tqdm`。
2. 创建与本文一致的目录结构，将源码放入 `wechat_db_parser/src/wechat_db_parser/`。
3. 设置 `PYTHONPATH=wechat_db_parser/src`，使用 `python -m wechat_db_parser.cli` 执行。
4. 传入解密目录与输出目录，使用 `--limit` 做小规模测试。

示例：

```bash
source venv/bin/activate
PYTHONPATH=wechat_db_parser/src python -m wechat_db_parser.cli \
  --data-dir Msg \
  --output out \
  --talkers 原ZWO天文摄影③群（元老群） \
  --limit 10
```

## 7. 注意事项

- 大规模导出时建议关闭 `--limit`，并适当调整 `--workers`。
- 若联系人数据库缺失，输出中的 `talker_display` / `sender_display` 会退化为 `wxid`。
- 某些稀有消息类型（如合并转发、笔记）仍以原始 XML 形式存储于 `raw_content`。
- `extras` 中的路径为相对路径，需结合原始微信数据目录定位真实文件。

---

通过上述说明，读者可完整理解 `wechat_db_parser` 的解析逻辑，并在此基础上实现新的功能或迁移到其他语言/平台。
