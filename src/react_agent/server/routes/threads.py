import sqlite3
import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from react_agent.agent import get_graph
from react_agent.server.deps import DB_PATH, WEB_DIR
from react_agent.server.thread_metadata import (
    delete_thread_metadata,
    ensure_thread_metadata,
    save_manual_title,
)
from react_agent.utils.messages import message_to_dict

router = APIRouter()


class ThreadUpdateRequest(BaseModel):
    title: str


@router.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@router.post("/api/thread")
def create_thread() -> dict:
    thread_id = uuid.uuid4().hex
    metadata = ensure_thread_metadata(thread_id)
    return {
        "thread_id": thread_id,
        "title": metadata["title"],
        "title_source": metadata["title_source"],
    }


@router.patch("/api/thread/{thread_id}")
def update_thread(thread_id: str, request: ThreadUpdateRequest) -> dict:
    metadata = save_manual_title(thread_id, request.title)
    return {
        "thread_id": thread_id,
        "title": metadata["title"],
        "title_source": metadata["title_source"],
    }


@router.delete("/api/thread/{thread_id}")
def delete_thread(thread_id: str) -> dict:
    deleted = 0
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
                (thread_id,),
            )
            row = cur.fetchone()
            deleted = int(row[0]) if row else 0
            conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.commit()
    except sqlite3.OperationalError:
        deleted = 0
    delete_thread_metadata(thread_id)
    return {"status": "ok", "deleted": deleted}


@router.get("/api/thread/{thread_id}/history")
def get_thread_history(thread_id: str) -> dict:
    metadata = ensure_thread_metadata(thread_id)
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        messages = snapshot.values.get("messages", []) if snapshot else []
    except Exception:
        messages = []
    return {
        "thread_id": thread_id,
        "title": metadata["title"],
        "title_source": metadata["title_source"],
        "messages": [message_to_dict(m) for m in messages],
    }
