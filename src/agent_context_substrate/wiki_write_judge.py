from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json
import subprocess

from .promotions import PromotionCandidate
from .safe_paths import safe_artifact_stem, safe_child_path
from .summarizer_backends import (
    AgentLLMRouter,
    LLMInputSafetyOptions,
    _call_router_with_json_repair,
    _codex_exec_env,
    _detect_codex_cli_command,
    _parse_json_text_object,
    _prepare_llm_request,
)
from .wiki_patches import WikiPatchProposal


WIKI_WRITE_JUDGE_SCHEMA_VERSION = "wiki_write_judge_v1"
WIKI_WRITE_DECISIONS = {"skip", "propose_only", "apply_managed", "apply_flexible", "review_required"}
WIKI_WRITE_ISSUE_SEVERITIES = {"info", "warning", "error"}
WIKI_WRITE_JUDGE_MODES = {"off", "hybrid", "auto", "codex-cli"}
WIKI_AUTO_MODES = {"off", "propose", "apply-managed", "apply-flexible"}
_JUDGE_DIFF_EXCERPT_CHARS = 150
_JUDGE_DIFF_TRUNCATION_MARKER = "...<TRUNCATED_DIFF_EXCERPT>"
_JUDGE_TEXT_FIELD_CHARS = 700
_JUDGE_RATIONALE_CHARS = 900
_JUDGE_EVIDENCE_ITEMS = 8
_JUDGE_EVIDENCE_REF_CHARS = 180
_JUDGE_TEXT_TRUNCATION_MARKER = "...<TRUNCATED_FOR_JUDGE>"


@dataclass(frozen=True)
class WikiWriteIssue:
    code: str
    severity: str
    field: str
    message: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiWriteIssue":
        if not isinstance(payload, dict):
            raise ValueError("wiki write judge issue must be an object")
        code = str(payload.get("code") or "").strip()
        message = str(payload.get("message") or "").strip()
        if not code:
            raise ValueError("wiki write judge issue code must be non-empty")
        if not message:
            raise ValueError("wiki write judge issue message must be non-empty")
        severity = str(payload.get("severity") or "warning")
        if severity not in WIKI_WRITE_ISSUE_SEVERITIES:
            severity = "warning"
        evidence_refs = payload.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            raise ValueError("wiki write judge issue evidence_refs must be a list")
        if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
            raise ValueError("wiki write judge issue evidence_refs must contain non-empty strings")
        return cls(
            code=code,
            severity=severity,
            field=str(payload.get("field") or ""),
            message=message,
            evidence_refs=list(evidence_refs),
        )


