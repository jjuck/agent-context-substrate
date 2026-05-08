from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.evidence import build_micro_evidence_bundle  # noqa: E402
from agent_context_substrate.summarizer_backends import (  # noqa: E402
    AgentLLMSummarizerBackend,
    HeuristicSummarizerBackend,
    get_summarizer_backend,
)


def _raw_bundle() -> dict:
    return {
        "session": {"id": "session-agent-llm", "source": "telegram", "title": "Agent LLM"},
        "messages": [
            {"id": 1, "role": "user", "content": "Summarize agent LLM routing design for README.md"},
            {"id": 2, "role": "assistant", "content": "Use the host Agent LLM router and strict JSON."},
        ],
    }


def _micro_payload(evidence: dict[str, object]) -> dict:
    return {
        "micro_id": evidence["micro_id"],
        "session_id": evidence["session_id"],
        "message_ids": evidence["message_ids"],
        "recovery_summary": "agent recovery",
        "knowledge_summary": "agent knowledge",
        "retrieval_summary": "agent retrieval README.md",
        "user_intent": "agent intent",
        "assistant_outcome": "agent outcome",
        "decisions": [{"text": "Use Agent router", "evidence_message_ids": evidence["message_ids"], "confidence": 0.9}],
        "claims": [],
        "action_items": [],
        "open_questions": [],
        "files": ["README.md"],
        "entities": ["AgentLLMSummarizerBackend"],
        "concepts": ["agent-llm"],
        "metadata": {
            "mode": "agent-llm",
            "schema_version": "micro_summary_v2",
            "prompt_version": "agent_llm_v1",
            "model": None,
            "input_hash": "sha256:agent",
            "created_at": "2026-05-07T00:00:00+00:00",
            "confidence": 0.9,
        },
        "provenance": None,
    }


def _unit_payload(micro: dict[str, object]) -> dict:
    return {
        "unit_id": "unit-agent-llm",
        "session_id": micro["session_id"],
        "title": "Agent LLM summarizer",
        "goal": "Reuse the host Agent LLM router.",
        "state": "in_progress",
        "decisions": micro["decisions"],
        "progress": ["agent outcome"],
        "next_actions": ["Add hybrid mode"],
        "open_questions": [],
        "risk_notes": [],
        "wiki_candidates": [],
        "micro_ids": [micro["micro_id"]],
        "related_pages": ["agent-context-substrate"],
        "metadata": {
            "mode": "agent-llm",
            "schema_version": "unit_summary_v2",
            "prompt_version": "agent_llm_v1",
            "model": None,
            "input_hash": "sha256:agent-unit",
            "created_at": "2026-05-07T00:00:00+00:00",
            "confidence": 0.9,
        },
        "provenance": None,
    }


class RecordingRouter:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> dict[str, object] | str:
        self.requests.append(request)
        if request["kind"] == "micro":
            return _micro_payload(request["evidence"])
        return json.dumps(_unit_payload(request["micro_summaries"][0]), ensure_ascii=False)


def test_agent_llm_summarizer_backend_uses_router_for_micro_and_unit_summaries() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-agent-llm")
    router = RecordingRouter()
    backend = AgentLLMSummarizerBackend(router=router, routing_hints={"budget": "cheap"})

    micro = backend.summarize_micro(evidence, schema_version="micro_summary_v2")
    unit = backend.summarize_unit(
        unit_id="unit-agent-llm",
        session_id="session-agent-llm",
        title="Agent LLM summarizer",
        goal="Reuse the host Agent LLM router.",
        micro_summaries=[micro],
        schema_version="unit_summary_v2",
        related_pages=["agent-context-substrate"],
    )

    assert backend.name == "agent-llm"
    assert micro.metadata.mode == "agent-llm"
    assert micro.decisions[0].text == "Use Agent router"
    assert unit.metadata.mode == "agent-llm"
    assert unit.next_actions == ["Add hybrid mode"]
    assert router.requests[0]["kind"] == "micro"
    assert router.requests[0]["schema_version"] == "micro_summary_v2"
    assert router.requests[0]["routing_hints"] == {"budget": "cheap"}
    assert router.requests[1]["kind"] == "unit"


def test_agent_llm_summarizer_backend_falls_back_when_unit_summary_fails_lint() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-agent-unit-lint")

    class BadUnitRouter(RecordingRouter):
        def __call__(self, request: dict[str, object]) -> dict[str, object] | str:
            if request["kind"] == "micro":
                return _micro_payload(request["evidence"])
            payload = _unit_payload(request["micro_summaries"][0])
            payload["micro_ids"] = ["invented-micro"]
            return payload

    backend = AgentLLMSummarizerBackend(router=BadUnitRouter(), fallback_backend=HeuristicSummarizerBackend())

    micro = backend.summarize_micro(evidence, schema_version="micro_summary_v2")
    unit = backend.summarize_unit(
        unit_id="unit-agent-unit-lint",
        session_id="session-agent-llm",
        title="Agent LLM summarizer",
        goal="Reuse the host Agent LLM router.",
        micro_summaries=[micro],
        schema_version="unit_summary_v2",
        related_pages=["agent-context-substrate"],
    )

    assert micro.metadata.mode == "agent-llm"
    assert unit.metadata.mode == "heuristic"
    assert unit.metadata.fallback_from == "agent-llm"
    assert unit.metadata.fallback_reason == "lint:micro_reference_exists"
    assert unit.micro_ids == ["micro-agent-unit-lint"]


def test_agent_llm_summarizer_backend_falls_back_to_heuristic_on_router_failure() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-agent-fallback")

    def failing_router(_request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("router unavailable")

    backend = AgentLLMSummarizerBackend(router=failing_router, fallback_backend=HeuristicSummarizerBackend())

    micro = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert micro.metadata.mode == "heuristic"
    assert micro.metadata.fallback_from == "agent-llm"
    assert micro.metadata.fallback_reason == "RuntimeError"
    assert micro.micro_id == "micro-agent-fallback"


def test_agent_llm_summarizer_backend_falls_back_when_micro_summary_fails_lint() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-agent-lint-fallback")

    def hallucinating_router(request: dict[str, object]) -> dict[str, object]:
        payload = _micro_payload(request["evidence"])
        payload["files"] = ["invented.py"]
        return payload

    backend = AgentLLMSummarizerBackend(router=hallucinating_router, fallback_backend=HeuristicSummarizerBackend())

    micro = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert micro.metadata.mode == "heuristic"
    assert micro.metadata.fallback_from == "agent-llm"
    assert micro.metadata.fallback_reason == "lint:no_new_files"
    assert micro.micro_id == "micro-agent-lint-fallback"
    assert "invented.py" not in micro.files


def test_get_summarizer_backend_rejects_agent_llm_without_router() -> None:
    try:
        get_summarizer_backend("agent-llm")
    except ValueError as exc:
        assert "agent-llm summarizer requires an injected Agent LLM router" in str(exc)
    else:
        raise AssertionError("agent-llm without router should fail")
