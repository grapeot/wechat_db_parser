from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from .exporter import export_conversations, export_public_articles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export WeChat data from decrypted databases.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    conversations = subparsers.add_parser("conversations", help="导出会话消息到 CSV")
    conversations.add_argument("--data-dir", type=Path, required=True, help="解密后的 MSG 数据目录，例如 Msg/")
    conversations.add_argument("--output", type=Path, required=True, help="导出 CSV 存放的目录")
    conversations.add_argument("--talkers", nargs="*", help="指定要导出的会话（支持微信ID或备注/昵称，默认全部）")
    conversations.add_argument("--start", type=str, help="起始时间，例如 2025-01-01 或 2025-01-01T12:00")
    conversations.add_argument("--end", type=str, help="结束时间")
    conversations.add_argument("--limit", type=int, help="每个会话导出的最大消息条数，用于调试")
    conversations.add_argument("--workers", type=int, default=1, help="并行 worker 数（默认 1）")
    conversations.set_defaults(handler=_run_conversations)

    official_articles = subparsers.add_parser("official-articles", help="从 PublicMsg.db 导出公众号文章卡片")
    official_articles.add_argument("--data-dir", type=Path, required=True, help="解密后的数据目录，例如 Msg/")
    official_articles.add_argument("--output", type=Path, required=True, help="导出文章 CSV 的文件路径")
    official_articles.add_argument("--accounts", nargs="*", help="指定公众号 ID 或名称，默认导出全部")
    official_articles.add_argument("--start", type=str, help="起始时间，例如 2025-01-01 或 2025-01-01T12:00")
    official_articles.add_argument("--end", type=str, help="结束时间")
    official_articles.add_argument("--limit", type=int, help="导出的最大文章数，用于调试")
    official_articles.set_defaults(handler=_run_official_articles)
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


def _run_conversations(args: argparse.Namespace) -> int:
    results = export_conversations(
        data_dir=args.data_dir,
        output_dir=args.output,
        talkers=args.talkers,
        start=parse_date(args.start),
        end=parse_date(args.end),
        limit=args.limit,
        workers=max(1, args.workers),
    )

    if not results:
        print("没有导出任何会话。")
        return 1

    print(f"成功导出 {len(results)} 个会话：")
    for talker, path in results:
        print(f"- {talker} -> {path}")
    return 0


def _run_official_articles(args: argparse.Namespace) -> int:
    count, output_path = export_public_articles(
        data_dir=args.data_dir,
        output_path=args.output,
        accounts=args.accounts,
        start=parse_date(args.start),
        end=parse_date(args.end),
        limit=args.limit,
    )

    if count <= 0:
        print(f"没有导出任何公众号文章，已写出空文件：{output_path}")
        return 1

    print(f"成功导出 {count} 条公众号文章 -> {output_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        handler: Callable[[argparse.Namespace], int] = args.handler
        return handler(args)
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
