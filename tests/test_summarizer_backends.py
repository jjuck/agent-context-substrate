from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.evidence import build_micro_evidence_bundle  # noqa: E402
from agent_context_substrate.models import MicroSummaryV2, UnitSummaryV2  # noqa: E402
from agent_context_substrate.summarizer_backends import (  # noqa: E402
    CustomCommandSummarizerBackend,
    HeuristicSummarizerBackend,
    HybridSummarizerBackend,
    get_summarizer_backend,
)


def _raw_bundle() -> dict:
    return {
        "session": {"id": "session-backend", "source": "telegram", "title": "Backend"},
        "messages": [
            {"id": 1, "role": "user", "content": "Design summary backend for README.md"},
            {"id": 2, "role": "assistant", "content": "Done.\n- Added backend abstraction"},
        ],
    }


def test_heuristic_summarizer_backend_builds_micro_and_unit_summaries() -> None:
    backend = HeuristicSummarizerBackend()
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-backend")

    micro = backend.summarize_micro(evidence, schema_version="micro_summary_v2")
    unit = backend.summarize_unit(
        unit_id="unit-backend",
        session_id="session-backend",
        title="Backend abstraction",
        goal="Wrap heuristic summarization behind a backend interface.",
        micro_summaries=[micro],
        schema_version="unit_summary_v2",
    )

    assert backend.name == "heuristic"
    assert isinstance(micro, MicroSummaryV2)
    assert isinstance(unit, UnitSummaryV2)
    assert micro.metadata.mode == "heuristic"
    assert unit.metadata.mode == "heuristic"


def test_get_summarizer_backend_returns_heuristic_backend() -> None:
    backend = get_summarizer_backend("heuristic")

    assert isinstance(backend, HeuristicSummarizerBackend)


