import sqlite3
import uuid
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse

from react_agent.agent import get_graph
from react_agent.server.deps import DB_PATH, WEB_DIR
from react_agent.utils.messages import message_to_dict

router = APIRouter()


@router.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@router.post("/api/thread")
def create_thread() -> dict:
    return {"thread_id": uuid.uuid4().hex}


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
    return {"status": "ok", "deleted": deleted}


@router.get("/api/thread/{thread_id}/history")
def get_thread_history(thread_id: str) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        messages = snapshot.values.get("messages", []) if snapshot else []
    except Exception:
        messages = []
    return {"thread_id": thread_id, "messages": [message_to_dict(m) for m in messages]}
