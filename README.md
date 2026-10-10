# 微信聊天数据库解析工具

本仓库假设你已经**在别处**完成了微信数据库的解密工作——网上有不少教程和第三方工具，例如 `pywxdump` 等，你可以自行决定是否采用。我们不负责解密环节，只关注在一个理想的前提下：你已经拿到了可读取的微信 Windows 版 3.9 系列（非 4.0）聊天数据库，并希望把会话导出为易于分析的格式。

## 环境准备

- 初次使用时执行 `uv venv .venv && source .venv/bin/activate` 创建并激活虚拟环境
- 激活环境后安装依赖：`uv pip install -e '.[dev]'`

## CLI 概览

项目提供一个统一入口 `wechat-db-export`，通过 subcommand 区分不同导出模式。

### 1. 会话全量导出

```bash
wechat-db-export \
  conversations \
  --data-dir /path/to/Msg \
  --output /path/to/output_dir \
  --talkers friend_wechat_id another_friend \
  --start 2025-01-01 \
  --end 2025-02-01
```

### 2. 公众号文章导出

`official-articles` 会优先从 `MicroMsg.db` 的 `BizSessionNewFeeds` 导出当前订阅流中的最新公众号更新；如果当前环境里只有旧数据，它会回退到 `PublicMsg.db` 的历史文章卡片。输出字段保持统一：`timestamp`、`account_name`、`account_id`、`title`、`url`、`summary`。

```bash
wechat-db-export \
  official-articles \
  --data-dir /path/to/Msg \
  --output /path/to/official_articles.csv \
  --accounts 科技早餐 量子位 \
  --start 2025-01-01 \
  --end 2025-02-01
```

### 3. 公众号文章时间线导出

`official-articles-timeline` 直接解析 `BizProfileV2.RespData`，按文章级别导出最近多篇内容，适合做时间线回看或 Markdown 归档。

```bash
wechat-db-export \
  official-articles-timeline \
  --data-dir /path/to/Msg \
  --output /path/to/official_articles_timeline.md \
  --accounts GeekPark \
  --limit 3 \
  --format markdown
```

如果希望从源代码目录直接调用模块，也可以使用：

```bash
PYTHONPATH=src python -m wechat_db_parser.cli --help
```

### conversations 参数说明

- `--data-dir`：指向解密后 MSG 数据目录（例如 Windows 客户端导出的 `Msg/`）。
- `--output`：CSV 导出目录，不存在时会自动创建。
- `--talkers`：可选，限定导出的联系人或群（支持微信号、备注、昵称）。
- `--start` / `--end`：可选，限制导出时间范围，接受 `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM[:SS]` 格式。
- `--limit`：可选，限制每个会话的消息数量，便于调试。
- `--workers`：可选，设置并行 worker 数，默认 1。

### official-articles 参数说明

- `--data-dir`：指向解密后的微信数据目录，支持传根目录或 `Msg/`。当前实现会优先查 `MicroMsg.db`，必要时回退到 `PublicMsg.db`。
- `--output`：导出 CSV 的文件路径。
- `--accounts`：可选，限定导出的公众号，支持账号 ID、名称或 `名称(账号ID)`。
- `--start` / `--end`：可选，限制文章时间范围，接受 `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM[:SS]` 格式。
- `--limit`：可选，限制导出的文章条数，便于调试。

### official-articles-timeline 参数说明

- `--data-dir`：指向解密后的微信数据目录，当前要求存在 `MicroMsg.db / BizProfileV2`。
- `--output`：导出文件路径，可以是 CSV 或 Markdown。
- `--accounts`：可选，限定导出的公众号，支持账号 ID、名称或 `名称(账号ID)`。
- `--start` / `--end`：可选，限制文章时间范围。
- `--limit`：可选，限制导出的文章条数，便于调试。
- `--format`：`csv` 或 `markdown`。

命令执行成功后，`conversations` 会打印每个会话对应的 CSV 文件，`official-articles` 和 `official-articles-timeline` 会打印最终文件路径与文章数量。

## 群沉默成员扫描（独立脚本）

`scripts/performance_improvement_plan.py` 是一个独立脚本（不在 `wechat-db-export` 子命令里），用来找出「过去 N 天从未发言」的群成员，并给出每人已沉默多久。

```bash
python scripts/performance_improvement_plan.py \
  --data-dir Msg \
  --talker 12345678901@chatroom \
  --past-days 365 \
  --output /path/to/silent_members.csv
```

- `--talker`：群名/备注或 `xxx@chatroom` ID。
- `--past-days`：统计窗口，默认 365。
- `--limit`：终端预览条数，默认 20（CSV 不受影响）。
- `--output`：可选，导出完整名单；建议写到仓库外或已忽略的 `output/` 目录。

输出两列（沉默时长、显示名）加判定依据，CSV 列为 `silence_duration,display_name,member_id,basis`。判定依据分三种：`最后发言`（窗口外发过言，距今按最后一次发言算）、`入群时间(推断)`（从未发言，按入群系统消息推断）、`无入群记录(下界)`（从未发言且无可归因入群记录，只给下界）。「发言」排除 type=10000 系统消息（入群/撤回/拍一拍）。脚本只打印显示名与时长，不打印消息正文。

## 给 AI 助手的 repo-local skill

仓库内提供了 repo-local skill：`skills/wechat_db_parser.md`。

如果 AI 助手直接在本仓库里工作，让它先读取这个文件，再做导出、排查或扩展。

如果你希望把这个 skill 安装到自己的本地 skill 目录，可以直接复制。下面只是一个占位示例，按你自己的 agent 约定替换即可：

```bash
mkdir -p <local-skill-dir>
cp skills/wechat_db_parser.md <local-skill-dir>/
```

## 注意事项

- 我们只针对微信 Windows PC 版 3.9 系列数据库进行测试，其他格式（含 v4、移动端等）尚未验证。
- 数据库结构和加密方式随微信版本变动较大，请确保你拥有合法访问和处理这些数据的权利。
- 当前公众号最新订阅流主要来自 `MicroMsg.db / BizSessionNewFeeds`，并通过 `BizProfileV2` 补充账号 ID 与 blob 信息。
- `PublicMsg.db / PublicNameToID` 仍然保留为历史 fallback，用于旧时间段或没有新订阅流数据的场景。
- `official-articles-timeline` 已经能从 `BizProfileV2.RespData` 中抽出最近多篇文章的标题、链接、时间和封面图 URL，并支持 Markdown 输出。
