# 微信聊天记录与公众号文章技能

这个 skill 面向任务执行，而不是仓库开发说明。

它覆盖两类常见任务：

1. 导出聊天会话
2. 导出公众号文章卡片

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

- 当前公众号文章导出只依赖已验证的 `PublicMsg` 和 `PublicNameToID`
- 当前文章 subtype 只覆盖已观察到的 `0` 和 `5`
- 不修改 raw DB，不写回 `Msg/`

## 遇到问题时先看哪里

- CLI 用法：`README.md`
- 产品边界：`docs/prd.md`
- 技术设计：`docs/rfc.md`
- 最近改动：`docs/working.md`
