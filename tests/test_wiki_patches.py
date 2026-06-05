from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.promotions import PromotionCandidate  # noqa: E402
from agent_context_substrate.wiki_patches import (  # noqa: E402
    WikiPatchApplyResult,
    WikiPatchOperation,
    WikiPatchProposal,
    apply_wiki_patch_proposal,
    plan_wiki_patch_proposal,
    render_wiki_patch_proposal_markdown,
)


def _candidate() -> PromotionCandidate:
    return PromotionCandidate(
        candidate_id="packet-1-candidate-1",
        packet_id="packet-1",
        kind="concept_update",
        target_page="summarization",
        reason="Claim atom packet-1-claim-1 may update durable wiki knowledge.",
        evidence=["claim:packet-1-claim-1", "packet:packet-1#micro-1"],
        proposed_change="Heuristic summarizer should remain the default for privacy.",
        proposed_action="update_existing",
        confidence=0.75,
        status="pending",
    )


def test_plan_wiki_patch_proposal_from_promotion_candidate(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Summarization\n\nExisting human prose.\n", encoding="utf-8")

    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=wiki_root)

    assert proposal == WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-1",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="insert_claim_block",
                rationale="Claim atom packet-1-claim-1 may update durable wiki knowledge.",
                evidence=["claim:packet-1-claim-1", "packet:packet-1#micro-1"],
                risk="low",
                diff={
                    "before": "",
                    "after": "<!-- acs:auto:claims:start -->\n- Heuristic summarizer should remain the default for privacy. `claim:packet-1-claim-1`\n<!-- acs:auto:claims:end -->",
                },
                status="proposed",
            )
        ],
        status="proposed",
    )
    assert WikiPatchProposal.from_dict(proposal.to_dict()) == proposal


def test_render_wiki_patch_proposal_markdown(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Summarization\n", encoding="utf-8")
    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=wiki_root)

    markdown = render_wiki_patch_proposal_markdown(proposal)

    assert "# Wiki Patch Proposal: packet-1" in markdown
    assert "packet-1-patch-1" in markdown
    assert "concepts/summarization.md" in markdown
    assert "insert_claim_block" in markdown
    assert "Heuristic summarizer" in markdown
    assert "claim:packet-1-claim-1" in markdown


def test_apply_wiki_patch_proposal_dry_run_does_not_modify_wiki(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n\nExisting human prose.\n"
    target.write_text(original, encoding="utf-8")
    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=wiki_root)

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=True)

    assert result == WikiPatchApplyResult(
        dry_run=True,
        applied_patch_ids=[],
        skipped_patch_ids=[],
        planned_patch_ids=["packet-1-patch-1"],
    )
    assert target.read_text(encoding="utf-8") == original


def test_create_page_patch_includes_lifecycle_metadata(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    candidate = PromotionCandidate(
        candidate_id="packet-1-candidate-new",
        packet_id="packet-1",
        kind="concept_update",
        target_page="new-concept",
        reason="New concept deserves a seed page.",
        evidence=["claim:packet-1-claim-new"],
        proposed_change="New concept should be reviewed as a seed page.",
        proposed_action="create_page",
        confidence=0.7,
        status="pending",
    )

    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[candidate], wiki_root=wiki_root)

    operation = proposal.operations[0]
    assert operation.operation == "create_page"
    assert operation.diff["after"].startswith(
        "---\nstatus: seed\nmaturity: 0.2\nreview_needed: true\n---\n"
    )
    assert "# New Concept" in operation.diff["after"]
    assert "New concept should be reviewed as a seed page." in operation.diff["after"]

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    target = wiki_root / "concepts" / "new-concept.md"
    assert result.applied_patch_ids == ["packet-1-patch-1"]
    assert target.read_text(encoding="utf-8") == operation.diff["after"]


def test_apply_wiki_patch_proposal_skips_conflicting_managed_block_with_reason(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# Summarization\n\n"
        "<!-- acs:auto:claims:start -->\n"
        "- Original generated claim. `claim:old`\n"
        "<!-- acs:auto:claims:end -->\n",
        encoding="utf-8",
    )
    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=wiki_root)
    target.write_text(
        "# Summarization\n\n"
        "<!-- acs:auto:claims:start -->\n"
        "- Human reviewed generated claim. `claim:changed`\n"
        "<!-- acs:auto:claims:end -->\n",
        encoding="utf-8",
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-1"]
    assert result.skipped_reasons == {
        "packet-1-patch-1": "conflict: current managed claim block differs from proposal before"
    }
    assert "Human reviewed generated claim" in target.read_text(encoding="utf-8")
    assert result.to_dict()["skipped_reasons"] == result.skipped_reasons


def test_apply_wiki_patch_proposal_updates_only_managed_claim_block(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# Summarization\n\nHuman intro.\n\n"
        "<!-- acs:auto:claims:start -->\n"
        "- Old generated claim. `claim:old`\n"
        "<!-- acs:auto:claims:end -->\n\n"
        "Human outro.\n",
        encoding="utf-8",
    )
    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=wiki_root)

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == ["packet-1-patch-1"]
    updated = target.read_text(encoding="utf-8")
    assert "Human intro." in updated
    assert "Human outro." in updated
    assert "Old generated claim" not in updated
    assert "Heuristic summarizer should remain the default for privacy." in updated
    assert updated.count("<!-- acs:auto:claims:start -->") == 1


