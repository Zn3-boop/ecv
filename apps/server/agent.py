from __future__ import annotations

import os

from dotenv import load_dotenv
load_dotenv()

from app.services.graph.graph import build_agent_graph

if os.getenv("LANGGRAPH_DEV") == "1":
    graph = build_agent_graph(checkpointer=None)
else:
    graph = build_agent_graph()