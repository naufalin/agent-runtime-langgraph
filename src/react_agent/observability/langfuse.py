import os
from typing import Optional, Sequence


def _langfuse_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


def get_callbacks() -> Optional[Sequence[object]]:
    # Only enable Langfuse when keys are present.
    if not _langfuse_enabled():
        return None

    from langfuse.langchain import CallbackHandler

    # Langfuse handler reads config from env; avoid passing args to keep
    # compatibility across handler versions.
    return [CallbackHandler()]


def session_metadata(session_id: str) -> Optional[dict]:
    if not _langfuse_enabled():
        return None

    return {"langfuse_session_id": session_id}
