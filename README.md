# 微信聊天数据库解析工具

本仓库假设你已经**在别处**完成了微信数据库的解密工作——网上有不少教程和第三方工具，例如 `pywxdump` 等，你可以自行决定是否采用。我们不负责解密环节，只关注在一个理想的前提下：你已经拿到了可读取的微信 Windows 版 3.9 系列（非 4.0）聊天数据库，并希望把会话导出为易于分析的格式。

## 环境准备

- 初次使用时执行 `uv venv venv && source venv/bin/activate` 创建并激活虚拟环境
- 激活环境后安装依赖：`uv pip install -e .`

## 基本用法

项目提供了命令行工具 `wechat-db-export`，用于将解密后的数据库导出为 CSV。

```bash
wechat-db-export \
  --data-dir /path/to/Msg \
  --output /path/to/output \
  --talkers friend_wechat_id another_friend \
  --start 2025-01-01 \
  --end 2025-02-01
```

如果希望从源代码目录直接调用模块，也可以使用：

```bash
PYTHONPATH=src python -m wechat_db_parser.cli --help
```

参数说明：

- `--data-dir`：指向解密后 MSG 数据目录（例如 Windows 客户端导出的 `Msg/`）。
- `--output`：CSV 导出目录，不存在时会自动创建。
- `--talkers`：可选，限定导出的联系人或群（支持微信号、备注、昵称）。
- `--start` / `--end`：可选，限制导出时间范围，接受 `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM[:SS]` 格式。
- `--limit`：可选，限制每个会话的消息数量，便于调试。
- `--workers`：可选，设置并行 worker 数，默认 1。

命令执行成功后，会在终端显示各会话与导出文件的对应关系，输出 CSV 位于 `--output` 指定目录。

## 注意事项

- 我们只针对微信 Windows PC 版 3.9 系列数据库进行测试，其他格式（含 v4、移动端等）尚未验证。
- 数据库结构和加密方式随微信版本变动较大，请确保你拥有合法访问和处理这些数据的权利。
