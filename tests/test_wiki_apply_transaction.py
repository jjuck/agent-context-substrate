from pathlib import Path

import pytest

from agent_context_substrate.paths import HarnessPaths
from agent_context_substrate.wiki_apply_transaction import WikiApplyTransaction
from agent_context_substrate.wiki_patches import WikiPatchOperation, WikiPatchProposal


class SimulatedProcessExit(BaseException):
    pass


def test_wiki_apply_transaction_recovers_prepared_snapshot_after_process_exit(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    page_path = wiki_root / "Durable Knowledge.md"
    page_path.write_text("original\n", encoding="utf-8")
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-1",
                candidate_id="packet-1-candidate-1",
                candidate_ids=["packet-1-candidate-1"],
                target="Durable Knowledge.md",
                operation="replace_page",
                rationale="Exercise transaction recovery.",
                evidence=["claim:packet-1-claim-1"],
                risk="medium",
                diff={},
                status="proposed",
            )
        ],
    )
    paths = HarnessPaths(project_root=project_root, wiki_root=wiki_root, home_dir=tmp_path)
    transaction = WikiApplyTransaction(paths=paths, wiki_root=wiki_root, proposal=proposal)

    def apply_before_exit() -> str:
        page_path.write_text("partially applied\n", encoding="utf-8")
        return "partial"

    with pytest.raises(SimulatedProcessExit):
        transaction.execute(
            apply_pages=apply_before_exit,
            commit_artifacts=lambda _result: (_ for _ in ()).throw(SimulatedProcessExit()),
        )

    assert page_path.read_text(encoding="utf-8") == "partially applied\n"

    recovered_original: list[str] = []

    def apply_after_recovery() -> str:
        recovered_original.append(page_path.read_text(encoding="utf-8"))
        page_path.write_text("completed\n", encoding="utf-8")
        return "completed"

    result = WikiApplyTransaction(paths=paths, wiki_root=wiki_root, proposal=proposal).execute(
        apply_pages=apply_after_recovery,
        commit_artifacts=lambda _result: None,
    )

    assert result == "completed"
    assert recovered_original == ["original\n"]
    assert page_path.read_text(encoding="utf-8") == "completed\n"
