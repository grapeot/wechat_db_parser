from __future__ import annotations

import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .model import Message, OfficialAccountArticle, OfficialAccountTimelineArticle
from .parser import build_message, decode_message_content, parse_biz_profile_resp_data

MESSAGE_DB_PATTERNS = ("MSG*.db",)
MULTI_DIR_NAME = "Multi"
MICRO_MSG_DB_NAME = "MicroMsg.db"
PUBLIC_MSG_DB_NAME = "PublicMsg.db"
PUBLIC_ARTICLE_SUBTYPES = (0, 5)
PUBLIC_ACCOUNT_ID_COLUMNS = ("UsrName", "userName", "UserName", "Alias")
PUBLIC_ACCOUNT_NAME_COLUMNS = (
    "NickName",
    "Nickname",
    "DisplayName",
    "Remark",
    "Alias",
    "UsrName",
    "userName",
)


class MessageDataSource:
    """High level access to WeChat MSG*.db files."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.message_dbs = self._discover_message_dbs()
        if not self.message_dbs:
            raise FileNotFoundError(f"No MSG*.db files found under {self.data_dir}")

    def _discover_message_dbs(self) -> List[Path]:
        paths: List[Path] = []
        search_roots = [self.data_dir]
        candidate = self.data_dir / "Msg"
        if candidate.is_dir():
            search_roots.append(candidate)
        for root in search_roots:
            for pattern in MESSAGE_DB_PATTERNS:
                paths.extend(root.glob(pattern))
                multi_dir = root / MULTI_DIR_NAME
                if multi_dir.is_dir():
                    paths.extend(multi_dir.glob(pattern))
        unique_paths = sorted({p.resolve() for p in paths}, key=_db_sort_key)
        return unique_paths

    def list_talkers(self) -> List[str]:
        talkers: Set[str] = set()
        for db_path in self.message_dbs:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for table in ("Name2ID", "Name2ID_v1"):
                    if _table_exists(conn, table):
                        rows = conn.execute(f"SELECT UsrName FROM {table}").fetchall()
                        talkers.update(row["UsrName"] for row in rows if row["UsrName"])
        return sorted(talkers)

    def iter_messages(
        self,
        talker: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
        workers: int = 1,
    ) -> List[Message]:
        talker = talker.strip()
        if not talker:
            raise ValueError("talker must not be empty")

        start_ts = int(start.timestamp()) if start else None
        end_ts = int(end.timestamp()) if end else None

        def query_db(db_path: Path) -> List[Message]:
            msgs: List[Message] = []
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                query = """
                    SELECT MsgSvrID, Sequence, CreateTime, StrTalker, IsSender,
                           Type, SubType, StrContent, CompressContent, BytesExtra
                    FROM MSG
                    WHERE StrTalker = ?
                """
                params: List[object] = [talker]
                if start_ts is not None:
                    query += " AND CreateTime >= ?"
                    params.append(start_ts)
                if end_ts is not None:
                    query += " AND CreateTime <= ?"
                    params.append(end_ts)
                query += " ORDER BY Sequence ASC"
                rows = conn.execute(query, params)
                for row in rows:
                    msgs.append(build_message(row))
            return msgs

        if workers <= 1:
            collected: List[Message] = []
            remaining = limit
            for db_path in self.message_dbs:
                if remaining is not None and remaining <= 0:
                    break
                msgs = query_db(db_path)
                for msg in msgs:
                    collected.append(msg)
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            break
        else:
            collected = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(query_db, path): path for path in self.message_dbs}
                for future in as_completed(futures):
                    collected.extend(future.result())

        collected.sort(key=lambda msg: (msg.timestamp, msg.sequence))
        if limit is not None:
            collected = collected[:limit]
        return collected


class PublicArticleDataSource:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.micro_msg_db = _discover_named_db(self.data_dir, MICRO_MSG_DB_NAME)
        self.public_msg_db = _discover_named_db(self.data_dir, PUBLIC_MSG_DB_NAME)
        if self.micro_msg_db is None and self.public_msg_db is None:
            raise FileNotFoundError(
                f"No {MICRO_MSG_DB_NAME} or {PUBLIC_MSG_DB_NAME} found under {self.data_dir}"
            )

    def iter_articles(
        self,
        accounts: Optional[Sequence[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[OfficialAccountArticle]:
        if self.micro_msg_db is not None:
            articles = self._iter_biz_feed_articles(accounts=accounts, start=start, end=end, limit=limit)
            if articles:
                return articles

        if self.public_msg_db is None:
            return []

        return self._iter_public_msg_articles(accounts=accounts, start=start, end=end, limit=limit)

    def iter_article_timeline(
        self,
        accounts: Optional[Sequence[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[OfficialAccountTimelineArticle]:
        micro_msg_db = self.micro_msg_db
        if micro_msg_db is None:
            return []

        start_ts = int(start.timestamp()) if start else None
        end_ts = int(end.timestamp()) if end else None
        with sqlite3.connect(micro_msg_db) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, "BizProfileV2"):
                return []
            profile_rows = self._load_biz_profile_rows(conn)
            account_mapping = self._build_biz_account_mapping(conn, profile_rows)
            resolved_accounts = _resolve_public_account_inputs(accounts, account_mapping)
            allowed_refs = {str(ref) for ref in resolved_accounts} if resolved_accounts else None

        timeline: List[OfficialAccountTimelineArticle] = []
        for talker_id, profile in profile_rows.items():
            if allowed_refs is not None and talker_id not in allowed_refs:
                continue
            account_id, account_name = account_mapping.get(talker_id, (talker_id, talker_id))
            articles = parse_biz_profile_resp_data(
                profile.get("RespData"),
                account_id=account_id,
                account_name=account_name,
            )
            for article in articles:
                article_ts = int(article.timestamp.timestamp())
                if start_ts is not None and article_ts < start_ts:
                    continue
                if end_ts is not None and article_ts > end_ts:
                    continue
                timeline.append(article)

        timeline.sort(key=lambda article: (article.timestamp, article.account_id, article.article_index))
        if limit is not None:
            timeline = timeline[-limit:]
        return timeline

    def _iter_biz_feed_articles(
        self,
        accounts: Optional[Sequence[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[OfficialAccountArticle]:
        micro_msg_db = self.micro_msg_db
        if micro_msg_db is None:
            return []
        start_ts = int(start.timestamp()) if start else None
        end_ts = int(end.timestamp()) if end else None

        with sqlite3.connect(micro_msg_db) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, "BizSessionNewFeeds"):
                return []

            profile_rows = self._load_biz_profile_rows(conn)
            account_mapping = self._build_biz_account_mapping(conn, profile_rows)
            resolved_accounts = _resolve_public_account_inputs(accounts, account_mapping)
            allowed_refs = {str(ref) for ref in resolved_accounts} if resolved_accounts else None

            query = (
                "SELECT TalkerId, BizName, Title, Desc, Type, UnreadCount, UpdateTime, CreateTime, BizAttrVersion "
                "FROM BizSessionNewFeeds WHERE Type = 49"
            )
            params: List[object] = []
            if start_ts is not None:
                query += " AND UpdateTime >= ?"
                params.append(start_ts)
            if end_ts is not None:
                query += " AND UpdateTime <= ?"
                params.append(end_ts)
            query += " ORDER BY UpdateTime ASC"
            rows = conn.execute(query, params).fetchall()

        articles: List[OfficialAccountArticle] = []
        for row in rows:
            account_ref = str(row["TalkerId"])
            if allowed_refs is not None and account_ref not in allowed_refs:
                continue
            article = _build_biz_feed_article(row, account_mapping, profile_rows)
            if article is None:
                continue
            articles.append(article)
            if limit is not None and len(articles) >= limit:
                break
        return articles

    def _iter_public_msg_articles(
        self,
        accounts: Optional[Sequence[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[OfficialAccountArticle]:
        public_msg_db = self.public_msg_db
        if public_msg_db is None:
            return []

        start_ts = int(start.timestamp()) if start else None
        end_ts = int(end.timestamp()) if end else None

        with sqlite3.connect(public_msg_db) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, "PublicMsg"):
                raise ValueError(f"PublicMsg table not found in {public_msg_db}")

            account_mapping = self._load_public_account_mapping(conn)
            public_msg_columns = set(_table_columns(conn, "PublicMsg"))
            talker_column = _pick_column(public_msg_columns, ("TalkerId", "TalkerID", "PublicTalkerId", "PublicID", "StrTalker"))
            create_time_column = _pick_column(public_msg_columns, ("CreateTime",))
            type_column = _pick_column(public_msg_columns, ("Type",))
            subtype_column = _pick_column(public_msg_columns, ("SubType",))
            str_content_column = _pick_column(public_msg_columns, ("StrContent",))
            compress_content_column = _pick_column(public_msg_columns, ("CompressContent",))

            if not all((
                talker_column,
                create_time_column,
                type_column,
                subtype_column,
                str_content_column,
                compress_content_column,
            )):
                raise ValueError("PublicMsg schema missing required columns for article export")

            query = (
                f"SELECT {talker_column} AS account_ref, "
                f"{create_time_column} AS create_time, "
                f"{type_column} AS msg_type, "
                f"{subtype_column} AS sub_type, "
                f"{str_content_column} AS str_content, "
                f"{compress_content_column} AS compress_content "
                "FROM PublicMsg "
                f"WHERE {type_column} = 49 "
                f"AND {subtype_column} IN ({', '.join(str(value) for value in PUBLIC_ARTICLE_SUBTYPES)})"
            )
            params: List[object] = []
            if start_ts is not None:
                query += f" AND {create_time_column} >= ?"
                params.append(start_ts)
            if end_ts is not None:
                query += f" AND {create_time_column} <= ?"
                params.append(end_ts)
            query += f" ORDER BY {create_time_column} ASC"
            rows = conn.execute(query, params).fetchall()

        resolved_accounts = _resolve_public_account_inputs(accounts, account_mapping)
        allowed_refs = {str(ref) for ref in resolved_accounts} if resolved_accounts else None

        articles: List[OfficialAccountArticle] = []
        for row in rows:
            account_ref = row["account_ref"]
            if allowed_refs is not None and str(account_ref) not in allowed_refs:
                continue
            article = _build_official_account_article(row, account_mapping)
            if article is None:
                continue
            articles.append(article)
            if limit is not None and len(articles) >= limit:
                break
        return articles

    def _load_public_account_mapping(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Tuple[str, str]]:
        should_close = conn is None
        if conn is None:
            public_msg_db = self.public_msg_db
            if public_msg_db is None:
                return {}
            conn = sqlite3.connect(public_msg_db)
            conn.row_factory = sqlite3.Row
        try:
            if not _table_exists(conn, "PublicNameToID"):
                return {}
            rows = conn.execute("SELECT rowid AS mapping_id, * FROM PublicNameToID").fetchall()
            mapping: Dict[str, Tuple[str, str]] = {}
            for row in rows:
                row_dict = dict(row)
                account_id = _first_non_empty(row_dict, PUBLIC_ACCOUNT_ID_COLUMNS) or str(row_dict["mapping_id"])
                account_name = _first_non_empty(row_dict, PUBLIC_ACCOUNT_NAME_COLUMNS) or account_id
                mapping[str(row_dict["mapping_id"])] = (account_id, account_name)
            return mapping
        finally:
            if should_close and conn is not None:
                conn.close()

    def _load_biz_profile_rows(self, conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
        if not _table_exists(conn, "BizProfileV2"):
            return {}
        rows = conn.execute(
            "SELECT TalkerId, UserName, ArticleCount, FriendSubscribedCount, IsSubscribed, TimeStamp, RespData FROM BizProfileV2"
        ).fetchall()
        return {str(row["TalkerId"]): dict(row) for row in rows}

    def _build_biz_account_mapping(
        self,
        conn: sqlite3.Connection,
        profile_rows: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Tuple[str, str]]:
        rows = conn.execute("SELECT TalkerId, BizName, Title FROM BizSessionNewFeeds").fetchall()
        mapping: Dict[str, Tuple[str, str]] = {}
        for row in rows:
            talker_id = str(row["TalkerId"])
            profile = profile_rows.get(talker_id, {})
            account_id = str(profile.get("UserName") or row["BizName"] or talker_id).strip()
            account_name = str(row["Title"] or account_id).strip()
            mapping[talker_id] = (account_id, account_name)
        return mapping


def _db_sort_key(path: Path) -> tuple[int, int, str]:
    name = path.stem
    numbers = re.findall(r"\d+", name)
    numeric = int(numbers[-1]) if numbers else 0
    return (path.parent.name != MULTI_DIR_NAME, numeric, str(path))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _discover_named_db(data_dir: Path, filename: str) -> Optional[Path]:
    candidates = [data_dir / filename, data_dir / "Msg" / filename]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _pick_column(columns: Set[str], candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _first_non_empty(values: Dict[str, Any], candidates: Sequence[str]) -> str:
    for candidate in candidates:
        value = values.get(candidate)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _resolve_public_account_inputs(
    inputs: Optional[Sequence[str]],
    mapping: Dict[str, Tuple[str, str]],
) -> List[str]:
    if not inputs:
        return []

    searchable: Dict[str, str] = {}
    for ref, (account_id, account_name) in mapping.items():
        for candidate in {ref, account_id, account_name, f"{account_name}({account_id})"}:
            text = candidate.strip()
            if text:
                searchable[text.lower()] = ref

    resolved: List[str] = []
    for item in inputs:
        candidate = item.strip()
        if not candidate:
            continue
        if candidate in mapping:
            resolved.append(candidate)
            continue
        ref = searchable.get(candidate.lower())
        if ref is None:
            label_only = candidate.split("(")[0].strip().lower()
            ref = searchable.get(label_only)
        if ref is None:
            raise ValueError(f"无法解析公众号标识：{item}")
        resolved.append(ref)
    return resolved


def _extract_first_mp_url(blob: Optional[bytes]) -> str:
    if not blob:
        return ""
    text = blob.decode("utf-8", errors="ignore")
    match = re.search(r"http://mp\.weixin\.qq\.com/s\?__biz=[^\s\x00\x01-\x1f\"<>]+", text)
    return match.group(0).strip().rstrip(":;,)") if match else ""


def _build_biz_feed_article(
    row: sqlite3.Row,
    mapping: Dict[str, Tuple[str, str]],
    profile_rows: Dict[str, Dict[str, Any]],
) -> Optional[OfficialAccountArticle]:
    account_ref = str(row["TalkerId"])
    account_id, account_name = mapping.get(account_ref, (account_ref, account_ref))
    title = str(row["Desc"] or "").strip()
    if not title:
        return None
    profile = profile_rows.get(account_ref, {})
    url = _extract_first_mp_url(profile.get("RespData"))
    return OfficialAccountArticle(
        timestamp=datetime.fromtimestamp(int(row["UpdateTime"] or 0)),
        account_id=account_id,
        account_name=account_name,
        title=title,
        url=url,
        summary="",
        msg_type=int(row["Type"] or 0),
        sub_type=0,
        raw_content="",
    )


def _build_official_account_article(
    row: sqlite3.Row,
    mapping: Dict[str, Tuple[str, str]],
) -> Optional[OfficialAccountArticle]:
    msg_type = int(row["msg_type"] or 0)
    sub_type = int(row["sub_type"] or 0)
    text, raw, meta = decode_message_content(msg_type, sub_type, row["str_content"], row["compress_content"])

    title = (meta.get("title") or text or "").strip()
    url = (meta.get("url") or "").strip()
    summary = (meta.get("description") or "").strip()
    if not any((title, url, summary)):
        return None

    account_ref = str(row["account_ref"])
    account_id, account_name = mapping.get(account_ref, (account_ref, account_ref))
    return OfficialAccountArticle(
        timestamp=datetime.fromtimestamp(int(row["create_time"] or 0)),
        account_id=account_id,
        account_name=account_name,
        title=title,
        url=url,
        summary=summary,
        msg_type=msg_type,
        sub_type=sub_type,
        raw_content=raw,
    )