@dataclass(frozen=True)
class WikiWriteDecision:
    ok: bool
    score: float
    decision: str
    candidate_ids: list[str]
    issues: list[WikiWriteIssue]
    rationale: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        metadata = dict(self.metadata)
        metadata.setdefault("schema_version", WIKI_WRITE_JUDGE_SCHEMA_VERSION)
        return {
            "ok": self.ok,
            "score": self.score,
            "decision": self.decision,
            "candidate_ids": list(self.candidate_ids),
            "issues": [issue.to_dict() for issue in self.issues],
            "rationale": self.rationale,
            "metadata": metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WikiWriteDecision":
        decision = str(payload["decision"])
        if decision not in WIKI_WRITE_DECISIONS:
            raise ValueError(f"Unsupported wiki write judge decision: {decision}")
        ok = _coerce_bool(payload.get("ok"), default=decision in {"apply_managed", "apply_flexible", "propose_only"})
        raw_candidate_ids = payload.get("candidate_ids", [])
        if not isinstance(raw_candidate_ids, list):
            raise ValueError("wiki write judge candidate_ids must be a list")
        raw_issues = payload.get("issues", [])
        if not isinstance(raw_issues, list):
            raise ValueError("wiki write judge issues must be a list")
        issues = [WikiWriteIssue.from_dict(item) for item in raw_issues]
        if ok and decision in {"review_required", "skip"}:
            ok = False
        if ok and any(issue.severity == "error" for issue in issues):
            raise ValueError("wiki write judge approved decision cannot include error issues")
        rationale = str(payload.get("rationale") or "").strip()
        if not rationale:
            raise ValueError("wiki write judge rationale must be non-empty")
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("schema_version", WIKI_WRITE_JUDGE_SCHEMA_VERSION)
        return cls(
            ok=ok,
            score=_coerce_score(payload["score"]),
            decision=decision,
            candidate_ids=[str(candidate_id) for candidate_id in raw_candidate_ids],
            issues=issues,
            rationale=rationale,
            metadata=metadata,
        )

    def approved_for_auto_apply(self, wiki_auto_mode: str) -> bool:
        normalized = normalize_wiki_auto_mode(wiki_auto_mode)
        if not self.ok:
            return False
        if normalized == "apply-flexible":
            return self.decision == "apply_flexible"
        if normalized == "apply-managed":
            return self.decision == "apply_managed"
        return False


class CodexCliWikiWriteJudgeRouter:
    def __init__(
        self,
        *,
        codex_command: str | None = None,
        project_root: Path | str,
        timeout_seconds: int = 90,
        routing_hints: dict[str, object] | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
    ) -> None:
        self.codex_command = codex_command
        self.project_root = Path(project_root)
        self.timeout_seconds = timeout_seconds
        self.routing_hints = dict(routing_hints or {})
        self.llm_safety = llm_safety or LLMInputSafetyOptions()

    def __call__(self, request: dict[str, object]) -> dict[str, object]:
        codex_command = self.codex_command or _detect_codex_cli_command()
        if not codex_command:
            raise RuntimeError("codex-cli wiki write judge unavailable: codex command was not found")
        prepared_request = _prepare_llm_request(request, safety=self.llm_safety)
        request_json = json.dumps(prepared_request, ensure_ascii=False, sort_keys=True)
        with TemporaryDirectory(prefix=".acs-codex-wiki-judge-", dir=self.project_root) as temp_dir:
            schema_path = Path(temp_dir) / "wiki-write-judge-schema.json"
            schema_path.write_text(json.dumps(_wiki_write_decision_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
            command = [
                codex_command,
                "exec",
                "-C",
                str(self.project_root),
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-c",
                "approval_policy=never",
                "-c",
                "service_tier=fast",
                "-c",
                "model_reasoning_effort=low",
                "-c",
                "features.hooks=false",
                "--json",
                "--output-schema",
                str(schema_path),
            ]
            model = self.routing_hints.get("model")
            if model:
                command.extend(["--model", str(model)])
            command.append(_wiki_write_prompt(request_json=request_json))
            result = subprocess.run(
                command,
                cwd=str(self.project_root),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                env=_codex_exec_env(),
            )
        if result.returncode != 0:
            raise RuntimeError(f"codex-cli wiki write judge failed with exit_code={result.returncode}: {result.stderr.strip()}")
        return _parse_codex_exec_json_payload(result.stdout)


def normalize_wiki_auto_mode(mode: str | None) -> str:
    normalized = (mode or "off").strip().lower()
    if normalized not in WIKI_AUTO_MODES:
        raise ValueError(f"Unsupported wiki_auto_mode={mode!r}; expected one of {sorted(WIKI_AUTO_MODES)}")
    return normalized


def normalize_wiki_write_judge_mode(mode: str | None) -> str:
    normalized = (mode or "off").strip().lower()
    if normalized not in WIKI_WRITE_JUDGE_MODES:
        raise ValueError(f"Unsupported wiki_write_judge_mode={mode!r}; expected one of {sorted(WIKI_WRITE_JUDGE_MODES)}")
    return normalized


def evaluate_wiki_write_with_judge(
    *,
    packet_id: str,
    candidates: list[PromotionCandidate],
    proposal: WikiPatchProposal,
    mode: str = "off",
    router: AgentLLMRouter | None = None,
    routing_hints: dict[str, object] | None = None,
    min_score: float = 0.85,
    llm_safety: LLMInputSafetyOptions | None = None,
) -> WikiWriteDecision:
    normalized_mode = normalize_wiki_write_judge_mode(mode)
    if not candidates or not proposal.operations:
        return _skip_decision(reason="No pending promotion candidates produced wiki patch operations.")
    if normalized_mode == "off":
        return _review_required_decision(
            code="judge_disabled",
            message="Wiki write judge is disabled; keeping proposal for review.",
            metadata={"judge_mode": "off"},
        )
    if router is None and normalized_mode in {"auto", "codex-cli"}:
        hints = dict(routing_hints or {})
        router = CodexCliWikiWriteJudgeRouter(
            codex_command=str(hints["codex_cli_command"]) if hints.get("codex_cli_command") else None,
            project_root=Path(str(hints.get("codex_project_root") or Path.cwd())),
            timeout_seconds=_positive_int_hint(hints, "codex_timeout_seconds", default=90),
            routing_hints=hints,
            llm_safety=llm_safety or LLMInputSafetyOptions(),
        )
    if router is None:
        return _review_required_decision(
            code="judge_unavailable",
            message="Wiki write judge router was not provided; automatic Wiki writes require an LLM verdict.",
            metadata={"judge_mode": "degraded" if normalized_mode == "hybrid" else normalized_mode},
        )
    request = _build_wiki_write_judge_request(
        packet_id=packet_id,
        candidates=candidates,
        proposal=proposal,
        routing_hints=dict(routing_hints or {}),
        min_score=min_score,
    )
    try:
        payload = _call_router_with_json_repair(
            router=router,
            request=request,
            safety=llm_safety or LLMInputSafetyOptions(),
            error_label="Wiki write judge router",
        )
        return _enforce_min_score(
            decision=WikiWriteDecision.from_dict(payload),
            min_score=min_score,
            mode=normalized_mode,
        )
    except Exception as exc:
        return _review_required_decision(
            code="judge_unavailable",
            message=f"Wiki write judge router failed; keeping proposal for review: {type(exc).__name__}",
            metadata={"judge_mode": "degraded", "schema_version": WIKI_WRITE_JUDGE_SCHEMA_VERSION},
        )


def export_wiki_write_decision(*, packet_id: str, decision: WikiWriteDecision, project_root: Path | str) -> Path:
    safe_packet_id = safe_artifact_stem(packet_id, label="packet id")
    output_dir = Path(project_root) / "data" / "wiki_decisions"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = safe_child_path(output_dir, safe_packet_id, ".json", label="wiki write decision id")
    output_path.write_text(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _build_wiki_write_judge_request(
    *,
    packet_id: str,
    candidates: list[PromotionCandidate],
    proposal: WikiPatchProposal,
    routing_hints: dict[str, object],
    min_score: float,
) -> dict[str, object]:
    return {
        "kind": "wiki-write-judge",
        "schema_version": WIKI_WRITE_JUDGE_SCHEMA_VERSION,
        "packet_id": packet_id,
        "evaluation_contract": {
            "decisions": sorted(WIKI_WRITE_DECISIONS),
            "instruction": (
                "Decide whether this packet should be written into the human-facing LLM Wiki. "
                "Prefer apply_flexible for durable, evidence-backed knowledge that improves the living knowledge graph. "
                "Use review_required for privacy risk, weak evidence, volatile notes, unsafe targets, or uncertain fit. "
                "Treat review_needed frontmatter as a follow-up signal, not by itself as an auto-apply blocker. "
                "Return strict JSON only and do not rewrite patch diffs."
            ),
            "min_score_for_auto_apply": min_score,
        },
        "candidates": [_compact_candidate_for_judge(candidate) for candidate in candidates],
        "proposal": _compact_proposal_for_judge(proposal),
        "routing_hints": dict(routing_hints),
    }


def _compact_candidate_for_judge(candidate: PromotionCandidate) -> dict[str, object]:
    payload = candidate.to_dict()
    compact: dict[str, object] = {}
    for key in (
        "candidate_id",
        "packet_id",
        "kind",
        "target_page",
        "proposed_action",
        "confidence",
        "status",
        "category",
        "language",
        "page_type",
        "placement_reason",
    ):
        if key in payload:
            compact[key] = payload[key]
    compact["reason"] = _compact_text_for_judge(str(payload.get("reason") or ""), max_chars=_JUDGE_TEXT_FIELD_CHARS)
    compact["proposed_change"] = _compact_text_for_judge(
        str(payload.get("proposed_change") or ""),
        max_chars=_JUDGE_TEXT_FIELD_CHARS,
    )
    compact["evidence"] = _compact_evidence_refs_for_judge(payload.get("evidence", []))
    return compact


def _compact_proposal_for_judge(proposal: WikiPatchProposal) -> dict[str, object]:
    payload = proposal.to_dict()
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        payload["metadata"] = {
            key: value
            for key, value in metadata.items()
            if key not in {"judge_verdict", "policy_verdict"}
        }
    compact_operations: list[object] = []
    for operation in payload.get("operations", []):
        if not isinstance(operation, dict):
            compact_operations.append(operation)
            continue
        compact_operation: dict[str, object] = {
            "patch_id": operation.get("patch_id"),
            "candidate_id": operation.get("candidate_id"),
            "candidate_ids": operation.get("candidate_ids") or [operation.get("candidate_id")],
            "target": operation.get("target"),
            "operation": operation.get("operation"),
            "risk": operation.get("risk"),
            "status": operation.get("status"),
            "rationale": _compact_text_for_judge(
                str(operation.get("rationale") or ""),
                max_chars=_JUDGE_RATIONALE_CHARS,
            ),
            "evidence": _compact_evidence_refs_for_judge(operation.get("evidence", [])),
        }
        metadata = operation.get("metadata")
        if isinstance(metadata, dict):
            compact_operation["metadata"] = metadata
        diff = operation.get("diff")
        if isinstance(diff, dict):
            compact_operation["diff"] = _compact_diff_for_judge(diff)
        compact_operations.append(compact_operation)
    payload["operations"] = compact_operations
    return payload


def _compact_diff_for_judge(diff: dict[str, object]) -> dict[str, object]:
    before = str(diff.get("before") or "")
    after = str(diff.get("after") or "")
    return {
        "base_sha256": str(diff.get("base_sha256") or ""),
        "before_chars": len(before),
        "after_chars": len(after),
        "before_excerpt": _diff_excerpt(before),
        "after_excerpt": _diff_excerpt(after),
        "compacted": True,
    }


def _diff_excerpt(text: str) -> str:
    if len(text) <= _JUDGE_DIFF_EXCERPT_CHARS:
        return text
    keep = max(0, _JUDGE_DIFF_EXCERPT_CHARS - len(_JUDGE_DIFF_TRUNCATION_MARKER))
    return text[:keep] + _JUDGE_DIFF_TRUNCATION_MARKER


def _compact_evidence_refs_for_judge(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    compacted = [_compact_text_for_judge(str(item), max_chars=_JUDGE_EVIDENCE_REF_CHARS) for item in value[:_JUDGE_EVIDENCE_ITEMS]]
    remaining = len(value) - len(compacted)
    if remaining > 0:
        compacted.append(f"...<{remaining}_MORE_EVIDENCE_REFS>")
    return compacted


def _compact_text_for_judge(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(_JUDGE_TEXT_TRUNCATION_MARKER))
    return text[:keep] + _JUDGE_TEXT_TRUNCATION_MARKER


def _enforce_min_score(*, decision: WikiWriteDecision, min_score: float, mode: str) -> WikiWriteDecision:
    if decision.decision not in {"apply_managed", "apply_flexible"} or decision.score >= min_score:
        metadata = dict(decision.metadata)
        metadata.setdefault("judge_mode", mode)
        metadata.setdefault("min_score", min_score)
        return WikiWriteDecision(
            ok=decision.ok,
            score=decision.score,
            decision=decision.decision,
            candidate_ids=list(decision.candidate_ids),
            issues=list(decision.issues),
            rationale=decision.rationale,
            metadata=metadata,
        )
    return WikiWriteDecision(
        ok=False,
        score=decision.score,
        decision="review_required",
        candidate_ids=list(decision.candidate_ids),
        issues=[
            *decision.issues,
            WikiWriteIssue(
                code="below_auto_apply_threshold",
                severity="warning",
                field="score",
                message=f"Wiki write judge score {decision.score} is below the auto-apply threshold {min_score}.",
            ),
        ],
        rationale=decision.rationale,
        metadata={**dict(decision.metadata), "judge_mode": mode, "min_score": min_score},
    )


def _skip_decision(*, reason: str) -> WikiWriteDecision:
    return WikiWriteDecision(
        ok=False,
        score=1.0,
        decision="skip",
        candidate_ids=[],
        issues=[],
        rationale=reason,
        metadata={"judge_mode": "mechanical", "schema_version": WIKI_WRITE_JUDGE_SCHEMA_VERSION},
    )


def _review_required_decision(*, code: str, message: str, metadata: dict[str, object]) -> WikiWriteDecision:
    return WikiWriteDecision(
        ok=False,
        score=0.0,
        decision="review_required",
        candidate_ids=[],
        issues=[
            WikiWriteIssue(
                code=code,
                severity="warning",
                field="judge",
                message=message,
            )
        ],
        rationale=message,
        metadata={**metadata, "schema_version": WIKI_WRITE_JUDGE_SCHEMA_VERSION},
    )


def _coerce_bool(value: object, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"wiki write judge score must be numeric, got {value!r}")
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"wiki write judge score must be between 0.0 and 1.0, got {score}")
    return score


def _positive_int_hint(hints: dict[str, object], key: str, *, default: int) -> int:
    try:
        value = int(hints.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_codex_exec_json_payload(stdout: str) -> dict[str, object]:
    stripped = stdout.strip()
    if not stripped:
        raise ValueError("codex-cli wiki write judge returned empty stdout")
    try:
        return _parse_json_text_object(stripped)
    except (ValueError, json.JSONDecodeError):
        pass
    last_agent_text: str | None = None
    for line in stripped.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            last_agent_text = str(item["text"])
        elif event.get("type") == "agent_message" and isinstance(event.get("text"), str):
            last_agent_text = str(event["text"])
    if last_agent_text is None:
        raise ValueError("codex-cli wiki write judge JSONL output did not include an agent_message item")
    return _parse_json_text_object(last_agent_text)


def _wiki_write_prompt(*, request_json: str) -> str:
    return (
        "Use this Agent Context Substrate wiki write decision input JSON: "
        f"{request_json}\n\nReturn only one strict JSON object. Decide whether to write the proposed knowledge "
        "into the LLM Wiki. Use only provided candidates, operations, and evidence. Do not invent claims, "
        "do not include markdown fences, and do not rewrite the proposed diff."
    )


def _wiki_write_decision_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ok": {"type": "boolean"},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "decision": {"type": "string", "enum": sorted(WIKI_WRITE_DECISIONS)},
            "candidate_ids": {"type": "array", "items": {"type": "string"}},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {"type": "string", "enum": sorted(WIKI_WRITE_ISSUE_SEVERITIES)},
                        "field": {"type": "string"},
                        "message": {"type": "string"},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["code", "severity", "field", "message", "evidence_refs"],
                },
            },
            "rationale": {"type": "string"},
            "metadata": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
        "required": ["ok", "score", "decision", "candidate_ids", "issues", "rationale", "metadata"],
    }