def test_hybrid_summarizer_backend_sends_heuristic_spine_to_router() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-hybrid")
    requests: list[dict[str, object]] = []

    def router(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        heuristic = request["heuristic_summary"]
        return {
            **heuristic,
            "knowledge_summary": "hybrid semantic knowledge",
            "retrieval_summary": "hybrid semantic retrieval README.md",
            "metadata": {
                **heuristic["metadata"],
                "mode": "hybrid",
                "prompt_version": "hybrid_v1",
                "confidence": 0.8,
            },
        }

    backend = HybridSummarizerBackend(router=router, routing_hints={"budget": "cheap"})

    summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert backend.name == "hybrid"
    assert summary.metadata.mode == "hybrid"
    assert summary.knowledge_summary == "hybrid semantic knowledge"
    assert requests[0]["kind"] == "micro"
    assert requests[0]["mode"] == "hybrid"
    assert requests[0]["routing_hints"] == {"budget": "cheap"}
    assert requests[0]["evidence"]["micro_id"] == "micro-hybrid"
    assert requests[0]["heuristic_summary"]["metadata"]["mode"] == "heuristic"
    assert requests[0]["heuristic_summary"]["files"] == ["README.md"]


def test_hybrid_summarizer_backend_falls_back_to_heuristic_with_metadata() -> None:
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-hybrid-fallback")

    def failing_router(_request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("router unavailable")

    backend = HybridSummarizerBackend(router=failing_router)

    summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert summary.metadata.mode == "heuristic"
    assert summary.metadata.fallback_from == "hybrid"
    assert summary.metadata.fallback_reason == "RuntimeError"
    assert summary.micro_id == "micro-hybrid-fallback"


def test_get_summarizer_backend_returns_hybrid_backend_when_router_is_injected() -> None:
    backend = get_summarizer_backend("hybrid", agent_llm_router=lambda _request: {})

    assert isinstance(backend, HybridSummarizerBackend)


def test_custom_command_summarizer_backend_uses_command_stdout_for_micro_summary(tmp_path: Path) -> None:
    script_path = tmp_path / "micro_summarizer.py"
    script_path.write_text(
        """
import json
import sys

evidence = json.loads(sys.stdin.read())
message_ids = evidence["message_ids"]
print(json.dumps({
    "micro_id": evidence["micro_id"],
    "session_id": evidence["session_id"],
    "message_ids": message_ids,
    "recovery_summary": "custom recovery",
    "knowledge_summary": "custom knowledge",
    "retrieval_summary": "custom retrieval README.md",
    "user_intent": "custom intent",
    "assistant_outcome": "custom outcome",
    "decisions": [{"text": "custom decision", "evidence_message_ids": message_ids, "confidence": 0.9}],
    "claims": [],
    "action_items": [],
    "open_questions": [],
    "files": ["README.md"],
    "entities": [],
    "concepts": [],
    "metadata": {
        "mode": "custom-command",
        "schema_version": "micro_summary_v2",
        "prompt_version": None,
        "model": None,
        "input_hash": "sha256:custom",
        "created_at": "2026-05-07T00:00:00+00:00",
        "confidence": 0.9
    },
    "provenance": None,
}, ensure_ascii=False))
""".strip(),
        encoding="utf-8",
    )
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-custom")
    backend = CustomCommandSummarizerBackend(command=f"{sys.executable} {script_path}")

    summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert summary.micro_id == "micro-custom"
    assert summary.recovery_summary == "custom recovery"
    assert summary.decisions[0].text == "custom decision"
    assert summary.metadata.mode == "custom-command"


def test_custom_command_summarizer_backend_falls_back_when_command_fails(tmp_path: Path) -> None:
    script_path = tmp_path / "failing_summarizer.py"
    script_path.write_text("import sys\nsys.exit(7)\n", encoding="utf-8")
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-custom-fallback")
    backend = CustomCommandSummarizerBackend(command=f"{sys.executable} {script_path}")

    summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert summary.metadata.mode == "heuristic"
    assert summary.metadata.fallback_from == "custom-command"
    assert summary.metadata.fallback_reason == "command_failed"
    assert summary.micro_id == "micro-custom-fallback"


def test_custom_command_summarizer_backend_falls_back_when_micro_summary_fails_lint(tmp_path: Path) -> None:
    script_path = tmp_path / "hallucinating_micro_summarizer.py"
    script_path.write_text(
        """
import json
import sys

evidence = json.loads(sys.stdin.read())
message_ids = evidence["message_ids"]
print(json.dumps({
    "micro_id": evidence["micro_id"],
    "session_id": evidence["session_id"],
    "message_ids": message_ids,
    "recovery_summary": "custom recovery",
    "knowledge_summary": "custom knowledge",
    "retrieval_summary": "custom retrieval invented.py",
    "user_intent": "custom intent",
    "assistant_outcome": "custom outcome",
    "decisions": [{"text": "custom decision", "evidence_message_ids": message_ids, "confidence": 0.9}],
    "claims": [],
    "action_items": [],
    "open_questions": [],
    "files": ["invented.py"],
    "entities": [],
    "concepts": [],
    "metadata": {
        "mode": "custom-command",
        "schema_version": "micro_summary_v2",
        "prompt_version": None,
        "model": None,
        "input_hash": "sha256:custom",
        "created_at": "2026-05-07T00:00:00+00:00",
        "confidence": 0.9
    },
    "provenance": None,
}, ensure_ascii=False))
""".strip(),
        encoding="utf-8",
    )
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-custom-lint-fallback")
    backend = CustomCommandSummarizerBackend(command=f"{sys.executable} {script_path}")

    summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")

    assert summary.metadata.mode == "heuristic"
    assert summary.metadata.fallback_from == "custom-command"
    assert summary.metadata.fallback_reason == "lint:no_new_files"
    assert summary.micro_id == "micro-custom-lint-fallback"
    assert "invented.py" not in summary.files


def test_custom_command_summarizer_backend_falls_back_when_unit_summary_fails_lint(tmp_path: Path) -> None:
    script_path = tmp_path / "hallucinating_unit_summarizer.py"
    script_path.write_text(
        """
import json
import sys

payload = json.loads(sys.stdin.read())
micro = payload["micro_summaries"][0]
print(json.dumps({
    "unit_id": payload["unit_id"],
    "session_id": payload["session_id"],
    "title": payload["title"],
    "goal": payload["goal"],
    "state": "completed",
    "decisions": micro["decisions"],
    "progress": ["custom progress"],
    "next_actions": [],
    "open_questions": [],
    "risk_notes": [],
    "wiki_candidates": [],
    "micro_ids": ["invented-micro"],
    "related_pages": [],
    "metadata": {
        "mode": "custom-command",
        "schema_version": "unit_summary_v2",
        "prompt_version": None,
        "model": None,
        "input_hash": "sha256:custom-unit",
        "created_at": "2026-05-07T00:00:00+00:00",
        "confidence": 0.9
    },
    "provenance": None,
}, ensure_ascii=False))
""".strip(),
        encoding="utf-8",
    )
    evidence = build_micro_evidence_bundle(raw_bundle=_raw_bundle(), micro_id="micro-custom-unit")
    micro = HeuristicSummarizerBackend().summarize_micro(evidence, schema_version="micro_summary_v2")
    backend = CustomCommandSummarizerBackend(command=f"{sys.executable} {script_path}")

    unit = backend.summarize_unit(
        unit_id="unit-custom-lint-fallback",
        session_id="session-backend",
        title="Backend abstraction",
        goal="Wrap heuristic summarization behind a backend interface.",
        micro_summaries=[micro],
        schema_version="unit_summary_v2",
    )

    assert unit.metadata.mode == "heuristic"
    assert unit.metadata.fallback_from == "custom-command"
    assert unit.metadata.fallback_reason == "lint:micro_reference_exists"
    assert unit.micro_ids == ["micro-custom-unit"]


def test_get_summarizer_backend_returns_custom_command_backend() -> None:
    backend = get_summarizer_backend("custom-command", command="python summarizer.py")

    assert isinstance(backend, CustomCommandSummarizerBackend)
