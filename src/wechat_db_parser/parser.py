from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import lz4.block

from .model import ContactDisplay, GroupMemberDisplay, Message


def _read_varint(data: bytes, pos: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _skip_field(wire_type: int, data: bytes, pos: int) -> int:
    if wire_type == 0:  # varint
        _, pos = _read_varint(data, pos)
        return pos
    if wire_type == 1:  # 64-bit
        return pos + 8
    if wire_type == 2:  # length-delimited
        length, pos = _read_varint(data, pos)
        return pos + length
    if wire_type == 5:  # 32-bit
        return pos + 4
    raise ValueError(f"unsupported wire type {wire_type}")


def parse_bytes_extra(blob: Optional[bytes]) -> Dict[int, str]:
    if not blob:
        return {}

    pos = 0
    items: Dict[int, str] = {}

    while pos < len(blob):
        tag, pos = _read_varint(blob, pos)
        field = tag >> 3
        wire = tag & 7

        if field == 1 and wire == 2:
            length, pos = _read_varint(blob, pos)
            pos += length
            continue

        if field == 3 and wire == 2:
            length, pos = _read_varint(blob, pos)
            item_data = blob[pos : pos + length]
            pos += length

            item_pos = 0
            type_id: Optional[int] = None
            value: Optional[str] = None

            while item_pos < len(item_data):
                tag2, item_pos = _read_varint(item_data, item_pos)
                field2 = tag2 >> 3
                wire2 = tag2 & 7

                if field2 == 1:
                    type_id, item_pos = _read_varint(item_data, item_pos)
                elif field2 == 2 and wire2 == 2:
                    str_len, item_pos = _read_varint(item_data, item_pos)
                    raw = item_data[item_pos : item_pos + str_len]
                    item_pos += str_len
                    value = raw.decode("utf-8", errors="ignore")
                else:
                    item_pos = _skip_field(wire2, item_data, item_pos)

            if type_id is not None:
                items[type_id] = value or ""
            continue

        pos = _skip_field(wire, blob, pos)

    return items


def _normalize_path(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.replace("\\", "/")
    parts = value.split("/")
    if len(parts) > 1:
        return "/".join(parts[1:])
    return value


def _extract_xml(xml_string: str, path: Iterable[str]) -> Optional[str]:
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_string)
    except Exception:
        return None
    node = root
    for part in path:
        node = node.find(part)
        if node is None:
            return None
    value = node.text or ""
    return value.strip() or None


def _decode_content(msg_type: int, subtype: int, str_content: Optional[str], compress_content: Optional[bytes]) -> Tuple[str, str, Dict[str, str]]:
    text = str_content or ""
    raw = text
    meta: Dict[str, str] = {}

    if msg_type == 49 and compress_content:
        size_hint = max(len(compress_content) * 4, 4096)
        data: Optional[bytes] = None
        while size_hint <= 16 * 1024 * 1024:
            try:
                data = lz4.block.decompress(compress_content, uncompressed_size=size_hint)
                break
            except lz4.block.LZ4BlockError:
                size_hint *= 2
        if data is None:
            raw = text
        else:
            decoded = data.decode("utf-8", errors="ignore").rstrip("\x00")
            raw = decoded
            title = _extract_xml(decoded, ["appmsg", "title"])
            summary = _extract_xml(decoded, ["appmsg", "des"]) or _extract_xml(decoded, ["appmsg", "digest"])
            url = _extract_xml(decoded, ["appmsg", "url"])
            text = title or decoded.strip()
            if summary:
                text += f" | {summary}"
            if url:
                meta["url"] = url
            if title:
                meta["title"] = title
            if summary:
                meta["description"] = summary

    if msg_type != 1:
        preview = (text or "").strip()
        if preview.startswith("<?xml") or preview.startswith("<msg"):
            raw = text
            text = ""

    return text, raw, meta


def build_message(row: sqlite3.Row) -> Message:
    (
        msgsvr_id,
        sequence,
        create_time,
        str_talker,
        is_sender,
        msg_type,
        sub_type,
        str_content,
        compress_content,
        bytes_extra_blob,
    ) = row

    extras_map = parse_bytes_extra(bytes_extra_blob)

    is_chatroom = str_talker.endswith("@chatroom")
    sender = ""
    if is_chatroom:
        sender = extras_map.get(1, "")
    else:
        sender = "self" if is_sender else str_talker

    text, raw, meta = _decode_content(msg_type, sub_type, str_content, compress_content)

    extras: Dict[str, str] = {}
    extras.update(meta)

    if msg_type == 34 and extras_map.get(4):
        extras["voice_path"] = _normalize_path(extras_map.get(4)) or ""
    if msg_type == 3:
        if extras_map.get(4):
            extras["image_path"] = _normalize_path(extras_map.get(4)) or ""
        if extras_map.get(3):
            extras["thumb_path"] = _normalize_path(extras_map.get(3)) or ""
    if msg_type == 43 and extras_map.get(4):
        extras["video_path"] = _normalize_path(extras_map.get(4)) or ""

    timestamp = datetime.fromtimestamp(create_time)

    return Message(
        server_id=msgsvr_id or 0,
        sequence=sequence or 0,
        timestamp=timestamp,
        talker=str_talker,
        talker_display="",
        is_chatroom=is_chatroom,
        is_self=bool(is_sender),
        msg_type=msg_type or 0,
        sub_type=sub_type or 0,
        sender=sender,
        sender_display="",
        content=text.strip(),
        raw_content=raw,
        extras=extras,
    )


def annotate_messages(
    messages: List[Message],
    contacts: Dict[str, ContactDisplay],
    group_members: Dict[Tuple[str, str], GroupMemberDisplay],
) -> None:
    def contact_label(identifier: str) -> str:
        info = contacts.get(identifier)
        return info.label() if info is not None else identifier

    for msg in messages:
        msg.talker_display = contact_label(msg.talker)

        if msg.is_chatroom:
            key = (msg.talker, msg.sender)
            group_info = group_members.get(key)
            contact_info = contacts.get(msg.sender)
            label_name = ""
            if group_info is not None:
                label_name = group_info.best_name(contact_info)
            if contact_info is not None and not label_name:
                label_name = contact_info.best_name()
            if label_name:
                base_username = contact_info.username if contact_info else msg.sender
                if label_name == base_username:
                    msg.sender_display = label_name
                else:
                    msg.sender_display = f"{label_name}({base_username})"
            else:
                msg.sender_display = msg.sender
        else:
            msg.sender_display = "我" if msg.is_self else contact_label(msg.sender)

        if not msg.sender_display:
            msg.sender_display = msg.sender or ("我" if msg.is_self else "")
