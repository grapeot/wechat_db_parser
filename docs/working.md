# Working DM

## Changelog

### 2026-10-10

#### scripts/performance_improvement_plan.py

- 沉默成员扫描在原有「过去 N 天未发言名单」基础上，新增每人「已沉默多久」输出（终端两列 + CSV）
- 沉默时长口径分三种判定依据：
  - `最后发言`：窗口外发过言 → 距今 = 现在 − 最后一次发言时间
  - `入群时间(推断)`：保留历史里从未发言 → 距今 = 现在 − 入群时间（从 type=10000 入群系统消息按昵称推断）
  - `无入群记录(下界)`：从未发言且无可归因入群记录 → 只给下界（≥ 保留历史最早消息距今），不臆测确切时长
- 「发言」定义收紧：排除 type=10000 系统消息（入群/撤回/拍一拍），避免把「拍了拍」误算成发言
- 入群昵称匹配加歧义保护：一个昵称对应多个成员时不归因入群时间；支持「A邀请B」「A、B加入」「A通过扫描…加入群聊」等形式
- 查询按 `end` 上界过滤，保证「截至 end」判定正确；`--past-days`/`--limit` 加参数校验
- CSV schema 由 `member_id,display_name` 改为 `silence_duration,display_name,member_id,basis`（本工具无仓库内调用方，属有意变更）
- 隐私：脚本只打印显示名/时长/判定依据，不打印消息正文；`--output` 仍为可选，建议写到仓库外或已忽略的 `output/`

#### tests/test_performance_improvement_plan.py（新增）

- 合成数据测试（不含真实个人信息）：type=10000 不算发言、三种判定依据、昵称歧义不归因、`end` 上界排除未来消息

#### README.md

- README 新增「群沉默成员扫描」独立脚本用法

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
