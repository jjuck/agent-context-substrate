from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
ASSET_PACKAGE = ROOT / "src" / "agent_context_substrate" / "assets" / "context_engine" / "agent_context_substrate"


def _load_retrieval_tools_module():
    package_name = "acs_context_engine_asset_for_retrieval_tool_tests"
    if package_name not in sys.modules:
        package_module = types.ModuleType(package_name)
        package_module.__path__ = [str(ASSET_PACKAGE)]
        sys.modules[package_name] = package_module

    module_name = f"{package_name}.retrieval_tools"
    spec = importlib.util.spec_from_file_location(module_name, ASSET_PACKAGE / "retrieval_tools.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    return module


def test_knowledge_search_tool_schema_exposes_recovery_mode() -> None:
    retrieval_tools = _load_retrieval_tools_module()

    schema = next(item for item in retrieval_tools.retrieval_tool_schemas() if item["name"] == "wiki_knowledge_search")
    mode_schema = schema["parameters"]["properties"]["mode"]

    assert mode_schema["enum"] == ["knowledge", "graph", "recovery"]
    assert "recovery" in mode_schema["description"]
