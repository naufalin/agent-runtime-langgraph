from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from react_agent.server.deps import WEB_DIR
from react_agent.server.routes.chat import router as chat_router
from react_agent.server.routes.health import router as health_router
from react_agent.server.routes.threads import router as threads_router

app = FastAPI(title="ReAct Agent Runtime")

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

app.include_router(health_router)
app.include_router(threads_router)
app.include_router(chat_router)
