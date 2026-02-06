from __future__ import annotations

from typing import Dict, Iterable

from react_agent.graph import graph as default_graph


_GRAPHS: Dict[str, object] = {
    "default": default_graph,
}


def get_graph(name: str = "default"):
    if name not in _GRAPHS:
        raise KeyError(f"Unknown graph: {name}")
    return _GRAPHS[name]


def list_graphs() -> Iterable[str]:
    return _GRAPHS.keys()
