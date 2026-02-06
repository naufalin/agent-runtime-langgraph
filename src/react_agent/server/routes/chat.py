import uuid
from typing import Iterator, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from react_agent.agent import get_graph
from react_agent.observability import get_callbacks, session_metadata
from react_agent.utils.messages import content_to_text, message_to_payloads
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
    inputs = {"messages": [HumanMessage(content=request.message)]}
    config = {"configurable": {"thread_id": thread_id}}

    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        metadata = session_metadata(thread_id)
        if metadata:
            config["metadata"] = metadata

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
    inputs = {"messages": [HumanMessage(content=request.message)]}
    config = {"configurable": {"thread_id": thread_id}}

    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        metadata = session_metadata(thread_id)
        if metadata:
            config["metadata"] = metadata

    def event_stream() -> Iterator[str]:
        yield sse_event({"type": "thread", "thread_id": thread_id})
        for event in graph.stream(inputs, stream_mode="messages", config=config):
            message, _metadata = normalize_stream_event(event)
            if message is None:
                continue
            for payload in message_to_payloads(message):
                yield sse_event(payload)
        yield sse_event({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
