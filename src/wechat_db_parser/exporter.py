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
from .datasource import MessageDataSource, PublicArticleDataSource
from .model import ContactDisplay, Message, OfficialAccountArticle, OfficialAccountTimelineArticle
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

PUBLIC_ARTICLE_HEADER = [
    "timestamp",
    "account_name",
    "account_id",
    "title",
    "url",
    "summary",
]

PUBLIC_ARTICLE_TIMELINE_HEADER = [
    "timestamp",
    "account_name",
    "account_id",
    "article_index",
    "title",
    "url",
    "summary",
    "cover_image_url",
    "cover_thumb_url",
    "source",
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
            talker=talker, start=start, end=end, limit=limit, workers=workers
        )
        if not messages:
            return None

        annotate_messages(messages, contacts, group_members)
        file_path = output_dir / _build_csv_name(talker, messages[0].talker_display)
        _write_csv(file_path, messages)
        return talker, file_path

    results: List[Tuple[str, Path]] = []

    progress = tqdm(all_talkers, desc="Exporting", unit="talker") if tqdm else None
    iterator: Iterable[str]
    if progress is not None:
        iterator = progress
    else:
        iterator = all_talkers

    if workers <= 1:
        for talker in iterator:
            try:
                result = process(talker)
                if result:
                    results.append(result)
            except Exception as exc:  # pragma: no cover - focus on robustness
                if progress is not None:
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

    if progress is not None:
        progress.close()

    return results


def export_public_articles(
    data_dir: Path,
    output_path: Path,
    accounts: Optional[Sequence[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> Tuple[int, Path]:
    data_dir = Path(data_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    datasource = PublicArticleDataSource(data_dir)
    articles = datasource.iter_articles(accounts=accounts, start=start, end=end, limit=limit)
    _write_public_articles_csv(output_path, articles)
    return len(articles), output_path


def export_public_article_timeline(
    data_dir: Path,
    output_path: Path,
    accounts: Optional[Sequence[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
    output_format: str = "csv",
) -> Tuple[int, Path]:
    data_dir = Path(data_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    datasource = PublicArticleDataSource(data_dir)
    articles = datasource.iter_article_timeline(accounts=accounts, start=start, end=end, limit=limit)
    if output_format == "csv":
        _write_public_article_timeline_csv(output_path, articles)
    elif output_format == "markdown":
        _write_public_article_timeline_markdown(output_path, articles)
    else:
        raise ValueError(f"unsupported output format: {output_format}")
    return len(articles), output_path


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


def _write_public_articles_csv(path: Path, articles: List[OfficialAccountArticle]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(PUBLIC_ARTICLE_HEADER)
        for article in articles:
            writer.writerow(
                [
                    article.timestamp.isoformat(sep=" ", timespec="seconds"),
                    article.account_name,
                    article.account_id,
                    article.title,
                    article.url,
                    article.summary,
                ]
            )


def _write_public_article_timeline_csv(path: Path, articles: List[OfficialAccountTimelineArticle]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(PUBLIC_ARTICLE_TIMELINE_HEADER)
        for article in articles:
            writer.writerow(
                [
                    article.timestamp.isoformat(sep=" ", timespec="seconds"),
                    article.account_name,
                    article.account_id,
                    article.article_index,
                    article.title,
                    article.url,
                    article.summary,
                    article.cover_image_url,
                    article.cover_thumb_url,
                    article.source,
                ]
            )


def _write_public_article_timeline_markdown(path: Path, articles: List[OfficialAccountTimelineArticle]) -> None:
    lines: List[str] = ["# Official account article timeline", ""]
    current_account = ""
    for article in articles:
        if article.account_name != current_account:
            if current_account:
                lines.append("")
            current_account = article.account_name
            lines.append(f"## {article.account_name}")
            lines.append("")
        lines.append(f"### {article.title}")
        lines.append("")
        lines.append(f"- Time: {article.timestamp.isoformat(sep=' ', timespec='seconds')}")
        lines.append(f"- Account: {article.account_name} ({article.account_id})")
        if article.url:
            lines.append(f"- URL: {article.url}")
        if article.cover_image_url:
            lines.append(f"- Cover: {article.cover_image_url}")
        if article.summary:
            lines.append("")
            lines.append(article.summary)
        if article.cover_image_url:
            lines.append("")
            lines.append(f"![{article.title}]({article.cover_image_url})")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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
