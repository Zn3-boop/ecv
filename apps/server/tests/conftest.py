import os

os.environ.setdefault("GRAPH_ENV", "dev")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("TOOL_DEF_CONFIG_PATH", "config/tools.yaml")

import pytest_asyncio
pytest_plugins = ["pytest_asyncio"]