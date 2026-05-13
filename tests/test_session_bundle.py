from __future__ import annotations

from agent_context_substrate import (
    SessionBundle,
    SessionMessage,
    build_micro_evidence_bundle,
    build_micro_summary,
    build_micro_summary_v2,
    derive_task_title,
    derive_unit_title,
    should_process_bundle,
)


def _raw_bundle() -> dict:
    return {
        "session": {
            "id": "session-typed",
            "source": "telegram",
            "title": "Typed session boundary",
            "started_at": 1.25,
            "ended_at": 2.5,
        },
        "messages": [
            {"id": 10, "role": "user", "content": "Please inspect README.md", "tool_name": None},
            {"id": 11, "role": "assistant", "content": "Done. README.md is relevant.", "tool_name": None},
            {"id": 12, "role": "tool", "content": "noisy tool output", "tool_name": "terminal"},
        ],
        "slice": {"start_message_id": 10, "end_message_id": 12},
        "message_count": 3,
    }


def test_session_bundle_round_trips_raw_hermes_bundle_shape() -> None:
    bundle = SessionBundle.from_raw_bundle(_raw_bundle())

    assert bundle.session_id == "session-typed"
    assert bundle.source == "telegram"
    assert bundle.title == "Typed session boundary"
    assert bundle.slice_start_message_id == 10
    assert bundle.slice_end_message_id == 12
    assert bundle.messages[0] == SessionMessage(
        id=10,
        role="user",
        content="Please inspect README.md",
        metadata={"tool_name": None},
    )
    assert bundle.to_raw_bundle()["session"]["id"] == "session-typed"
    assert bundle.to_raw_bundle()["messages"][2]["tool_name"] == "terminal"
    assert bundle.to_raw_bundle()["message_count"] == 3


def test_evidence_and_summary_builders_accept_typed_session_bundle() -> None:
    typed_bundle = SessionBundle.from_raw_bundle(_raw_bundle())

    evidence = build_micro_evidence_bundle(raw_bundle=typed_bundle, micro_id="micro-typed")
    summary = build_micro_summary(
        raw_bundle=typed_bundle,
        micro_id="micro-typed",
        parent_unit_id="unit-typed",
    )

    v2_summary = build_micro_summary_v2(
        raw_bundle=typed_bundle,
        micro_id="micro-typed-v2",
        parent_unit_id="unit-typed",
    )

    assert evidence.session_id == "session-typed"
    assert evidence.message_ids == [10, 11, 12]
    assert evidence.files == ["README.md"]
    assert summary.session_id == "session-typed"
    assert summary.message_ids == [10, 11, 12]
    assert summary.files == ["README.md"]
    assert summary.provenance is not None
    assert summary.provenance.source == "telegram"
    assert v2_summary.session_id == "session-typed"
    assert v2_summary.files == ["README.md"]


def test_naming_and_policy_helpers_accept_typed_session_bundle() -> None:
    typed_bundle = SessionBundle.from_raw_bundle(_raw_bundle())

    task_title = derive_task_title(typed_bundle, "session-typed")
    unit_title = derive_unit_title(typed_bundle, task_title)

    assert task_title == "Typed session boundary"
    assert unit_title == "Please inspect README.md"
    assert should_process_bundle(
        typed_bundle,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[r"^scratch"],
    )
    assert not should_process_bundle(
        typed_bundle,
        min_message_count=4,
        allowed_sources=["telegram"],
    )
    assert not should_process_bundle(
        typed_bundle,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[r"^Typed session boundary$"],
    )
