from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .exporter import export_conversations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export WeChat conversations from MSG databases.")
    parser.add_argument("--data-dir", type=Path, required=True, help="解密后的 MSG 数据目录，例如 Msg/")
    parser.add_argument("--output", type=Path, required=True, help="导出 CSV 存放的目录")
    parser.add_argument("--talkers", nargs="*", help="指定要导出的会话（支持微信ID或备注/昵称，默认全部）")
    parser.add_argument("--start", type=str, help="起始时间，例如 2025-01-01 或 2025-01-01T12:00")
    parser.add_argument("--end", type=str, help="结束时间")
    parser.add_argument("--limit", type=int, help="每个会话导出的最大消息条数，用于调试")
    parser.add_argument("--workers", type=int, default=1, help="并行 worker 数（默认 1）")
    return parser


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间格式: {value}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    start = parse_date(args.start)
    end = parse_date(args.end)

    try:
        results = export_conversations(
            data_dir=args.data_dir,
            output_dir=args.output,
            talkers=args.talkers,
            start=start,
            end=end,
            limit=args.limit,
            workers=max(1, args.workers),
        )
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2

    if not results:
        print("没有导出任何会话。")
        return 1

    print(f"成功导出 {len(results)} 个会话：")
    for talker, path in results:
        print(f"- {talker} -> {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
