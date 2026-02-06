from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated, Sequence, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from react_agent.prompts import SYSTEM_PROMPT
from react_agent.tools import TOOLS

load_dotenv()


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def _build_model() -> ChatGoogleGenerativeAI:
    model_name = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    return ChatGoogleGenerativeAI(model=model_name)


tools = TOOLS
model = _build_model().bind_tools(tools)
tools_by_name = {tool.name: tool for tool in tools}


def tool_node(state: AgentState) -> dict:
    outputs = []
    for tool_call in state["messages"][-1].tool_calls:
        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        outputs.append(
            ToolMessage(
                content=json.dumps(tool_result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )
    return {"messages": outputs}


def call_model(state: AgentState, config: RunnableConfig) -> dict:
    now = datetime.now().astimezone()
    datetime_context = (
        f"Current datetime: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}."
    )
    system_prompt = SystemMessage(f"{SYSTEM_PROMPT}\n\n{datetime_context}")
    response = model.invoke([system_prompt] + list(state["messages"]), config)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if not getattr(last_message, "tool_calls", None):
        return "end"
    return "continue"


workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"continue": "tools", "end": END},
)
workflow.add_edge("tools", "agent")

DB_PATH = Path(__file__).resolve().parents[2] / "langgraph.db"
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_checkpointer = SqliteSaver(_conn)

graph = workflow.compile(checkpointer=_checkpointer)
