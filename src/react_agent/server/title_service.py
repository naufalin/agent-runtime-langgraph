import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from react_agent.server.thread_metadata import clean_title
from react_agent.utils.messages import content_to_text

logger = logging.getLogger(__name__)

DEFAULT_TITLE_MODEL = "gemini-3.1-flash-lite-preview"
MAX_TITLE_TURNS = 3

TITLE_SYSTEM_PROMPT = """Create a concise title for a chat session.
Return only the title.
Use 4 to 6 words when possible.
Do not use quotation marks, trailing punctuation, emojis, or generic words like Chat."""


def generate_title(messages: list[dict[str, str]]) -> str | None:
    if not messages:
        return None

    model_name = os.getenv("TITLE_MODEL", DEFAULT_TITLE_MODEL)
    transcript = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in messages
        if message.get("content")
    )
    if not transcript:
        return None

    try:
        model = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        response = model.invoke(
            [
                SystemMessage(content=TITLE_SYSTEM_PROMPT),
                HumanMessage(content=transcript),
            ]
        )
    except Exception:
        logger.exception("Failed to generate thread title with model %s", model_name)
        return None

    title = clean_title(content_to_text(getattr(response, "content", None)))
    return title or None


def recent_title_messages(
    messages: list[dict[str, str]],
    limit: int = 6,
) -> list[dict[str, str]]:
    relevant = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message.get("role") in {"user", "assistant"} and message.get("content")
    ]
    return relevant[-limit:]
