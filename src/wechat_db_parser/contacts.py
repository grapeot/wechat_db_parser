from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Tuple

from .model import ContactDisplay, GroupMemberDisplay


def load_contact_book(db_path: Path) -> Dict[str, ContactDisplay]:
    contacts: Dict[str, ContactDisplay] = {}
    if not db_path.exists():
        return contacts

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT n.userName,
                   IFNULL(c.c0alias, ''),
                   IFNULL(c.c1nickname, ''),
                   IFNULL(c.c2remark, '')
            FROM FTSContact15_content AS c
            JOIN FTSContact15_MetaData AS m ON m.docid = c.docid
            JOIN NameToId AS n ON n.rowid = m.entityId
            """
        )
        for username, alias, nickname, remark in cur.fetchall():
            contacts[username] = ContactDisplay(
                username=username, alias=alias, nickname=nickname, remark=remark
            )
    finally:
        conn.close()
    return contacts


def load_group_directory(db_path: Path) -> Dict[Tuple[str, str], GroupMemberDisplay]:
    members: Dict[Tuple[str, str], GroupMemberDisplay] = {}
    if not db_path.exists():
        return members

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT chat.userName,
                   member.userName,
                   IFNULL(c.c0groupRemark, ''),
                   IFNULL(c.c1nickname, ''),
                   IFNULL(c.c2alias, '')
            FROM FTSChatroom15_content AS c
            JOIN FTSChatroom15_MetaData AS m ON m.docid = c.docid
            LEFT JOIN NameToId AS chat ON chat.rowid = m.groupTalkerId
            LEFT JOIN NameToId AS member ON member.rowid = m.talkerId
            WHERE chat.userName IS NOT NULL AND member.userName IS NOT NULL
            """
        )
        for chatroom, member, remark, nickname, alias in cur.fetchall():
            members[(chatroom, member)] = GroupMemberDisplay(
                chatroom=chatroom,
                member=member,
                group_remark=remark,
                nickname=nickname,
                alias=alias,
            )
    finally:
        conn.close()
    return members
