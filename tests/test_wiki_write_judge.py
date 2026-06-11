from __future__ import annotations

import json

from pathlib import Path

from agent_context_substrate.summarizer_backends import LLMInputSafetyOptions, _prepare_llm_request
from agent_context_substrate.promotions import PromotionCandidate
from agent_context_substrate.wiki_patches import plan_wiki_patch_proposal
from agent_context_substrate.wiki_write_judge import (
    WikiWriteDecision,
    evaluate_wiki_write_with_judge,
    export_wiki_write_decision,
    _build_wiki_write_judge_request,
    _wiki_write_decision_json_schema,
)


def _candidate() -> PromotionCandidate:
    return PromotionCandidate(
        candidate_id="packet-1-candidate-1",
        packet_id="packet-1",
        kind="concept_update",
        target_page="summarization",
        reason="Durable claim worth integrating.",
        evidence=["claim:packet-1-claim-1", "message:2"],
        proposed_change="LLM Wiki pages should be maintained as living knowledge graph prose.",
        proposed_action="update_existing",
        confidence=0.91,
        status="pending",
    )


def test_wiki_write_judge_approves_flexible_apply_when_llm_verdict_is_strong(tmp_path) -> None:
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=tmp_path / "wiki",
        write_mode="flexible",
    )
    requests: list[dict[str, object]] = []

    def router(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        return {
            "ok": True,
            "score": 0.91,
            "decision": "apply_flexible",
            "candidate_ids": ["packet-1-candidate-1"],
            "issues": [],
            "rationale": "Evidence-backed durable knowledge belongs in the LLM Wiki.",
            "metadata": {"model": "judge-test"},
        }

    decision = evaluate_wiki_write_with_judge(
        packet_id="packet-1",
        candidates=[_candidate()],
        proposal=proposal,
        mode="hybrid",
        router=router,
        min_score=0.85,
    )

    assert decision.ok is True
    assert decision.decision == "apply_flexible"
    assert decision.approved_for_auto_apply("apply-flexible") is True
    assert requests[0]["kind"] == "wiki-write-judge"
    assert requests[0]["proposal"]["operations"][0]["operation"] == "create_page"


def test_wiki_write_judge_degrades_to_review_required_without_llm() -> None:
    decision = evaluate_wiki_write_with_judge(
        packet_id="packet-1",
        candidates=[_candidate()],
        proposal=plan_wiki_patch_proposal(packet_id="packet-1", candidates=[_candidate()], wiki_root=Path(".")),
        mode="hybrid",
        router=None,
    )

    assert decision.ok is False
    assert decision.decision == "review_required"
    assert decision.approved_for_auto_apply("apply-flexible") is False
    assert decision.issues[0].code == "judge_unavailable"


def test_export_wiki_write_decision_writes_reviewable_artifact(tmp_path) -> None:
    decision = WikiWriteDecision(
        ok=True,
        score=0.9,
        decision="apply_flexible",
        candidate_ids=["packet-1-candidate-1"],
        issues=[],
        rationale="Approved.",
        metadata={"judge_mode": "hybrid"},
    )

    path = export_wiki_write_decision(packet_id="packet-1", decision=decision, project_root=tmp_path)

    assert path == tmp_path / "data" / "wiki_decisions" / "packet-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["decision"] == "apply_flexible"
    assert payload["metadata"]["schema_version"] == "wiki_write_judge_v1"


def test_wiki_write_decision_schema_is_strict_for_codex_structured_output() -> None:
    schema = _wiki_write_decision_json_schema()

    def assert_object_schemas_are_strict(node: object, path: str = "$") -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, path
            for key, value in node.items():
                assert_object_schemas_are_strict(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                assert_object_schemas_are_strict(value, f"{path}[{index}]")

    assert_object_schemas_are_strict(schema)


def test_wiki_write_decision_normalizes_review_required_ok_flag() -> None:
    decision = WikiWriteDecision.from_dict(
        {
            "ok": True,
            "score": 0.62,
            "decision": "review_required",
            "candidate_ids": ["packet-1-candidate-1"],
            "issues": [
                {
                    "code": "low_confidence",
                    "severity": "warning",
                    "field": "candidates.confidence",
                    "message": "Confidence is below the auto-apply threshold.",
                    "evidence_refs": ["claim:packet-1-claim-1"],
                }
            ],
            "rationale": "Human review should decide whether this belongs in the wiki.",
            "metadata": {},
        }
    )

    assert decision.ok is False
    assert decision.decision == "review_required"
    assert decision.candidate_ids == ["packet-1-candidate-1"]


def test_wiki_write_judge_request_preserves_material_under_default_llm_budget(tmp_path) -> None:
    candidates = [
        PromotionCandidate(
            candidate_id=f"packet-1-candidate-{index}",
            packet_id="packet-1",
            kind="concept_update",
            target_page="Agent Context Substrate",
            reason="Durable claim worth integrating.",
            evidence=[f"claim:packet-1-claim-{index}", "packet:packet-1#micro-1", "message:2"],
            proposed_change=(
                "Agent Context Substrate should preserve enough wiki write judge material "
                "for a real decision. "
                + ("evidence-backed detail " * 24)
            ),
            proposed_action="update_existing",
            confidence=0.91,
            status="pending",
        )
        for index in range(1, 6)
    ]
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=candidates,
        wiki_root=tmp_path / "wiki",
        write_mode="flexible",
    )

    request = _build_wiki_write_judge_request(
        packet_id="packet-1",
        candidates=candidates,
        proposal=proposal,
        routing_hints={"codex_timeout_seconds": 90},
        min_score=0.85,
    )
    prepared = _prepare_llm_request(request, safety=LLMInputSafetyOptions())

    assert prepared.get("llm_input_truncated") is not True
    assert len(prepared["candidates"]) == 5
    assert len(prepared["proposal"]["operations"]) == 1
    assert prepared["proposal"]["operations"][0]["candidate_ids"] == [
        f"packet-1-candidate-{index}" for index in range(1, 6)
    ]
    assert prepared["proposal"]["operations"][0]["diff"]["compacted"] is True


def test_wiki_write_judge_request_omits_pre_judge_policy_verdict(tmp_path) -> None:
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=[_candidate()],
        wiki_root=tmp_path / "wiki",
        write_mode="flexible",
    )

    request = _build_wiki_write_judge_request(
        packet_id="packet-1",
        candidates=[_candidate()],
        proposal=proposal,
        routing_hints={},
        min_score=0.85,
    )

    metadata = request["proposal"].get("metadata", {})
    assert "policy_verdict" not in metadata
    assert "judge_verdict" not in metadata
    assert "review_needed frontmatter" in request["evaluation_contract"]["instruction"]
    assert "not by itself as an auto-apply blocker" in request["evaluation_contract"]["instruction"]


