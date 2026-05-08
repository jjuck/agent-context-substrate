from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate import build_micro_evidence_bundle as exported_build_micro_evidence_bundle  # noqa: E402
from agent_context_substrate.evidence import build_micro_evidence_bundle, export_micro_evidence_bundle  # noqa: E402
from agent_context_substrate.models import EvidenceMessage, MicroEvidenceBundle  # noqa: E402


def test_build_micro_evidence_bundle_is_public_export() -> None:
    assert exported_build_micro_evidence_bundle is build_micro_evidence_bundle


def test_build_micro_evidence_bundle_collects_grounded_inputs() -> None:
    raw_bundle = {
        "session": {"id": "session-1", "source": "telegram", "title": "Hybrid summary"},
        "messages": [
            {
                "id": 10,
                "role": "user",
                "content": (
                    "Please design hybrid summarization for README.md.\n"
                    "See https://example.com/spec.\n"
                    "```python\nprint('hello')\n```"
                ),
            },
            {
                "id": 11,
                "role": "assistant",
                "content": (
                    "# Proposal\n"
                    "Use a heuristic pre-pass plus structured LLM summary.\n"
                    "- Keep message ids as evidence\n"
                    "- Add summary-lint\n"
                    "Next question?"
                ),
            },
        ],
    }

    bundle = build_micro_evidence_bundle(raw_bundle=raw_bundle, micro_id="micro-1")

    assert bundle == MicroEvidenceBundle(
        session_id="session-1",
        micro_id="micro-1",
        message_ids=[10, 11],
        user_messages=[
            EvidenceMessage(
                message_id=10,
                role="user",
                content=(
                    "Please design hybrid summarization for README.md.\n"
                    "See https://example.com/spec.\n"
                    "```python\nprint('hello')\n```"
                ),
            )
        ],
        assistant_messages=[
            EvidenceMessage(
                message_id=11,
                role="assistant",
                content=(
                    "# Proposal\n"
                    "Use a heuristic pre-pass plus structured LLM summary.\n"
                    "- Keep message ids as evidence\n"
                    "- Add summary-lint\n"
                    "Next question?"
                ),
            )
        ],
        heuristic_request="Please design hybrid summarization for README.md. See https://example.com/spec. ```python print('hello') ```",
        heuristic_outcome="Proposal",
        heuristic_key_points=["Keep message ids as evidence", "Add summary-lint"],
        files=["README.md"],
        code_blocks=["python\nprint('hello')"],
        urls=["https://example.com/spec"],
        headings=["Proposal"],
        explicit_questions=["Next question?"],
    )


def test_micro_evidence_bundle_round_trips_to_dict() -> None:
    bundle = MicroEvidenceBundle(
        session_id="session-1",
        micro_id="micro-1",
        message_ids=[10],
        user_messages=[EvidenceMessage(message_id=10, role="user", content="Update README.md")],
        assistant_messages=[],
        heuristic_request="Update README.md",
        heuristic_outcome=None,
        heuristic_key_points=[],
        files=["README.md"],
        code_blocks=[],
        urls=[],
        headings=[],
        explicit_questions=[],
    )

    payload = bundle.to_dict()

    assert payload["session_id"] == "session-1"
    assert payload["user_messages"][0]["message_id"] == 10
    assert MicroEvidenceBundle.from_dict(payload) == bundle


def test_export_micro_evidence_bundle_writes_debug_json(tmp_path: Path) -> None:
    bundle = MicroEvidenceBundle(
        session_id="session-1",
        micro_id="packet-1-micro-1",
        message_ids=[10],
        user_messages=[EvidenceMessage(message_id=10, role="user", content="Update README.md")],
        assistant_messages=[],
        heuristic_request="Update README.md",
        heuristic_outcome=None,
        heuristic_key_points=[],
        files=["README.md"],
        code_blocks=[],
        urls=[],
        headings=[],
        explicit_questions=[],
    )

    export_path = export_micro_evidence_bundle(bundle=bundle, exports_dir=tmp_path / "exports")

    assert export_path == tmp_path / "exports" / "evidence" / "session-1" / "packet-1-micro-1.json"
    assert export_path.exists()
    assert MicroEvidenceBundle.from_dict(__import__("json").loads(export_path.read_text(encoding="utf-8"))) == bundle
