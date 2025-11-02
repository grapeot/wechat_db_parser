from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None  # type: ignore

from .contacts import load_contact_book, load_group_directory
from .datasource import MessageDataSource
from .model import ContactDisplay, Message
from .parser import annotate_messages


EXPORT_HEADER = [
    "timestamp",
    "talker_display",
    "talker_id",
    "sender_display",
    "sender_id",
    "message_type",
    "message_subtype",
    "content",
    "raw_content",
    "extras",
]


def export_conversations(
    data_dir: Path,
    output_dir: Path,
    talkers: Optional[Sequence[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
    workers: int = 1,
) -> List[Tuple[str, Path]]:
    """
    Export conversations to CSV files.

    Returns a list of (talker, path) tuples for successfully exported conversations.
    """

    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    datasource = MessageDataSource(data_dir)
    available_talkers = datasource.list_talkers()
    contact_db = _find_contact_db(data_dir)
    contacts = load_contact_book(contact_db)
    group_members = load_group_directory(contact_db)

    if talkers:
        resolved = _resolve_talker_inputs(talkers, contacts, available_talkers)
        if not resolved:
            return []
        all_talkers = resolved
    else:
        all_talkers = available_talkers

    if not all_talkers:
        return []

    def process(talker: str) -> Optional[Tuple[str, Path]]:
        messages = datasource.iter_messages(
            talker=talker, start=start, end=end, limit=limit
        )
        if not messages:
            return None

        annotate_messages(messages, contacts, group_members)
        file_path = output_dir / _build_csv_name(talker, messages[0].talker_display)
        _write_csv(file_path, messages)
        return talker, file_path

    results: List[Tuple[str, Path]] = []

    iterator: Iterable[str] = all_talkers
    progress = tqdm(iterator, desc="Exporting", unit="talker") if tqdm else iterator

    if workers <= 1:
        for talker in progress:
            try:
                result = process(talker)
                if result:
                    results.append(result)
            except Exception as exc:  # pragma: no cover - focus on robustness
                if tqdm:
                    progress.write(f"[WARN] Failed to export {talker}: {exc}")
                else:
                    print(f"[WARN] Failed to export {talker}: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(process, talker): talker for talker in all_talkers
            }
            if tqdm:
                for future in tqdm(as_completed(future_map), total=len(future_map), desc="Exporting", unit="talker"):
                    talker = future_map[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as exc:
                        tqdm.write(f"[WARN] Failed to export {talker}: {exc}")
            else:
                for future in as_completed(future_map):
                    talker = future_map[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as exc:
                        print(f"[WARN] Failed to export {talker}: {exc}")

    if tqdm:
        progress.close()

    return results


def _write_csv(path: Path, messages: List[Message]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(EXPORT_HEADER)
        for msg in messages:
            writer.writerow(
                [
                    msg.timestamp.isoformat(sep=" ", timespec="seconds"),
                    msg.talker_display,
                    msg.talker,
                    msg.sender_display,
                    msg.sender,
                    msg.msg_type,
                    msg.sub_type,
                    msg.content,
                    msg.raw_content,
                    json.dumps(msg.extras, ensure_ascii=False) if msg.extras else "",
                ]
            )


def _build_csv_name(talker: str, talker_display: str) -> str:
    label = talker_display.strip() if talker_display else ""
    base = label or talker
    safe_base = _sanitize_filename(base)
    suffix = sha1(talker.encode("utf-8")).hexdigest()[:6]
    return f"{safe_base}__{suffix}.csv"


def _sanitize_filename(name: str) -> str:
    sanitized = "".join(
        ch if ch.isalnum() or ch in (" ", "-", "_", "(", ")", "（", "）") else "_"
        for ch in name
    ).strip()
    return sanitized or "conversation"


def _find_contact_db(data_dir: Path) -> Path:
    candidates = [
        data_dir / "FTSContact.db",
        data_dir / "Msg" / "FTSContact.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # fall back to first candidate (even if missing) so downstream behaves gracefully
    return candidates[0]


def _resolve_talker_inputs(
    inputs: Sequence[str],
    contacts: Dict[str, ContactDisplay],
    available_ids: Sequence[str],
) -> List[str]:
    available_set = set(available_ids)
    mapping: dict[str, str] = {}
    for contact in contacts.values():
        names = {
            contact.best_name(),
            contact.alias,
            contact.nickname,
            contact.remark,
            contact.label(),
        }
        for name in names:
            if name:
                mapping[name.lower()] = contact.username

    resolved: List[str] = []
    for item in inputs:
        candidate = item.strip()
        if candidate in available_set:
            resolved.append(candidate)
            continue
        lower = candidate.lower()
        if lower in mapping and mapping[lower] in available_set:
            resolved.append(mapping[lower])
            continue
        label_lower = candidate.split("(")[0].strip().lower()
        if label_lower in mapping and mapping[label_lower] in available_set:
            resolved.append(mapping[label_lower])
            continue
        raise ValueError(f"无法解析会话标识：{item}")
    return resolved
