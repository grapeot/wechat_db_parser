from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wechat_db_parser import cli


def test_build_parser_supports_conversations_subcommand() -> None:
    args = cli.build_parser().parse_args(
        [
            "conversations",
            "--data-dir",
            "Msg",
            "--output",
            "out",
            "--talkers",
            "friend_a",
            "friend_b",
            "--workers",
            "4",
        ]
    )

    assert args.command == "conversations"
    assert args.data_dir == Path("Msg")
    assert args.output == Path("out")
    assert args.talkers == ["friend_a", "friend_b"]
    assert args.workers == 4


def test_main_routes_official_articles_subcommand(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_export_public_articles(data_dir, output_path, accounts, start, end, limit):
        captured["data_dir"] = data_dir
        captured["output_path"] = output_path
        captured["accounts"] = accounts
        captured["start"] = start
        captured["end"] = end
        captured["limit"] = limit
        return 1, output_path

    monkeypatch.setattr(cli, "export_public_articles", fake_export_public_articles)

    exit_code = cli.main(
        [
            "official-articles",
            "--data-dir",
            "Msg",
            "--output",
            "articles.csv",
            "--accounts",
            "科技早餐",
            "--start",
            "2026-03-01",
            "--end",
            "2026-03-02T12:00",
            "--limit",
            "5",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "data_dir": Path("Msg"),
        "output_path": Path("articles.csv"),
        "accounts": ["科技早餐"],
        "start": cli.parse_date("2026-03-01"),
        "end": cli.parse_date("2026-03-02T12:00"),
        "limit": 5,
    }
    assert "成功导出 1 条公众号文章 -> articles.csv" in capsys.readouterr().out
