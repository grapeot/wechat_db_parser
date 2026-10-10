#!/usr/bin/env python3
from __future__ import annotations

"""
群活跃度扫描工具：识别「过去 N 天从未发言」的群成员，并给出每人已沉默多久。

沉默时长的口径：
- 窗口内没发言但在保留历史里发过言：距今 = 现在 - 最后一次发言时间。
- 保留历史里从未发言：距今 = 现在 - 入群时间（从 type=10000 入群系统消息按昵称推断，
  仅在昵称能唯一对应到某个成员时才采用，否则不臆测）。
- 从未发言且没有可归因的入群记录：只给下界（≥ 保留历史最早消息距今），标注为下界。

「发言」指非系统消息（排除 type=10000 的入群/撤回/拍一拍）。
"""

import argparse
import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from wechat_db_parser.contacts import load_contact_book, load_group_directory
from wechat_db_parser.datasource import MessageDataSource
from wechat_db_parser.model import ContactDisplay, GroupMemberDisplay, Message

# 加入群聊系统消息：type=10000
JOIN_MSG_TYPE = 10000

# 入群短语与其前面的被引号包裹的名字
JOIN_PHRASE_RE = re.compile(r"(?:通过扫描[^，。]*加入群聊|加入了群聊)")
QUOTED_NAME_RE = re.compile(r'"+([^"]+?)"')

# 判定依据标签
BASIS_LAST_SPOKEN = "最后发言"
BASIS_JOIN_INFERRED = "入群时间(推断)"
BASIS_NO_JOIN = "无入群记录(下界)"


def find_chatroom_db(data_dir: Path) -> Path:
    candidates = [
        data_dir / "ChatRoomUser.db",
        data_dir / "Msg" / "ChatRoomUser.db",
        data_dir / "MicroMsg" / "ChatRoomUser.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"未找到 ChatRoomUser.db，请确认 --data-dir 正确，或使用 --chatroom-db 显式指定路径。"
    )


def find_contact_db(data_dir: Path) -> Path:
    candidates = [
        data_dir / "FTSContact.db",
        data_dir / "Msg" / "FTSContact.db",
        data_dir / "MicroMsg" / "FTSContact.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"未找到 FTSContact.db，请确认 --data-dir 正确，或使用 --contact-db 显式指定路径。"
        f"已尝试: {[str(c) for c in candidates]}"
    )


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


def member_name_keys(
    talker: str,
    member_id: str,
    contacts: dict[str, ContactDisplay],
    group_members: dict[Tuple[str, str], GroupMemberDisplay],
) -> Set[str]:
    """收集一个成员可能出现在入群系统消息里的所有昵称变体（小写）。"""
    keys: Set[str] = set()
    contact = contacts.get(member_id)
    if contact is not None:
        for value in (contact.nickname, contact.alias, contact.remark, contact.best_name()):
            if value:
                keys.add(value.strip().lower())
    group_info = group_members.get((talker, member_id))
    if group_info is not None:
        for value in (
            group_info.group_remark,
            group_info.nickname,
            group_info.alias,
            group_info.best_name(contact),
        ):
            if value:
                keys.add(value.strip().lower())
    return keys


def extract_join_invitees(text: str) -> List[str]:
    """从入群系统消息里抽取被邀请/加入的人名（小写）。

    支持：
    - "邀请人"邀请"被邀请人"加入了群聊 / 你邀请"被邀请人"加入了群聊 → 取最后一个名字
    - "A"、"B"加入了群聊（无"邀请"）→ 全部名字都算加入者
    - "X"通过扫描"群主"分享的二维码加入群聊 → 取"邀请"以外的加入者（此处即 X）
    """
    match = JOIN_PHRASE_RE.search(text)
    if not match:
        return []
    prefix = text[: match.start()]
    names = [n.strip().lower() for n in QUOTED_NAME_RE.findall(prefix) if n.strip()]
    if not names:
        return []
    if "邀请" in prefix:
        return [names[-1]]
    return names


def compute_last_spoken(messages: Iterable[Message]) -> Dict[str, datetime]:
    """每个发送者最后一次「发言」的时间。系统消息（type=10000）不算发言。"""
    last: Dict[str, datetime] = {}
    for msg in messages:
        if not msg.sender or msg.sender == msg.talker:
            continue
        if msg.msg_type == JOIN_MSG_TYPE:
            continue
        if msg.sender not in last or msg.timestamp > last[msg.sender]:
            last[msg.sender] = msg.timestamp
    return last


def compute_join_times(messages: Iterable[Message]) -> Dict[str, datetime]:
    """昵称（小写）→ 最早一次入群系统消息时间。"""
    joins: Dict[str, datetime] = {}
    for msg in messages:
        if msg.msg_type != JOIN_MSG_TYPE:
            continue
        text = msg.content or msg.raw_content or ""
        for name in extract_join_invitees(text):
            if name not in joins or msg.timestamp < joins[name]:
                joins[name] = msg.timestamp
    return joins


def format_duration(dt: datetime, now: datetime) -> str:
    days = (now - dt).days
    if days < 30:
        return f"{days} 天"
    if days < 365:
        return f"{days / 30.4:.1f} 个月"
    return f"{days / 365.25:.1f} 年"


