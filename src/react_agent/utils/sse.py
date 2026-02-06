import json
from typing import Tuple


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def normalize_stream_event(event) -> Tuple[object, dict]:
    if isinstance(event, tuple) and len(event) == 2:
        return event[0], event[1]
    return event, {}
