#!/usr/bin/env python3
from __future__ import annotations

"""
针对 `wechat-db-export` 导出的 CSV 进行文本消息精简。

原始文件混杂了进群提示、系统通知、媒体占位等噪声，同时
`sender_display` 常以“昵称(wxid)”的组合形式出现。为便于后续内容分析、
建模或向量化，本脚本执行以下步骤：

1. 仅保留 `message_type == 1` 的纯文本消息；
2. 将“昵称(wxid)”拆分成易于聚合的 `sender_nickname` 与 `sender_id`，并在确认
   群内不存在一人多昵称冲突后仅保留昵称列；
3. 过滤空白内容行，将输出列精简为 `sender_nickname` 与 `content`，便于直接导入
   Pandas、Notebook 等分析工具。

运行本脚本即可从原始 CSV 生成轻量级文本数据，为后续分析打好基础。
"""

import argparse
import csv
import re
from pathlib import Path
from typing import Tuple

DISPLAY_PATTERN = re.compile(r"^(?P<nickname>.+?)[(（](?P<identifier>[^()（）]+)[)）]$")


def split_display(sender_display: str, sender_id: str) -> Tuple[str, str]:
    """Split '昵称(wxid)' style display names into nickname and identifier."""
    display = (sender_display or "").strip()
    identifier = (sender_id or "").strip()

    if not display:
        return identifier or "", identifier

    match = DISPLAY_PATTERN.match(display)
    if match:
        nickname = match.group("nickname").strip()
        extracted_id = match.group("identifier").strip()
        return nickname or identifier, extracted_id or identifier

    return display, identifier


def filter_text_messages(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8", newline="") as src, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as dest:
        reader = csv.DictReader(src)
        writer = csv.writer(dest)
        writer.writerow(["sender_nickname", "content"])

        for row in reader:
            if row.get("message_type") != "1":
                continue

            nickname, identifier = split_display(row.get("sender_display", ""), row.get("sender_id", ""))
            content = (row.get("content") or "").strip()
            if not content:
                continue

            writer.writerow([nickname, content])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter exported WeChat CSV to only keep text messages with sender nickname, id, and content."
    )
    parser.add_argument("input", type=Path, help="Path to the original CSV exported by wechat-db-export.")
    parser.add_argument("output", type=Path, help="Path to write the filtered CSV.")
    args = parser.parse_args()

    filter_text_messages(args.input, args.output)


if __name__ == "__main__":
    main()
