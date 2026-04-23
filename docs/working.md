# Working DM

## Changelog

### 2026-04-22

#### official-articles timeline v2

- 新增 `official-articles-timeline` 子命令
- `BizProfileV2.RespData` 不再只做 best-effort URL 抽取，而是支持按文章级别解析最近多篇内容
- 当前可导出的字段包括标题、链接、摘要、文章时间、文章序号、封面图 URL
- 新增 Markdown 输出，适合单个公众号最近若干篇文章的人工阅读和 review

#### official-articles source migration

- 重新检查本地真实数据后确认：`PublicMsg.db` 文件仍会同步，但新文章卡片行在 2026-03-19 后停止增长
- 当前最新公众号更新实际出现在 `MicroMsg.db / BizSessionNewFeeds`
- `BizProfileV2` 与 `BizSessionNewFeeds` 可通过 `TalkerId` join；`RespData` 中已验证包含 `mp.weixin` 链接和文章字符串
- `PublicArticleDataSource` 现在优先读取 `BizSessionNewFeeds`，旧的 `PublicMsg` 路径保留为 fallback

#### unified CLI

- 将原来的 flat CLI 改为统一入口 + subcommand 结构
- `conversations` 保留原有会话导出能力
- `official-articles` 新增公众号文章导出入口

#### official articles export

- 新增 `PublicArticleDataSource`
- 第一版从 `PublicMsg.db` 中读取 `type 49 / subtype {0, 5}` 的文章卡片
- 现在改为优先读取 `MicroMsg.db / BizSessionNewFeeds`，并通过 `BizProfileV2` 补充 `account_id` 与 best-effort `url`
- `PublicNameToID` 路径保留为历史 fallback
- 第二版进一步解析 `BizProfileV2.RespData`，把每个公众号最近多篇文章拉成时间线

#### docs and skill

- 更新 README 为统一 CLI 说明
- 新增 `docs/prd.md`、`docs/rfc.md`
- 新增 repo-local skill：`skills/wechat_db_parser.md`

#### tests

- 新增 CLI subcommand 解析与 dispatch 测试
- 新增基于临时 SQLite fixture 的公众号文章导出测试，覆盖 MicroMsg 优先和 PublicMsg fallback 两条路径
- 新增 `RespData` synthetic fixture，验证 timeline 解析与 Markdown 导出
