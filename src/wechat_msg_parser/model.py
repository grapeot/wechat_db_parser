from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Message:
    """Normalized chat message."""

    server_id: int
    sequence: int
    timestamp: datetime
    talker: str
    talker_display: str
    is_chatroom: bool
    is_self: bool
    msg_type: int
    sub_type: int
    sender: str
    sender_display: str
    content: str
    raw_content: str
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContactDisplay:
    """Contact level metadata providing multiple naming options."""

    username: str
    alias: str = ""
    nickname: str = ""
    remark: str = ""

    def best_name(self) -> str:
        return (self.remark or self.alias or self.nickname or "").strip()

    def label(self) -> str:
        name = self.best_name()
        if not name or name == self.username:
            return self.username
        return f"{name}({self.username})"


@dataclass
class GroupMemberDisplay:
    """Human readable labels for group members (群昵称)."""

    chatroom: str
    member: str
    group_remark: str = ""
    nickname: str = ""
    alias: str = ""

    def best_name(self, contact: Optional[ContactDisplay]) -> str:
        for candidate in (self.group_remark, self.nickname, self.alias):
            candidate = candidate.strip()
            if candidate:
                return candidate
        if contact is not None:
            name = contact.best_name()
            if name:
                return name
        return ""
