import os

from .app import app

__all__ = ["app", "main"]


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("react_agent.server:app", host="0.0.0.0", port=port, reload=True)