def test_apply_wiki_patch_proposal_skips_unsafe_target_paths(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    outside = tmp_path / "outside.md"
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-unsafe",
                candidate_id="packet-1-candidate-1",
                target="../outside.md",
                operation="insert_claim_block",
                rationale="Unsafe path should be skipped.",
                evidence=["claim:packet-1-claim-1"],
                risk="high",
                diff={"before": "", "after": "unsafe"},
                status="proposed",
            )
        ],
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-unsafe"]
    assert not outside.exists()


def test_apply_wiki_patch_proposal_skips_system_and_non_markdown_targets(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    system_target = wiki_root / "_system" / "secret.md"
    non_markdown_target = wiki_root / "concepts" / "data.json"
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-system",
                candidate_id="packet-1-candidate-1",
                target="_system/secret.md",
                operation="insert_claim_block",
                rationale="System pages should not be modified.",
                evidence=["claim:packet-1-claim-1"],
                risk="high",
                diff={"before": "", "after": "unsafe"},
                status="proposed",
            ),
            WikiPatchOperation(
                patch_id="packet-1-patch-json",
                candidate_id="packet-1-candidate-1",
                target="concepts/data.json",
                operation="insert_claim_block",
                rationale="Non-markdown targets should not be modified.",
                evidence=["claim:packet-1-claim-1"],
                risk="high",
                diff={"before": "", "after": "unsafe"},
                status="proposed",
            ),
        ],
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-system", "packet-1-patch-json"]
    assert not system_target.exists()
    assert not non_markdown_target.exists()


def test_apply_wiki_patch_proposal_skips_unsupported_operations(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n"
    target.write_text(original, encoding="utf-8")
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-unsupported",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="replace_section",
                rationale="Unsupported operation should be skipped until explicitly implemented.",
                evidence=["claim:packet-1-claim-1"],
                risk="high",
                diff={"before": "# Summarization", "after": "replacement"},
                status="proposed",
            )
        ],
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-unsupported"]
    assert target.read_text(encoding="utf-8") == original



def test_apply_wiki_patch_proposal_defaults_to_alpha_operation_subset(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\n"
        "title: Summarization\n"
        "status: active\n"
        "---\n"
        "# Summarization\n\n"
        "## Notes\n"
        "Existing note.\n\n"
        "## Related Pages\n"
        "- [[Context Packet]]\n",
        encoding="utf-8",
    )
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-append",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="append_section",
                rationale="Append evidence note.",
                evidence=["claim:packet-1-claim-1"],
                risk="low",
                diff={"section": "Notes", "after": "- New evidence-backed note."},
                status="proposed",
            ),
            WikiPatchOperation(
                patch_id="packet-1-patch-link",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="add_link",
                rationale="Link related page.",
                evidence=["claim:packet-1-claim-1"],
                risk="low",
                diff={"after": "[[LLM Wiki]]"},
                status="proposed",
            ),
            WikiPatchOperation(
                patch_id="packet-1-patch-stale",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="mark_stale",
                rationale="Mark page for review.",
                evidence=["claim:packet-1-claim-1"],
                risk="low",
                diff={"after": "review_needed: true"},
                status="proposed",
            ),
        ],
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == ["packet-1-patch-append"]
    assert result.skipped_patch_ids == ["packet-1-patch-link", "packet-1-patch-stale"]
    updated = target.read_text(encoding="utf-8")
    assert "status: active" in updated
    assert "review_needed: true" not in updated
    assert "## Notes\nExisting note.\n- New evidence-backed note.\n\n## Related Pages" in updated
    assert "- [[Context Packet]]" in updated
    assert "- [[LLM Wiki]]" not in updated


