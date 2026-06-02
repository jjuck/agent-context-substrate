from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "src" / "agent_context_substrate" / "assets" / "user_plugin" / "agent_context_substrate"


def _load_runtime_module():
    if str(PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGIN_DIR))
    sys.modules.pop("config", None)
    module_name = "acs_user_plugin_runtime_agent_llm_test"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_DIR / "runtime.py")
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


def test_session_finalize_passes_host_agent_llm_router_when_summary_mode_requires_it(tmp_path, monkeypatch) -> None:
    runtime = _load_runtime_module()
    host = object()
    captured: dict[str, object] = {}

    config = SimpleNamespace(
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        auto_finalize_enabled=True,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[],
        promotion_mode="packet-only",
        summary_mode="agent-llm",
        summary_model="host-default",
        summary_budget="cheap",
        summary_cache=False,
        llm_redact=True,
        llm_max_input_chars=4096,
        llm_allow_code_snippets=False,
        llm_path_policy="allow",
    )

    def fake_should_process_session(*args, **kwargs):
        return True

    def fake_run_session_finalize_pipeline(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(packet_id="session-1", skipped=False, recovery_json_path=tmp_path / "recovery.json")

    def fake_build_agent_llm_router(value, **kwargs):
        captured["router_host"] = value
        captured["router_kwargs"] = kwargs
        return "ROUTER"

    monkeypatch.setattr(runtime, "load_plugin_config", lambda: config)
    monkeypatch.setattr(runtime, "_load_harness_api", lambda: (fake_should_process_session, fake_run_session_finalize_pipeline))
    monkeypatch.setattr(runtime, "_load_agent_llm_router_builder", lambda: fake_build_agent_llm_router)

    result = runtime.handle_session_finalize(session_id="session-1", platform="telegram", host=host)

    assert result["status"] == "processed"
    assert captured["router_host"] is host
    assert captured["router_kwargs"] == {"path_policy": "allow"}
    assert captured["summary_mode"] == "agent-llm"
    assert captured["agent_llm_router"] == "ROUTER"
    assert captured["summary_model"] == "host-default"
    assert captured["summary_budget"] == "cheap"
    assert captured["summary_cache"] is False
    assert captured["llm_safety"].redact is True
    assert captured["llm_safety"].max_input_chars == 4096
    assert captured["llm_safety"].allow_code_snippets is False
    assert captured["llm_safety"].path_policy == "allow"


def test_session_finalize_uses_hermes_auxiliary_router_when_hook_has_no_host(tmp_path, monkeypatch) -> None:
    runtime = _load_runtime_module()
    captured: dict[str, object] = {}

    config = SimpleNamespace(
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        auto_finalize_enabled=True,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[],
        promotion_mode="packet-only",
        summary_mode="hybrid",
        summary_model=None,
        summary_budget="balanced",
        summary_cache=False,
        llm_redact=True,
        llm_max_input_chars=4096,
        llm_allow_code_snippets=False,
        llm_path_policy="redact",
    )

    def fake_run_session_finalize_pipeline(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(packet_id="session-1", skipped=False, recovery_json_path=tmp_path / "recovery.json")

    def fake_build_auxiliary_router(**kwargs):
        captured["aux_router_kwargs"] = kwargs
        return "AUX_ROUTER"

    monkeypatch.setattr(runtime, "load_plugin_config", lambda: config)
    monkeypatch.setattr(runtime, "_load_harness_api", lambda: (lambda *args, **kwargs: True, fake_run_session_finalize_pipeline))
    monkeypatch.setattr(runtime, "_load_hermes_auxiliary_llm_router_builder", lambda: fake_build_auxiliary_router)

    result = runtime.handle_session_finalize(session_id="session-1", platform="telegram")

    assert result["status"] == "processed"
    assert captured["aux_router_kwargs"] == {"path_policy": "redact"}
    assert captured["summary_mode"] == "hybrid"
    assert captured["agent_llm_router"] == "AUX_ROUTER"
    assert captured["summary_budget"] == "balanced"


def test_session_finalize_uses_auxiliary_router_for_opt_in_summary_judge(tmp_path, monkeypatch) -> None:
    runtime = _load_runtime_module()
    captured: dict[str, object] = {}

    config = SimpleNamespace(
        project_root=tmp_path / "project",
        wiki_root=tmp_path / "wiki",
        auto_finalize_enabled=True,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[],
        promotion_mode="packet-only",
        summary_mode="heuristic",
        summary_judge_mode="hybrid",
        summary_model=None,
        summary_budget="quality",
        summary_cache=False,
        llm_redact=True,
        llm_max_input_chars=4096,
        llm_allow_code_snippets=False,
        llm_path_policy="redact",
    )

    def fake_run_session_finalize_pipeline(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(packet_id="session-1", skipped=False, recovery_json_path=tmp_path / "recovery.json")

    def fake_build_auxiliary_router(**kwargs):
        captured["aux_router_kwargs"] = kwargs
        return "AUX_ROUTER"

    monkeypatch.setattr(runtime, "load_plugin_config", lambda: config)
    monkeypatch.setattr(runtime, "_load_harness_api", lambda: (lambda *args, **kwargs: True, fake_run_session_finalize_pipeline))
    monkeypatch.setattr(runtime, "_load_hermes_auxiliary_llm_router_builder", lambda: fake_build_auxiliary_router)

    result = runtime.handle_session_finalize(session_id="session-1", platform="telegram")

    assert result["status"] == "processed"
    assert captured["aux_router_kwargs"] == {"path_policy": "redact"}
    assert captured["summary_mode"] == "heuristic"
    assert captured["summary_judge_mode"] == "hybrid"
    assert captured["agent_llm_router"] == "AUX_ROUTER"
