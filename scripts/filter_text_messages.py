#!/usr/bin/env python3
from __future__ import annotations

"""
Utilities for trimming the raw `wechat-db-export` CSV down to a text-only dataset.

The original export混杂了进群提示、系统通知、媒体占位等噪声信息，而且
`sender_display` 往往是“昵称(wxid)”的组合形式。为了做后续的内容分析、
建模或向量化，我们需要：

1. 只保留 message_type == 1 的纯文本消息；
2. 将“昵称(wxid)”切分成易于聚合的 `sender_nickname` / `sender_id`；
3. 去掉空白内容行，便于直接喂给 Pandas / Notebook 等分析工具。

运行本脚本即可从原始 CSV 生成一个轻量的 text-only CSV，为后续分析打好基础。
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
        writer.writerow(["sender_nickname", "sender_id", "content"])

        for row in reader:
            if row.get("message_type") != "1":
                continue

            nickname, identifier = split_display(row.get("sender_display", ""), row.get("sender_id", ""))
            content = (row.get("content") or "").strip()
            if not content:
                continue

            writer.writerow([nickname, identifier, content])


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
