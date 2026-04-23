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
            "Tech Breakfast",
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
        "accounts": ["Tech Breakfast"],
        "start": cli.parse_date("2026-03-01"),
        "end": cli.parse_date("2026-03-02T12:00"),
        "limit": 5,
    }
    assert "成功导出 1 条公众号文章 -> articles.csv" in capsys.readouterr().out


def test_main_routes_official_articles_timeline_subcommand(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_export_public_article_timeline(data_dir, output_path, accounts, start, end, limit, output_format):
        captured["data_dir"] = data_dir
        captured["output_path"] = output_path
        captured["accounts"] = accounts
        captured["start"] = start
        captured["end"] = end
        captured["limit"] = limit
        captured["output_format"] = output_format
        return 3, output_path

    monkeypatch.setattr(cli, "export_public_article_timeline", fake_export_public_article_timeline)

    exit_code = cli.main(
        [
            "official-articles-timeline",
            "--data-dir",
            "Msg",
            "--output",
            "timeline.md",
            "--accounts",
            "GeekPark",
            "--start",
            "2026-03-01",
            "--end",
            "2026-03-02T12:00",
            "--limit",
            "3",
            "--format",
            "markdown",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "data_dir": Path("Msg"),
        "output_path": Path("timeline.md"),
        "accounts": ["GeekPark"],
        "start": cli.parse_date("2026-03-01"),
        "end": cli.parse_date("2026-03-02T12:00"),
        "limit": 3,
        "output_format": "markdown",
    }
    assert "Successfully exported 3 official account timeline articles -> timeline.md" in capsys.readouterr().out