def find_silent_members(
    data_dir: Path,
    talker: str,
    datasource: MessageDataSource,
    group_members: dict[Tuple[str, str], GroupMemberDisplay],
    contacts: dict[str, ContactDisplay],
    chatroom_db: Optional[Path] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Tuple[Set[str], Set[str], Set[str], Dict[str, Tuple[str, int, str]]]:
    """返回 (members, active_senders, silent, detail)。

    detail[member_id] = (display_duration, sort_days, basis)，仅覆盖沉默成员。
    """
    chatroom_db = chatroom_db or find_chatroom_db(data_dir)
    members = load_members(chatroom_db, talker)

    now = end or datetime.now()
    cutoff = start or (now - timedelta(days=365))

    # 只取 end 之前的消息，保证「截至 end」的判定正确；下界不设，保留窗口前的发言历史。
    messages: List[Message] = datasource.iter_messages(talker, end=now)
    last_spoken = compute_last_spoken(messages)
    join_times = compute_join_times(messages)

    active_senders = {
        sender for sender, ts in last_spoken.items() if ts >= cutoff and sender in members
    }
    silent = members - active_senders

    # 昵称 → 成员集合，用于识别歧义昵称（一个昵称对应多个成员时不归因入群时间）
    member_keys: Dict[str, Set[str]] = {
        mid: member_name_keys(talker, mid, contacts, group_members) for mid in members
    }
    key_to_members: Dict[str, Set[str]] = {}
    for mid, keys in member_keys.items():
        for key in keys:
            key_to_members.setdefault(key, set()).add(mid)

    retained_start = min((m.timestamp for m in messages), default=None)

    detail: Dict[str, Tuple[str, int, str]] = {}
    for member_id in silent:
        last = last_spoken.get(member_id)
        if last is not None:
            detail[member_id] = (format_duration(last, now), (now - last).days, BASIS_LAST_SPOKEN)
            continue

        join_ts = None
        for key in member_keys[member_id]:
            if len(key_to_members.get(key, ())) != 1:
                continue  # 昵称歧义，不归因
            candidate = join_times.get(key)
            if candidate is not None and (join_ts is None or candidate < join_ts):
                join_ts = candidate
        if join_ts is not None:
            detail[member_id] = (format_duration(join_ts, now), (now - join_ts).days, BASIS_JOIN_INFERRED)
        elif retained_start is not None:
            days = (now - retained_start).days
            detail[member_id] = (f"≥{format_duration(retained_start, now)}", days, BASIS_NO_JOIN)
        else:
            detail[member_id] = ("未知", 0, BASIS_NO_JOIN)

    return members, active_senders, silent, detail


def write_csv(path: Path, rows: Iterable[Tuple[str, str, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["silence_duration", "display_name", "member_id", "basis"])
        for duration, display, member_id, basis in rows:
            writer.writerow([duration, display, member_id, basis])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="统计「过去 N 天从未发言」的群成员，并给出每人已沉默多久。"
    )
    parser.add_argument("--data-dir", type=Path, required=True, help="解密后的数据目录（包含 MSG*.db 等文件）。")
    parser.add_argument(
        "--contact-db",
        type=Path,
        help="FTSContact.db 路径（若 data-dir 结构非标准可显式指定）。",
    )
    parser.add_argument(
        "--chatroom-db",
        type=Path,
        help="ChatRoomUser.db 路径（若 data-dir 结构非标准可显式指定）。",
    )
    parser.add_argument("--talker", type=str, required=True, help="群聊标识，可输入群名/备注或 chatroom ID。")
    parser.add_argument(
        "--output",
        type=Path,
        help="将沉默成员（含沉默时长）导出到 CSV。建议写到仓库外或已忽略的 output/ 目录。",
    )
    parser.add_argument(
        "--past-days",
        type=int,
        default=365,
        help="统计过去多少天内的发言（默认 365）。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="终端预览条数（默认 20，CSV 不受影响）。",
    )
    args = parser.parse_args()

    if args.past_days <= 0:
        parser.error("--past-days 必须为正整数。")
    if args.limit < 0:
        parser.error("--limit 不能为负。")

    data_dir = args.data_dir
    contact_db = args.contact_db or find_contact_db(data_dir)
    chatroom_db = args.chatroom_db or find_chatroom_db(data_dir)
    contacts = load_contact_book(contact_db)
    group_members = load_group_directory(contact_db)

    datasource = MessageDataSource(data_dir)
    talker = resolve_talker(args.talker, contacts, datasource.list_talkers())

    end = datetime.now()
    start = end - timedelta(days=args.past_days)

    members, active_senders, silent, detail = find_silent_members(
        data_dir,
        talker,
        datasource,
        group_members,
        contacts,
        chatroom_db=chatroom_db,
        start=start,
        end=end,
    )

    print(
        f"群聊 {talker}: 成员 {len(members)} 人，过去{args.past_days}天发言者 {len(active_senders)} 人，"
        f"过去{args.past_days}天未发言 {len(silent)} 人。"
    )

    if silent:
        rows = sorted(
            (
                detail[member_id][1],
                detail[member_id][0],
                normalize_display(talker, member_id, contacts, group_members),
                member_id,
                detail[member_id][2],
            )
            for member_id in silent
        )
        rows.sort(key=lambda row: row[0], reverse=True)  # 沉默最久的排前面
        print(f"\n{'沉默时长':<12}\t显示名\t判定依据")
        for _days, duration, display, _member_id, basis in rows[: args.limit]:
            print(f"{duration:<12}\t{display}\t{basis}")
        if len(rows) > args.limit:
            if args.output:
                print(f"...（共 {len(rows)} 人，完整列表见 CSV）")
            else:
                print(f"...（共 {len(rows)} 人，加 --output 导出完整列表）")
        if args.output:
            write_csv(
                args.output,
                (
                    (duration, display, member_id, basis)
                    for _days, duration, display, member_id, basis in rows
                ),
            )
            print(f"\n已写入沉默成员列表：{args.output}")
    else:
        print("没有满足条件的沉默成员。")


if __name__ == "__main__":
    main()