def test_plan_wiki_patch_proposal_never_reads_unsafe_target_page(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    review_dir = wiki_root / "_review"
    review_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(
        "# Outside\n\n"
        "<!-- acs:auto:claims:start -->\n"
        "- outside managed claim should not leak\n"
        "<!-- acs:auto:claims:end -->\n",
        encoding="utf-8",
    )
    candidate = PromotionCandidate(
        candidate_id="packet-1-candidate-unsafe",
        packet_id="packet-1",
        kind="concept_update",
        target_page="../outside.md",
        reason="Unsafe target should be quarantined.",
        evidence=["claim:packet-1-claim-unsafe"],
        proposed_change="Safe generated claim.",
        proposed_action="update_existing",
        confidence=0.75,
        status="pending",
    )

    proposal = plan_wiki_patch_proposal(packet_id="packet-1", candidates=[candidate], wiki_root=wiki_root)

    assert len(proposal.operations) == 1
    operation = proposal.operations[0]
    assert operation.target == "_review/untriaged.md"
    assert "outside managed claim" not in operation.diff["before"]
    assert "Safe generated claim." in operation.diff["after"]


def test_plan_flexible_wiki_patch_proposes_full_page_revision_with_policy_metadata(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n\nExisting human prose.\n"
    target.write_text(original, encoding="utf-8")

    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=wiki_root,
        write_mode="flexible",
    )

    operation = proposal.operations[0]
    assert proposal.metadata["write_mode"] == "flexible"
    assert proposal.metadata["judge_mode"] == "off"
    assert proposal.metadata["judge_verdict"] == "not_requested"
    assert proposal.metadata["policy_verdict"] == "proposal_only"
    assert proposal.metadata["rubric_advisories"]
    assert operation.operation == "replace_page"
    assert operation.diff["base_sha256"] == hashlib.sha256(original.encode("utf-8")).hexdigest()
    assert operation.diff["before"] == original
    assert "Existing human prose." in operation.diff["after"]
    assert "Heuristic summarizer should remain the default for privacy." in operation.diff["after"]
    assert "claim:packet-1-claim-1" in operation.diff["after"]


def test_apply_flexible_replace_page_requires_approved_judge_verdict(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n\nExisting human prose.\n"
    target.write_text(original, encoding="utf-8")
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=wiki_root,
        write_mode="flexible",
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-1"]
    assert result.skipped_reasons == {
        "packet-1-patch-1": "flexible write requires approved judge verdict"
    }
    assert target.read_text(encoding="utf-8") == original


def test_apply_replace_page_requires_flexible_policy_metadata(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n\nExisting human prose.\n"
    target.write_text(original, encoding="utf-8")
    proposal = WikiPatchProposal(
        proposal_id="packet-1-wiki-patch-proposal",
        packet_id="packet-1",
        status="proposed",
        operations=[
            WikiPatchOperation(
                patch_id="packet-1-patch-1",
                candidate_id="packet-1-candidate-1",
                target="concepts/summarization.md",
                operation="replace_page",
                rationale="Hand-edited proposal should not bypass write policy.",
                evidence=["claim:packet-1-claim-1"],
                risk="medium",
                diff={
                    "before": original,
                    "after": "# Summarization\n\nUnsafe replacement.\n",
                    "base_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                },
                status="proposed",
            )
        ],
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-1"]
    assert result.skipped_reasons == {
        "packet-1-patch-1": "replace_page requires flexible write metadata"
    }
    assert target.read_text(encoding="utf-8") == original


def test_apply_flexible_replace_page_updates_when_judge_approved_and_hash_matches(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    original = "# Summarization\n\nExisting human prose.\n"
    target.write_text(original, encoding="utf-8")
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=wiki_root,
        write_mode="flexible",
        judge_verdict="approved",
    )

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == ["packet-1-patch-1"]
    updated = target.read_text(encoding="utf-8")
    assert "Existing human prose." in updated
    assert "Heuristic summarizer should remain the default for privacy." in updated
    assert "claim:packet-1-claim-1" in updated


def test_apply_flexible_replace_page_skips_hash_conflict(tmp_path) -> None:
    wiki_root = tmp_path / "wiki"
    target = wiki_root / "concepts" / "summarization.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Summarization\n\nOriginal prose.\n", encoding="utf-8")
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=wiki_root,
        write_mode="flexible",
        judge_verdict="approved",
    )
    target.write_text("# Summarization\n\nHuman changed prose.\n", encoding="utf-8")

    result = apply_wiki_patch_proposal(proposal=proposal, wiki_root=wiki_root, dry_run=False)

    assert result.applied_patch_ids == []
    assert result.skipped_patch_ids == ["packet-1-patch-1"]
    assert result.skipped_reasons == {
        "packet-1-patch-1": "conflict: current page hash differs from proposal base"
    }
    assert "Human changed prose." in target.read_text(encoding="utf-8")
