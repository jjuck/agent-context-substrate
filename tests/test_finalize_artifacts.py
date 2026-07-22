from pathlib import Path

from agent_context_substrate.finalize_artifacts import (
    FinalizeArtifactOptions,
    build_finalize_artifacts,
    summary_artifact_paths,
)
from agent_context_substrate.paths import HarnessPaths
from agent_context_substrate.session_bundle import SessionBundle, SessionMessage


def test_finalize_artifacts_builds_source_neutral_packet_and_summary(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project", wiki_root=tmp_path / "wiki")
    paths.ensure_project_dirs()
    raw_export_path = paths.exports_dir / "raw" / "session-1.json"
    raw_export_path.parent.mkdir(parents=True, exist_ok=True)
    raw_export_path.write_text("{}", encoding="utf-8")
    bundle = SessionBundle(
        session_id="session-1",
        source="test-adapter",
        title="Typed boundary",
        messages=[
            SessionMessage(id=1, role="user", content="Document the shared finalize boundary."),
            SessionMessage(id=2, role="assistant", content="The boundary now accepts SessionBundle."),
        ],
        slice_start_message_id=1,
        slice_end_message_id=2,
    )

    result = build_finalize_artifacts(
        session_bundle=bundle,
        raw_export_path=raw_export_path,
        paths=paths,
        options=FinalizeArtifactOptions(
            session_id="session-1",
            packet_id="packet-1",
            macro_context="Recover a typed session without replaying the transcript.",
            summary_mode="heuristic",
        ),
    )

    assert result.raw_export_path == raw_export_path
    assert result.packet.raw_pointers[0].source == "test-adapter"
    assert result.summary_artifacts is not None
    assert summary_artifact_paths(result.summary_artifacts)["summary_micro_path"] == str(
        result.summary_artifacts.micro_path
    )
