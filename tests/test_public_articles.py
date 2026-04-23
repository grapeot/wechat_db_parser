from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import lz4.block

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wechat_db_parser.exporter import export_public_articles


def test_export_public_articles_writes_normalized_rows(tmp_path: Path) -> None:
    data_dir = tmp_path / "Msg"
    data_dir.mkdir()
    db_path = data_dir / "PublicMsg.db"
    _build_public_msg_fixture(db_path)

    output_path = tmp_path / "output" / "official_articles.csv"
    count, written_path = export_public_articles(
        data_dir=tmp_path,
        output_path=output_path,
        accounts=["科技早餐"],
    )

    assert count == 1
    assert written_path == output_path

    with output_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))

    expected_timestamp = datetime.fromtimestamp(1772352000).isoformat(sep=" ", timespec="seconds")

    assert rows == [
        ["timestamp", "account_name", "account_id", "title", "url", "summary"],
        [
            expected_timestamp,
            "科技早餐",
            "gh_breakfast",
            "早报精选",
            "https://mp.weixin.qq.com/s/breakfast",
            "今天的三条 AI 新闻",
        ],
    ]


def _build_public_msg_fixture(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE PublicNameToID (UsrName TEXT NOT NULL, NickName TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE PublicMsg (TalkerId INTEGER NOT NULL, CreateTime INTEGER NOT NULL, Type INTEGER NOT NULL, SubType INTEGER NOT NULL, StrContent TEXT, CompressContent BLOB)"
        )

        conn.execute(
            "INSERT INTO PublicNameToID (UsrName, NickName) VALUES (?, ?)",
            ("gh_breakfast", "科技早餐"),
        )
        conn.execute(
            "INSERT INTO PublicNameToID (UsrName, NickName) VALUES (?, ?)",
            ("gh_other", "另一账号"),
        )

        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                1772352000,
                49,
                5,
                "",
                _compress_article_xml(
                    title="早报精选",
                    url="https://mp.weixin.qq.com/s/breakfast",
                    summary="今天的三条 AI 新闻",
                ),
            ),
        )
        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (
                2,
                1772352600,
                49,
                0,
                "",
                _compress_article_xml(
                    title="应该被账号过滤掉",
                    url="https://mp.weixin.qq.com/s/other",
                    summary="过滤验证",
                ),
            ),
        )
        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                1772353200,
                49,
                19,
                "",
                _compress_article_xml(
                    title="聊天记录卡片",
                    url="https://mp.weixin.qq.com/s/ignored",
                    summary="这个 subtype 不应导出",
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _compress_article_xml(title: str, url: str, summary: str) -> bytes:
    xml = (
        "<msg><appmsg>"
        f"<title>{title}</title>"
        f"<des>{summary}</des>"
        f"<url>{url}</url>"
        "</appmsg></msg>"
    )
    return lz4.block.compress(xml.encode("utf-8"), store_size=False)
