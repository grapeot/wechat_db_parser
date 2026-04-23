from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import lz4.block

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wechat_db_parser.exporter import export_public_articles


def test_export_public_articles_prefers_biz_session_new_feeds(tmp_path: Path) -> None:
    data_dir = tmp_path / "Msg"
    data_dir.mkdir()
    _build_micro_msg_fixture(data_dir / "MicroMsg.db")
    _build_public_msg_fixture(data_dir / "PublicMsg.db")

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

    expected_timestamp = datetime.fromtimestamp(1776826800).isoformat(sep=" ", timespec="seconds")

    assert rows == [
        ["timestamp", "account_name", "account_id", "title", "url", "summary"],
        [
            expected_timestamp,
            "科技早餐",
            "gh_breakfast",
            "今天的头条",
            "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=2247483647&idx=1&sn=abcdef1234567890#rd2",
            "",
        ],
    ]


def test_export_public_articles_falls_back_to_public_msg(tmp_path: Path) -> None:
    data_dir = tmp_path / "Msg"
    data_dir.mkdir()
    _build_public_msg_fixture(data_dir / "PublicMsg.db")

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


def _build_micro_msg_fixture(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE BizProfileV2 (TalkerId INTEGER PRIMARY KEY, UserName TEXT, ServiceType INTEGER, ArticleCount INTEGER, FriendSubscribedCount INTEGER, IsSubscribed INTEGER, Offset TEXT, IsEnd INTEGER, TimeStamp INTEGER, Reserved1 INTEGER, Reserved2 INTEGER, Reserved3 TEXT, Reserved4 TEXT, RespData BLOB, Reserved5 BLOB)"
        )
        conn.execute(
            "CREATE TABLE BizSessionNewFeeds (TalkerId INTEGER PRIMARY KEY, BizName TEXT, Title TEXT, Desc TEXT, Type INTEGER, UnreadCount INTEGER, UpdateTime INTEGER, CreateTime INTEGER, BizAttrVersion INTEGER, Reserved1 INTEGER, Reserved2 INTEGER, Reserved3 TEXT, Reserved4 TEXT, Reserved5 BLOB)"
        )
        conn.execute(
            "INSERT INTO BizProfileV2 (TalkerId, UserName, ArticleCount, FriendSubscribedCount, IsSubscribed, TimeStamp, RespData) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                101,
                "gh_breakfast",
                123,
                0,
                1,
                1776826800,
                _fake_biz_profile_blob(
                    title="今天的头条",
                    url="http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=2247483647&idx=1&sn=abcdef1234567890#rd2",
                ),
            ),
        )
        conn.execute(
            "INSERT INTO BizSessionNewFeeds (TalkerId, BizName, Title, Desc, Type, UnreadCount, UpdateTime, CreateTime, BizAttrVersion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "gh_breakfast", "科技早餐", "今天的头条", 49, 1, 1776826800, 1776826800, 11),
        )
        conn.commit()
    finally:
        conn.close()


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


def _fake_biz_profile_blob(title: str, url: str) -> bytes:
    return f"{title}\x01{url}\x01https://mmbiz.qpic.cn/sample.jpg".encode("utf-8")
