# Working DM

## Changelog

### 2026-04-22

#### unified CLI

- 将原来的 flat CLI 改为统一入口 + subcommand 结构
- `conversations` 保留原有会话导出能力
- `official-articles` 新增公众号文章导出入口

#### official articles export

- 新增 `PublicArticleDataSource`
- 从 `PublicMsg.db` 中读取 `type 49 / subtype {0, 5}` 的文章卡片
- 结合 `PublicNameToID` 输出 `account_name` 与 `account_id`
- 复用现有 type-49 appmsg 解码逻辑抽取 `title`、`url`、`summary`

#### docs and skill

- 更新 README 为统一 CLI 说明
- 新增 `docs/prd.md`、`docs/rfc.md`
- 新增 repo-local skill：`skills/wechat_db_parser.md`

#### tests

- 新增 CLI subcommand 解析与 dispatch 测试
- 新增基于临时 SQLite fixture 的公众号文章导出测试
