# LangGraph ReAct Agent Runtime (Python)

This is a minimal LangGraph ReAct agent runtime using the LangGraph ReAct agent template style, packaged with `uv`.

## Requirements

- Python 3.11+
- `uv`
- A Google GenAI API key
- A Tavily API key

## Setup

1. Create your env file:

```bash
cp .env.example .env
```

2. Add your `GOOGLE_API_KEY` (and optionally `GOOGLE_MODEL`) and `TAVILY_API_KEY` to `.env`.

3. Install dependencies:

```bash
uv sync
```

## Run the REST server + frontend

```bash
uv run react-agent-server
```

Then open `http://localhost:8000` in your browser.

The frontend uses `POST /api/chat/stream` (SSE-style) for streaming responses and tool activity.

## Run the LangGraph dev server

```bash
uv run langgraph dev
```

By default this uses `langgraph.json` in the project root.

## Run the CLI helper

```bash
uv run react-agent "What's the weather in San Francisco?"
```

To keep a persistent conversation thread:

```bash
uv run react-agent --thread demo "Search the web for today's weather in SF."
```

## Observability (Langfuse + LangSmith)

Langfuse is optional and can run alongside LangSmith. Set the Langfuse env vars in `.env`:

```
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=http://your-langfuse-host:3000
LANGFUSE_FLUSH_INTERVAL=1
LANGFUSE_FLUSH_AT=1
```

Sessions are keyed by `thread_id` (the conversation thread).

## Customize

- Add or modify tools in `src/react_agent/tools.py`.
- Update the system prompt in `src/react_agent/prompts.py`.
- Adjust the ReAct loop in `src/react_agent/graph.py`.
- Add more graphs/agents via `src/react_agent/agent/registry.py`.
- HTTP routes live in `src/react_agent/server/routes/`.
- Shared helpers live in `src/react_agent/utils/`.

## Persistence

The SQLite checkpoint database is `langgraph.db` in the project root.
