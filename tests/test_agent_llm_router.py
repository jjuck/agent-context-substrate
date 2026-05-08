from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.agent_llm_router import (  # noqa: E402
    AgentLLMRouterUnavailable,
    build_agent_llm_router,
)


class FakeHostRouter:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def route_llm_json(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        return {"content": '{"summary": "ok", "mode": "agent-llm"}'}


def test_build_agent_llm_router_delegates_to_host_json_router() -> None:
    host = FakeHostRouter()
    router = build_agent_llm_router(host)

    response = router(
        {
            "kind": "micro",
            "schema_version": "micro_summary_v2",
            "evidence": {"session_id": "session-1", "message_ids": [1, 2]},
            "routing_hints": {"budget": "cheap"},
        }
    )

    assert response == {"summary": "ok", "mode": "agent-llm"}
    assert len(host.requests) == 1
    host_request = host.requests[0]
    assert host_request["routing_hints"] == {"budget": "cheap"}
    assert host_request["response_format"] == {"type": "json_object"}
    assert host_request["messages"][0]["role"] == "system"
    assert "strict JSON" in host_request["messages"][0]["content"]
    assert '"session_id": "session-1"' in host_request["messages"][1]["content"]


def test_build_agent_llm_router_redacts_secret_like_payload_before_host_call() -> None:
    host = FakeHostRouter()
    router = build_agent_llm_router(host)

    router(
        {
            "kind": "micro",
            "schema_version": "micro_summary_v2",
            "evidence": {
                "session_id": "session-1",
                "user_messages": [
                    {
                        "message_id": 1,
                        "role": "user",
                        "content": "api_key=sk-testsecret1234567890 and email user@example.com",
                    }
                ],
            },
            "routing_hints": {"api_key": "sk-hintsecret1234567890"},
        }
    )

    serialized_messages = str(host.requests[0]["messages"])
    assert "sk-testsecret1234567890" not in serialized_messages
    assert "sk-hintsecret1234567890" not in serialized_messages
    assert "user@example.com" not in serialized_messages
    assert "<REDACTED_SECRET>" in serialized_messages
    assert host.requests[0]["routing_hints"] == {"api_key": "<REDACTED_SECRET>"}


def test_build_agent_llm_router_rejects_host_without_llm_route() -> None:
    try:
        build_agent_llm_router(object())
    except AgentLLMRouterUnavailable as exc:
        assert "no compatible Agent LLM router" in str(exc)
    else:
        raise AssertionError("host without an LLM router should fail")
