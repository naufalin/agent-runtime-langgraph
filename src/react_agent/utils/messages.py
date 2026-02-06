import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def message_to_payloads(message: object) -> list[dict]:
    payloads: list[dict] = []
    if isinstance(message, ToolMessage):
        payloads.append(
            {
                "type": "tool_result",
                "tool_name": message.name,
                "content": message.content or "",
            }
        )
        return payloads

    if isinstance(message, (AIMessage, AIMessageChunk)):
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            payloads.append(
                {
                    "type": "tool_call",
                    "tool_name": tool_call.get("name", "tool"),
                    "args": tool_call.get("args", {}),
                }
            )
        content = content_to_text(getattr(message, "content", None))
        if content:
            payloads.append(
                {
                    "type": "delta",
                    "role": "assistant",
                    "content": content,
                }
            )
        return payloads

    return payloads


def message_to_dict(message: object) -> dict:
    role = "assistant"
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, ToolMessage):
        role = "tool"
    elif isinstance(message, SystemMessage):
        role = "system"
    content = content_to_text(getattr(message, "content", None))
    return {"role": role, "content": content}


def content_to_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(text)
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
                continue
            parts.append(str(item))
        return "".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        if text is not None:
            return text
        return json.dumps(content, ensure_ascii=False)
    return str(content)
