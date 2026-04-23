from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import lz4.block

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wechat_db_parser.exporter import export_public_article_timeline, export_public_articles
from wechat_db_parser.parser import parse_biz_profile_resp_data


def test_export_public_articles_prefers_biz_session_new_feeds(tmp_path: Path) -> None:
    data_dir = tmp_path / "Msg"
    data_dir.mkdir()
    _build_micro_msg_fixture(data_dir / "MicroMsg.db")
    _build_public_msg_fixture(data_dir / "PublicMsg.db")

    output_path = tmp_path / "output" / "official_articles.csv"
    count, written_path = export_public_articles(
        data_dir=tmp_path,
        output_path=output_path,
        accounts=["Tech Breakfast"],
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
            "Tech Breakfast",
            "gh_breakfast",
            "Today headline",
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
        accounts=["Tech Breakfast"],
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
            "Tech Breakfast",
            "gh_breakfast",
            "Morning digest",
            "https://mp.weixin.qq.com/s/breakfast",
            "Three AI stories today",
        ],
    ]


def test_parse_biz_profile_resp_data_extracts_article_timeline() -> None:
    blob = _build_biz_profile_resp_data_blob(
        [
            {"mid": 101, "created": 1776826800, "updated": 1776827800, "index": 1, "title": "First", "summary": "Summary 1", "url": "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=101&idx=1&sn=aaa#rd2", "cover": "https://mmbiz.qpic.cn/cover1.jpg", "thumb": "https://mmbiz.qpic.cn/thumb1.jpg"},
            {"mid": 102, "created": 1776828800, "updated": 1776829800, "index": 2, "title": "Second", "summary": "Summary 2", "url": "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=102&idx=1&sn=bbb#rd2", "cover": "https://mmbiz.qpic.cn/cover2.jpg", "thumb": "https://mmbiz.qpic.cn/thumb2.jpg"},
        ]
    )
    articles = parse_biz_profile_resp_data(blob, account_id="gh_breakfast", account_name="Tech Breakfast")
    assert [(article.title, article.url, article.cover_image_url, article.cover_thumb_url, article.article_index) for article in articles] == [
        ("First", "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=101&idx=1&sn=aaa#rd2", "https://mmbiz.qpic.cn/cover1.jpg", "https://mmbiz.qpic.cn/thumb1.jpg", 1),
        ("Second", "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=102&idx=1&sn=bbb#rd2", "https://mmbiz.qpic.cn/cover2.jpg", "https://mmbiz.qpic.cn/thumb2.jpg", 2),
    ]


def test_export_public_article_timeline_markdown(tmp_path: Path) -> None:
    data_dir = tmp_path / "Msg"
    data_dir.mkdir()
    _build_micro_msg_fixture(
        data_dir / "MicroMsg.db",
        timeline_articles=[
            {"mid": 101, "created": 1776826800, "updated": 1776827800, "index": 1, "title": "First article", "summary": "Summary 1", "url": "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=101&idx=1&sn=aaa#rd2", "cover": "https://mmbiz.qpic.cn/cover1.jpg", "thumb": "https://mmbiz.qpic.cn/thumb1.jpg"},
            {"mid": 102, "created": 1776828800, "updated": 1776829800, "index": 2, "title": "Second article", "summary": "Summary 2", "url": "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=102&idx=1&sn=bbb#rd2", "cover": "https://mmbiz.qpic.cn/cover2.jpg", "thumb": "https://mmbiz.qpic.cn/thumb2.jpg"},
        ],
    )
    output_path = tmp_path / "timeline.md"
    count, written_path = export_public_article_timeline(
        data_dir=tmp_path,
        output_path=output_path,
        accounts=["Tech Breakfast"],
        output_format="markdown",
    )
    assert count == 2
    assert written_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "## Tech Breakfast" in text
    assert "### First article" in text
    assert "![First article](https://mmbiz.qpic.cn/cover1.jpg)" in text


def _build_micro_msg_fixture(db_path: Path, timeline_articles: list[dict[str, object]] | None = None) -> None:
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
                _build_biz_profile_resp_data_blob(timeline_articles or [
                    {"mid": 2247483647, "created": 1776826800, "updated": 1776826800, "index": 1, "title": "Today headline", "summary": "Today summary", "url": "http://mp.weixin.qq.com/s?__biz=MzU5QkZBS0VT&mid=2247483647&idx=1&sn=abcdef1234567890#rd2", "cover": "https://mmbiz.qpic.cn/sample.jpg", "thumb": "https://mmbiz.qpic.cn/sample_thumb.jpg"}
                ]),
            ),
        )
        conn.execute(
            "INSERT INTO BizSessionNewFeeds (TalkerId, BizName, Title, Desc, Type, UnreadCount, UpdateTime, CreateTime, BizAttrVersion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "gh_breakfast", "Tech Breakfast", "Today headline", 49, 1, 1776826800, 1776826800, 11),
        )
        conn.commit()
    finally:
        conn.close()


def _build_public_msg_fixture(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE PublicNameToID (UsrName TEXT NOT NULL, NickName TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE PublicMsg (TalkerId INTEGER NOT NULL, CreateTime INTEGER NOT NULL, Type INTEGER NOT NULL, SubType INTEGER NOT NULL, StrContent TEXT, CompressContent BLOB)"
        )

        conn.execute("INSERT INTO PublicNameToID (UsrName, NickName) VALUES (?, ?)", ("gh_breakfast", "Tech Breakfast"))
        conn.execute("INSERT INTO PublicNameToID (UsrName, NickName) VALUES (?, ?)", ("gh_other", "Other Account"))

        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1772352000, 49, 5, "", _compress_article_xml(title="Morning digest", url="https://mp.weixin.qq.com/s/breakfast", summary="Three AI stories today")),
        )
        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (2, 1772352600, 49, 0, "", _compress_article_xml(title="Should be filtered out", url="https://mp.weixin.qq.com/s/other", summary="Filter check")),
        )
        conn.execute(
            "INSERT INTO PublicMsg (TalkerId, CreateTime, Type, SubType, StrContent, CompressContent) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1772353200, 49, 19, "", _compress_article_xml(title="Chat history card", url="https://mp.weixin.qq.com/s/ignored", summary="This subtype should not export")),
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


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def _field_varint(field: int, value: int) -> bytes:
    return _encode_varint((field << 3) | 0) + _encode_varint(value)


def _field_bytes(field: int, value: bytes) -> bytes:
    return _encode_varint((field << 3) | 2) + _encode_varint(len(value)) + value


def _field_text(field: int, value: str) -> bytes:
    return _field_bytes(field, value.encode("utf-8"))


def _build_biz_profile_resp_data_blob(articles: list[dict[str, object]]) -> bytes:
    item_blobs = []
    for article in articles:
        time_meta = b"".join([
            _field_varint(1, int(article["mid"])),
            _field_varint(2, int(article["created"])),
            _field_varint(3, int(article["updated"])),
            _field_varint(4, int(article["index"])),
            _field_varint(5, 0),
        ])
        content_meta = b"".join([
            _field_text(1, str(article["title"])),
            _field_text(3, str(article["summary"])),
            _field_text(5, str(article["url"])),
            _field_text(7, str(article["cover"])),
            _field_text(8, str(article["thumb"])),
            _field_varint(10, 0),
        ])
        envelope = _field_bytes(1, time_meta) + _field_bytes(2, content_meta)
        item_blobs.append(_field_bytes(6, envelope))
    feed = b"".join(_field_bytes(1, item_blob) for item_blob in item_blobs)
    return _field_bytes(4, feed)
