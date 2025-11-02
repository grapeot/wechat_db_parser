# 设计草稿：WeChat 日志解析通用库与 CLI

## 总体目标

构建一个可复用的 Python 库，用于解析微信解密后的消息数据库；同时提供一个命令行工具，批量导出聊天记录（按群/联系人分卷写入 CSV），并具备一定的并行与进度反馈能力。

> 约束：不依赖 Go 代码；直接消费解密目录（`Msg/*.db`、`MSG*.db` 等）。

## 功能分层设计

1. **数据访问层 (`wechat_msg_parser.datasource`)**
   - 负责定位并读取各类 SQLite 数据库：
     - 消息库：`MSG*.db` / `Multi/MSG*.db`（Windows v3）或 `message_*.db`（v4）。
     - 联系人库：`FTSContact.db`。
     - 群成员信息：`FTSChatroom*.db`。
   - 抽象出统一的迭代接口（按 talker/timestamp 过滤）。
   - 支持资源管理（连接池或懒加载）。

2. **模型与解析层 (`wechat_msg_parser.model`)**
   - 消息对象：包含时间、talker、sender、内容、多媒体元数据等。
   - 联系人/群成员对象：封装显示名、别名、备注。
   - Proto/LZ4/Zstd 解析工具：复用现有 `BytesExtra`、`PackedInfo` 解析器，封装成纯 Python 函数。

3. **业务逻辑层 (`wechat_msg_parser.service`)**
   - 组合数据访问与模型，完成消息补充（显示名、媒体路径）。
   - 提供批量导出方法：按 talker 聚合，返回统一的数据结构。
   - 并行能力：基于 `concurrent.futures` 或 `multiprocessing`，支持多 talker 并行导出。

4. **CLI 层 (`wechat_msg_parser.__main__` 或 `wechat_msg_parser.cli`)**
   - 参数：
     - `--data-dir`：解密目录根路径。
     - `--output`：导出目录。
     - `--workers`：并行 worker 数。
     - `--talkers`：可选，指定导出对象（默认全量）。
     - `--start` / `--end`：时间范围过滤。
   - 进度条：使用 `tqdm` 显示导出进度。
   - 异常处理：容忍个别文件失败，最终输出总结。

## 目录结构草案

```
wechat_msg_parser/
  docs/
    design.md
  src/
    wechat_msg_parser/
      __init__.py
      datasource.py
      model.py
      parser.py
      exporter.py
      cli.py
  pyproject.toml (或 setup.cfg)
  README.md
  tests/
    ...
```

## 导出格式建议

- CSV 字段（唯一支持的导出格式）：
  - `timestamp`（ISO8601 或 epoch 秒）
  - `talker_display` / `talker_id`
  - `sender_display` / `sender_id`
  - `message_type` / `message_subtype`
  - `content`（纯文本）
  - `raw_content`（原始 XML/JSON 文本）
  - `media_path`（可选）

文件命名：`{talker_display or talker_id}.csv`，必要时清理无效字符。

## 并行策略

- 按 talker 粗粒度分片，`ThreadPoolExecutor`/`ProcessPoolExecutor` 均可。
- 每个 worker 打开自己的 SQLite 连接，避免跨线程共享。
- `tqdm` 结合 `as_completed` 显示整体进度。

## 下一步

1. 定义 `pyproject.toml`，建立基础包结构。
2. 将现有脚本逻辑拆分成 `model` + `parser` + `exporter`。
3. 补充最小单元测试（可使用截取的样例 DB）。
4. 实现 CLI，完成端到端 CSV 导出。
