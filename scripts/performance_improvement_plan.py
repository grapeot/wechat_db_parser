#!/usr/bin/env python3
from __future__ import annotations

"""
群活跃度扫描工具：识别在整个聊天历史中从未发言的群成员。

使用场景：
1. 结合 `ChatRoomUser.db` 获得群成员全集；
2. 遍历消息数据库统计实际发言者；
3. 计算二者差集，输出“沉默成员”名单，便于制定后续运营或邀请计划。

输出结果默认打印统计摘要，可选 `--output` 将沉默成员写入 CSV（字段为
`member_id`, `display_name`）。脚本依赖 `wechat_db_parser` 提供的联系人与消息读取逻辑，
支持群名/备注模糊匹配。
"""

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Sequence, Set, Tuple

from wechat_db_parser.contacts import load_contact_book, load_group_directory
from wechat_db_parser.datasource import MessageDataSource
from wechat_db_parser.model import ContactDisplay, GroupMemberDisplay


def find_chatroom_db(data_dir: Path) -> Path:
    candidates = [
        data_dir / "ChatRoomUser.db",
        data_dir / "Msg" / "ChatRoomUser.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("未找到 ChatRoomUser.db，请确认 data_dir 设置正确。")


def load_members(chatroom_db: Path, talker: str) -> Set[str]:
    conn = sqlite3.connect(chatroom_db)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user.UsrName
            FROM ChatRoomUser AS cru
            JOIN ChatRoomUserNameToId AS chatroom ON chatroom.rowid = cru.ChatRoomId
            JOIN ChatRoomUserNameToId AS user ON user.rowid = cru.UserId
            WHERE chatroom.UsrName = ?
            """,
            (talker,),
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def normalize_display(
    talker: str,
    member_id: str,
    contacts: dict[str, ContactDisplay],
    group_members: dict[Tuple[str, str], GroupMemberDisplay],
) -> str:
    contact = contacts.get(member_id)
    group_info = group_members.get((talker, member_id))

    if group_info is not None:
        label = group_info.best_name(contact)
        if label:
            return label
    if contact is not None:
        label = contact.best_name()
        if label:
            return label
    return member_id


def resolve_talker(
    talker_input: str,
    contacts: dict[str, ContactDisplay],
    available: Sequence[str],
) -> str:
    candidate = talker_input.strip()
    if not candidate:
        raise ValueError("必须提供有效的群标识。")
    if candidate in available:
        return candidate

    mapping: dict[str, str] = {}
    for contact in contacts.values():
        names: Set[str] = {
            contact.best_name(),
            contact.alias,
            contact.nickname,
            contact.remark,
            contact.label(),
        }
        for name in names:
            if name:
                mapping[name.lower()] = contact.username

    lowered = candidate.lower()
    if lowered in mapping and mapping[lowered] in available:
        return mapping[lowered]

    label_lower = candidate.split("(")[0].strip().lower()
    if label_lower in mapping and mapping[label_lower] in available:
        return mapping[label_lower]

    raise ValueError(f"无法解析群标识：{talker_input}")


def find_silent_members(
    data_dir: Path,
    talker: str,
    datasource: MessageDataSource,
) -> Tuple[Set[str], Set[str], Set[str]]:
    chatroom_db = find_chatroom_db(data_dir)
    members = load_members(chatroom_db, talker)

    messages = datasource.iter_messages(talker)
    active_senders = {msg.sender for msg in messages if msg.sender and msg.sender != talker}

    silent = members - active_senders
    return members, active_senders, silent


def write_csv(path: Path, rows: Iterable[Tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["member_id", "display_name"])
        for member_id, display in rows:
            writer.writerow([member_id, display])


def main() -> None:
    parser = argparse.ArgumentParser(description="统计指定群聊的沉默成员名单。")
    parser.add_argument("--data-dir", type=Path, required=True, help="解密后的数据目录（包含 MSG*.db 等文件）。")
    parser.add_argument("--talker", type=str, required=True, help="群聊标识，可输入群名/备注或 chatroom ID。")
    parser.add_argument("--output", type=Path, help="将沉默成员导出到 CSV 文件。")
    args = parser.parse_args()

    data_dir = args.data_dir
    contact_db = find_contact_db(data_dir)
    contacts = load_contact_book(contact_db)
    group_members = load_group_directory(contact_db)

    datasource = MessageDataSource(data_dir)
    talker = resolve_talker(args.talker, contacts, datasource.list_talkers())

    members, active_senders, silent = find_silent_members(data_dir, talker, datasource)

    print(f"群聊 {talker}: 成员 {len(members)} 人，发言者 {len(active_senders)} 人，沉默成员 {len(silent)} 人。")

    if silent:
        preview = sorted(
            (member_id, normalize_display(talker, member_id, contacts, group_members)) for member_id in silent
        )
        for member_id, display in preview[:20]:
            print(f"- {display} ({member_id})")
        if args.output:
            write_csv(args.output, preview)
            print(f"已写入沉默成员列表：{args.output}")
    else:
        print("所有成员都至少发言过一次。")


def find_contact_db(data_dir: Path) -> Path:
    candidates = [
        data_dir / "FTSContact.db",
        data_dir / "Msg" / "FTSContact.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("未找到 FTSContact.db，请确认 data_dir 设置正确。")


if __name__ == "__main__":
    main()