def test_wiki_write_judge_request_compacts_long_evidence_refs_before_llm_bound(tmp_path) -> None:
    long_source_ref = "hermes-session:packet-1#messages=" + ",".join(str(index) for index in range(1, 750))
    candidates = [
        PromotionCandidate(
            candidate_id=f"packet-1-candidate-{index}",
            packet_id="packet-1",
            kind="wiki_update",
            target_page="context-packet",
            reason="Durable ACS installation/runtime observation worth integrating.",
            evidence=[f"claim:packet-1-claim-{index}", "packet:packet-1#micro-1", long_source_ref],
            proposed_change=(
                "ACS Codex integration should keep wiki write judge candidates and operations visible "
                "even when provenance references are large."
            ),
            proposed_action="update_existing",
            confidence=0.91,
            status="pending",
            category="acs-runtime-observation",
            page_type="knowledge",
        )
        for index in range(1, 5)
    ]
    proposal = plan_wiki_patch_proposal(
        packet_id="packet-1",
        candidates=candidates,
        wiki_root=tmp_path / "wiki",
        write_mode="flexible",
    )

    request = _build_wiki_write_judge_request(
        packet_id="packet-1",
        candidates=candidates,
        proposal=proposal,
        routing_hints={"codex_timeout_seconds": 90},
        min_score=0.85,
    )
    prepared = _prepare_llm_request(request, safety=LLMInputSafetyOptions())

    assert prepared.get("llm_input_truncated") is not True
    assert len(json.dumps(prepared, ensure_ascii=False, sort_keys=True)) <= 12_000
    assert len(prepared["candidates"]) == 4
    assert prepared["proposal"]["operations"][0]["candidate_ids"] == [
        f"packet-1-candidate-{index}" for index in range(1, 5)
    ]
    assert prepared["proposal"]["operations"][0]["target"] == "context-packet.md"
