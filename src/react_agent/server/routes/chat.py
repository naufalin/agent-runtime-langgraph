import uuid
from typing import Iterator, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from react_agent.agent import get_graph
from react_agent.observability import get_callbacks, session_metadata
from react_agent.server.thread_metadata import ensure_thread_metadata, save_auto_title
from react_agent.server.title_service import (
    MAX_TITLE_TURNS,
    generate_title,
    recent_title_messages,
)
from react_agent.utils.messages import (
    content_to_text,
    message_to_dict,
    message_to_payloads,
)
from react_agent.utils.sse import normalize_stream_event, sse_event

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    thread_id: str
    response: str


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    graph = get_graph()
    thread_id = request.thread_id or uuid.uuid4().hex
    ensure_thread_metadata(thread_id)
    inputs = {"messages": [HumanMessage(content=request.message)]}
    config = {"configurable": {"thread_id": thread_id}}

    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        callback_metadata = session_metadata(thread_id)
        if callback_metadata:
            config["metadata"] = callback_metadata

    final_message = None
    for event in graph.stream(inputs, stream_mode="values", config=config):
        final_message = event["messages"][-1]

    response_text = ""
    if final_message is not None:
        response_text = content_to_text(getattr(final_message, "content", None))

    return ChatResponse(thread_id=thread_id, response=response_text)


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    graph = get_graph()
    thread_id = request.thread_id or uuid.uuid4().hex
    title_metadata = ensure_thread_metadata(thread_id)
    inputs = {"messages": [HumanMessage(content=request.message)]}
    config = {"configurable": {"thread_id": thread_id}}
    before_messages = _thread_messages(graph, config)
    before_title_messages = [message_to_dict(m) for m in before_messages]
    previous_user_turns = sum(1 for m in before_title_messages if m["role"] == "user")
    current_user_turns = previous_user_turns + 1

    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        callback_metadata = session_metadata(thread_id)
        if callback_metadata:
            config["metadata"] = callback_metadata

    def event_stream() -> Iterator[str]:
        yield sse_event({"type": "thread", "thread_id": thread_id})
        if title_metadata["title_source"] == "auto" and previous_user_turns == 0:
            title = generate_title([{"role": "user", "content": request.message}])
            if title:
                updated = save_auto_title(thread_id, title, current_user_turns)
                if updated:
                    yield sse_event(
                        {
                            "type": "title",
                            "title": updated["title"],
                            "title_source": updated["title_source"],
                        }
                    )

        assistant_text = ""
        for event in graph.stream(inputs, stream_mode="messages", config=config):
            message, _metadata = normalize_stream_event(event)
            if message is None:
                continue
            for payload in message_to_payloads(message):
                if payload.get("type") == "delta":
                    assistant_text += payload.get("content", "")
                yield sse_event(payload)
        latest_metadata = ensure_thread_metadata(thread_id)
        if (
            latest_metadata["title_source"] == "auto"
            and current_user_turns <= MAX_TITLE_TURNS
        ):
            title_messages = before_title_messages + [
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": assistant_text},
            ]
            title = generate_title(recent_title_messages(title_messages))
            if title:
                updated = save_auto_title(thread_id, title, current_user_turns)
                if updated and updated["title"] != latest_metadata["title"]:
                    yield sse_event(
                        {
                            "type": "title",
                            "title": updated["title"],
                            "title_source": updated["title_source"],
                        }
                    )
        yield sse_event({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _thread_messages(graph, config: dict) -> list:
    try:
        snapshot = graph.get_state(config)
        return list(snapshot.values.get("messages", []) if snapshot else [])
    except Exception:
        return []
