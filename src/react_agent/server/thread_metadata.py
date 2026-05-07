import logging
import sqlite3
from datetime import datetime, timezone
from typing import Literal, TypedDict

from react_agent.server.deps import DB_PATH

logger = logging.getLogger(__name__)

TitleSource = Literal["auto", "manual"]


class ThreadMetadata(TypedDict):
    thread_id: str
    title: str
    title_source: TitleSource
    title_updated_at: str
    title_turn_count: int


DEFAULT_TITLE = "New Session"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_thread_metadata() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_metadata (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                title_source TEXT NOT NULL DEFAULT 'auto',
                title_updated_at TEXT NOT NULL,
                title_turn_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def ensure_thread_metadata(thread_id: str) -> ThreadMetadata:
    init_thread_metadata()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT thread_id, title, title_source, title_updated_at, title_turn_count
            FROM thread_metadata
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
        if row:
            return _row_to_metadata(row)

        timestamp = _now()
        conn.execute(
            """
            INSERT INTO thread_metadata (
                thread_id,
                title,
                title_source,
                title_updated_at,
                title_turn_count
            )
            VALUES (?, ?, 'auto', ?, 0)
            """,
            (thread_id, DEFAULT_TITLE, timestamp),
        )
        conn.commit()
        return {
            "thread_id": thread_id,
            "title": DEFAULT_TITLE,
            "title_source": "auto",
            "title_updated_at": timestamp,
            "title_turn_count": 0,
        }


def save_auto_title(
    thread_id: str,
    title: str,
    title_turn_count: int,
) -> ThreadMetadata | None:
    metadata = ensure_thread_metadata(thread_id)
    if metadata["title_source"] == "manual":
        return None

    cleaned = clean_title(title)
    if not cleaned:
        return metadata

    timestamp = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE thread_metadata
            SET title = ?,
                title_source = 'auto',
                title_updated_at = ?,
                title_turn_count = ?
            WHERE thread_id = ? AND title_source != 'manual'
            """,
            (cleaned, timestamp, title_turn_count, thread_id),
        )
        conn.commit()

    return ensure_thread_metadata(thread_id)


def save_manual_title(thread_id: str, title: str) -> ThreadMetadata:
    cleaned = clean_title(title) or DEFAULT_TITLE
    timestamp = _now()
    ensure_thread_metadata(thread_id)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE thread_metadata
            SET title = ?,
                title_source = 'manual',
                title_updated_at = ?
            WHERE thread_id = ?
            """,
            (cleaned, timestamp, thread_id),
        )
        conn.commit()
    return ensure_thread_metadata(thread_id)


def delete_thread_metadata(thread_id: str) -> None:
    init_thread_metadata()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM thread_metadata WHERE thread_id = ?", (thread_id,))
            conn.commit()
    except sqlite3.OperationalError:
        logger.exception("Failed to delete thread metadata for %s", thread_id)


def clean_title(title: str) -> str:
    cleaned = " ".join((title or "").strip().strip("\"'`").split())
    return cleaned[:80]


def _row_to_metadata(row: tuple) -> ThreadMetadata:
    source = row[2] if row[2] in {"auto", "manual"} else "auto"
    return {
        "thread_id": row[0],
        "title": row[1],
        "title_source": source,
        "title_updated_at": row[3],
        "title_turn_count": int(row[4] or 0),
    }
