from __future__ import annotations

from datetime import datetime, timedelta

from scripts import performance_improvement_plan as pip
from wechat_db_parser.model import ContactDisplay, Message

TALKER = "room@chatroom"
NOW = datetime(2026, 1, 1, 12, 0, 0)


def mk_msg(sender: str, ts: datetime, msg_type: int = 1, content: str = "hi") -> Message:
    return Message(
        server_id=0,
        sequence=0,
        timestamp=ts,
        talker=TALKER,
        talker_display="",
        is_chatroom=True,
        is_self=False,
        msg_type=msg_type,
        sub_type=0,
        sender=sender,
        sender_display="",
        content=content,
        raw_content=content,
    )


class FakeDataSource:
    def __init__(self, messages):
        self._messages = messages

    def iter_messages(self, talker, start=None, end=None):
        out = [m for m in self._messages if m.talker == talker]
        if end is not None:
            out = [m for m in out if m.timestamp <= end]
        if start is not None:
            out = [m for m in out if m.timestamp >= start]
        return out


def test_extract_join_invitees():
    assert pip.extract_join_invitees('"邀请人"邀请"小明"加入了群聊') == ["小明"]
    assert pip.extract_join_invitees('你邀请"小红"加入了群聊') == ["小红"]
    assert pip.extract_join_invitees('"甲"、"乙"加入了群聊') == ["甲", "乙"]
    assert pip.extract_join_invitees('"小刚"通过扫描"群主"分享的二维码加入群聊') == ["小刚"]
    assert pip.extract_join_invitees('"某人" 撤回了一条消息') == []


def test_type10000_not_counted_as_speech(monkeypatch):
    old = NOW - timedelta(days=400)
    messages = [
        mk_msg("member_old", old, msg_type=1),
        mk_msg("member_old", NOW - timedelta(days=1), msg_type=10000),  # pat, ignored
    ]
    last = pip.compute_last_spoken(messages)
    assert last["member_old"] == old


def test_find_silent_members_duration_and_basis(monkeypatch):
    members = {"member_old", "member_join", "member_unknown", "member_active",
               "amb_a", "amb_b"}
    monkeypatch.setattr(pip, "load_members", lambda chatroom_db, talker: set(members))

    contacts = {
        "member_join": ContactDisplay(username="member_join", nickname="joiner"),
        "amb_a": ContactDisplay(username="amb_a", nickname="dup"),
        "amb_b": ContactDisplay(username="amb_b", nickname="dup"),
    }

    messages = [
        mk_msg("member_old", NOW - timedelta(days=400), msg_type=1),
        mk_msg("member_old", NOW - timedelta(days=1), msg_type=10000),
        mk_msg("member_active", NOW - timedelta(days=365), msg_type=1),  # exactly at cutoff
        mk_msg("system", NOW - timedelta(days=40), msg_type=10000,
               content='"x"邀请"joiner"加入了群聊'),
        mk_msg("system", NOW - timedelta(days=10), msg_type=10000,
               content='"x"邀请"dup"加入了群聊'),
    ]
    ds = FakeDataSource(messages)

    members_out, active, silent, detail = pip.find_silent_members(
        data_dir=None,
        talker=TALKER,
        datasource=ds,
        group_members={},
        contacts=contacts,
        chatroom_db="dummy",
        start=NOW - timedelta(days=365),
        end=NOW,
    )

    assert members_out == members
    assert active == {"member_active"}
    assert silent == {"member_old", "member_join", "member_unknown", "amb_a", "amb_b"}

    # last real speech stays 400 days ago, not the 1-day-ago pat
    assert detail["member_old"][2] == pip.BASIS_LAST_SPOKEN
    assert detail["member_old"][1] == 400

    # unique nickname join attribution
    assert detail["member_join"][2] == pip.BASIS_JOIN_INFERRED
    assert detail["member_join"][1] == 40

    # ambiguous shared nickname is NOT attributed to either member
    assert detail["amb_a"][2] == pip.BASIS_NO_JOIN
    assert detail["amb_b"][2] == pip.BASIS_NO_JOIN
    assert detail["member_unknown"][2] == pip.BASIS_NO_JOIN
    assert detail["member_unknown"][0].startswith("≥")


def test_end_bound_excludes_future_messages(monkeypatch):
    monkeypatch.setattr(pip, "load_members", lambda chatroom_db, talker: {"only_future"})
    messages = [mk_msg("only_future", NOW + timedelta(days=10), msg_type=1)]
    ds = FakeDataSource(messages)

    _members, active, silent, detail = pip.find_silent_members(
        data_dir=None,
        talker=TALKER,
        datasource=ds,
        group_members={},
        contacts={},
        chatroom_db="dummy",
        start=NOW - timedelta(days=365),
        end=NOW,
    )
    assert active == set()
    assert silent == {"only_future"}
