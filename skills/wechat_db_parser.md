# 微信聊天记录与公众号文章技能

这个 skill 面向任务执行，而不是仓库开发说明。

它覆盖三类常见任务：

1. 导出聊天会话
2. 导出公众号文章卡片
3. 导出公众号最近多篇文章时间线

## 统一 CLI

```bash
wechat-db-export conversations --data-dir /path/to/Msg --output /tmp/wechat_export
wechat-db-export official-articles --data-dir /path/to/Msg --output /tmp/wechat_official_articles.csv
```

## 常见任务

### 导出指定会话

```bash
wechat-db-export conversations \
  --data-dir /path/to/Msg \
  --output /tmp/wechat_export \
  --talkers friend_wechat_id another_friend
```

### 导出公众号文章

```bash
wechat-db-export official-articles \
  --data-dir /path/to/Msg \
  --output /tmp/wechat_official_articles.csv
```

当前数据源有两层：

- 最新更新：`MicroMsg.db / BizSessionNewFeeds`
- 历史 fallback：`PublicMsg.db / PublicNameToID`

如果你需要单个公众号最近多篇文章，而不是只有最近一条，可以使用 `official-articles-timeline`。

### 按公众号过滤

```bash
wechat-db-export official-articles \
  --data-dir /path/to/Msg \
  --output /tmp/wechat_official_articles.csv \
  --accounts 科技早餐 量子位
```

### 搜索导出结果

```bash
grep "关键词" /tmp/wechat_official_articles.csv
```

## 任务边界

- 当前最新公众号更新主要来自 `MicroMsg.db / BizSessionNewFeeds`
- `official-articles-timeline` 会解析 `BizProfileV2.RespData`，导出最近多篇文章的标题、链接、时间和封面图 URL
- `PublicMsg` 和 `PublicNameToID` 保留为历史 fallback
- 不修改 raw DB，不写回 `Msg/`

## 遇到问题时先看哪里

- CLI 用法：`README.md`
- 产品边界：`docs/prd.md`
- 技术设计：`docs/rfc.md`
- 最近改动：`docs/working.md`
