from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.semantic_lint import (  # noqa: E402
    SemanticLintIssue,
    SemanticLintReport,
    lint_promotion_substrate,
    render_semantic_lint_report,
)
from agent_context_substrate.wiki_patches import WikiPatchOperation, WikiPatchProposal  # noqa: E402


def test_lint_promotion_substrate_reports_missing_evidence_and_target() -> None:
    report = lint_promotion_substrate(
        promotions=[
            {
                "candidate_id": "packet-1-candidate-1",
                "packet_id": "packet-1",
                "status": "pending",
                "target_page": "",
                "evidence": [],
            }
        ],
        patch_proposals=[],
        applied_patch_records=[],
    )

    assert report == SemanticLintReport(
        issues=[
            SemanticLintIssue(
                code="promotion_missing_evidence",
                severity="warning",
                ref="promotion:packet-1-candidate-1",
                message="Promotion candidate has no evidence refs.",
            ),
            SemanticLintIssue(
                code="promotion_missing_target_page",
                severity="warning",
                ref="promotion:packet-1-candidate-1",
                message="Promotion candidate has no target_page and requires review.",
            ),
        ]
    )
    assert not report.ok


def test_lint_promotion_substrate_reports_applied_promotion_without_applied_patch_log() -> None:
    report = lint_promotion_substrate(
        promotions=[
            {
                "candidate_id": "packet-1-candidate-1",
                "packet_id": "packet-1",
                "status": "applied",
                "target_page": "summarization",
                "evidence": ["claim:packet-1-claim-1"],
            }
        ],
        patch_proposals=[
            WikiPatchProposal(
                proposal_id="packet-1-wiki-patch-proposal",
                packet_id="packet-1",
                status="proposed",
                operations=[
                    WikiPatchOperation(
                        patch_id="packet-1-patch-1",
                        candidate_id="packet-1-candidate-1",
                        target="concepts/summarization.md",
                        operation="insert_claim_block",
                        rationale="Apply candidate.",
                        evidence=["claim:packet-1-claim-1"],
                        risk="low",
                        diff={"before": "", "after": "managed block"},
                        status="proposed",
                    )
                ],
            )
        ],
        applied_patch_records=[],
    )

    assert report.issues == [
        SemanticLintIssue(
            code="applied_promotion_without_applied_patch",
            severity="error",
            ref="promotion:packet-1-candidate-1",
            message="Promotion is marked applied but has no applied patch log record.",
        )
    ]
    assert not report.ok


def test_lint_promotion_substrate_accepts_applied_promotion_with_log() -> None:
    report = lint_promotion_substrate(
        promotions=[
            {
                "candidate_id": "packet-1-candidate-1",
                "packet_id": "packet-1",
                "status": "applied",
                "target_page": "summarization",
                "evidence": ["claim:packet-1-claim-1"],
            }
        ],
        patch_proposals=[],
        applied_patch_records=[{"candidate_id": "packet-1-candidate-1", "patch_id": "packet-1-patch-1"}],
    )

    assert report.ok
    assert report.issues == []


def test_lint_promotion_substrate_reports_patch_candidate_and_log_integrity() -> None:
    report = lint_promotion_substrate(
        promotions=[
            {
                "candidate_id": "packet-1-candidate-1",
                "packet_id": "packet-1",
                "status": "pending",
                "target_page": "summarization",
                "evidence": ["claim:packet-1-claim-1"],
            }
        ],
        patch_proposals=[
            WikiPatchProposal(
                proposal_id="packet-1-wiki-patch-proposal",
                packet_id="packet-1",
                status="proposed",
                operations=[
                    WikiPatchOperation(
                        patch_id="packet-1-patch-missing-candidate",
                        candidate_id="packet-1-candidate-missing",
                        target="concepts/summarization.md",
                        operation="insert_claim_block",
                        rationale="Candidate id should exist.",
                        evidence=["claim:packet-1-claim-1"],
                        risk="low",
                        diff={"before": "", "after": "managed block"},
                        status="proposed",
                    ),
                    WikiPatchOperation(
                        patch_id="packet-1-patch-applied-without-log",
                        candidate_id="packet-1-candidate-1",
                        target="concepts/summarization.md",
                        operation="insert_claim_block",
                        rationale="Applied patches need an applied log record.",
                        evidence=["claim:packet-1-claim-1"],
                        risk="low",
                        diff={"before": "", "after": "managed block"},
                        status="applied",
                    ),
                ],
            )
        ],
        applied_patch_records=[],
    )

    assert report.issues == [
        SemanticLintIssue(
            code="patch_without_candidate",
            severity="error",
            ref="wiki_patch:packet-1-patch-missing-candidate",
            message="Wiki patch operation references a missing promotion candidate: packet-1-candidate-missing.",
        ),
        SemanticLintIssue(
            code="applied_patch_missing_log",
            severity="error",
            ref="wiki_patch:packet-1-patch-applied-without-log",
            message="Wiki patch operation is marked applied but has no applied patch log record.",
        ),
    ]
    assert not report.ok


def test_lint_promotion_substrate_reports_claims_without_source_and_duplicate_concepts() -> None:
    report = lint_promotion_substrate(
        promotions=[],
        patch_proposals=[],
        applied_patch_records=[],
        claim_atoms=[{"atom_id": "claim-1", "text": "Unsupported claim", "source_refs": []}],
        concept_atoms=[
            {"atom_id": "concept-1", "name": "Packet Only", "status": "active"},
            {"atom_id": "concept-2", "name": "packet  only", "status": "active"},
            {"atom_id": "concept-3", "name": "packet only", "status": "deprecated"},
        ],
    )

    assert report.issues == [
        SemanticLintIssue(
            code="claim_without_source",
            severity="error",
            ref="claim:claim-1",
            message="Claim atom has no source_refs.",
        ),
        SemanticLintIssue(
            code="duplicate_concept",
            severity="warning",
            ref="concept:packet only",
            message="Active concept atoms duplicate the same normalized name: concept-1, concept-2.",
        ),
    ]


def test_lint_promotion_substrate_reports_promotion_backlog() -> None:
    report = lint_promotion_substrate(
        promotions=[
            {"candidate_id": "cand-1", "status": "pending", "target_page": "Concept.md", "evidence": ["claim:1"]},
            {"candidate_id": "cand-2", "status": "pending", "target_page": "Concept.md", "evidence": ["claim:2"]},
            {"candidate_id": "cand-3", "status": "applied", "target_page": "Concept.md", "evidence": ["claim:3"]},
        ],
        patch_proposals=[],
        applied_patch_records=[{"candidate_id": "cand-3", "patch_id": "patch-3"}],
        promotion_backlog_threshold=2,
    )

    assert report.issues == [
        SemanticLintIssue(
            code="promotion_backlog",
            severity="warning",
            ref="promotions:pending",
            message="Pending promotion backlog is 2, meeting or exceeding threshold 2.",
        )
    ]


def test_render_semantic_lint_report() -> None:
    report = SemanticLintReport(
        issues=[
            SemanticLintIssue(
                code="promotion_missing_evidence",
                severity="warning",
                ref="promotion:packet-1-candidate-1",
                message="Promotion candidate has no evidence refs.",
            )
        ]
    )

    text = render_semantic_lint_report(report)

    assert "semantic_lint ok=False issues=1" in text
    assert "warning promotion_missing_evidence promotion:packet-1-candidate-1" in text
