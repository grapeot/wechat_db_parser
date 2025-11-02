from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from .parser import build_message
from .model import Message

MESSAGE_DB_PATTERNS = ("MSG*.db",)
MULTI_DIR_NAME = "Multi"


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
    ) -> List[Message]:
        talker = talker.strip()
        if not talker:
            raise ValueError("talker must not be empty")

        start_ts = int(start.timestamp()) if start else None
        end_ts = int(end.timestamp()) if end else None

        remaining = limit if limit is not None else None
        collected: List[Message] = []

        for db_path in self.message_dbs:
            if remaining is not None and remaining <= 0:
                break

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
                if remaining is not None:
                    query += " LIMIT ?"
                    params.append(remaining)

                rows = conn.execute(query, params)
                for row in rows:
                    collected.append(build_message(row))
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            break

        collected.sort(key=lambda m: (m.timestamp, m.sequence))
        if limit is not None:
            collected = collected[:limit]
        return collected


def _db_sort_key(path: Path) -> tuple:
    name = path.stem  # e.g. MSG57
    numbers = re.findall(r"\d+", name)
    numeric = int(numbers[-1]) if numbers else 0
    return (path.parent.name != MULTI_DIR_NAME, numeric, str(path))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None
