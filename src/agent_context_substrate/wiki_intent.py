from __future__ import annotations

from dataclasses import dataclass
import re

from .atoms import ClaimAtom


_GENERIC_SUBJECTS = {
    "context packet",
    "packet",
    "session",
    "thread",
    "conversation",
    "micro summary",
    "unit summary",
    "summary",
}
_HANGUL_PATTERN = re.compile(r"[\uac00-\ud7a3]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class WikiPageIntent:
    """A soft semantic intent; placement policy decides its physical path."""

    target_page: str
    category: str | None = None
    language: str | None = None
    page_type: str | None = None
    placement_reason: str | None = None

    @classmethod
    def from_claim(cls, claim: ClaimAtom) -> "WikiPageIntent":
        target_page = _semantic_subject(claim.subjects)
        return cls(
            target_page=target_page,
            language=_infer_language(" ".join([claim.text, *claim.subjects])),
            page_type=_broad_page_type(claim.type),
        )


def _semantic_subject(subjects: list[str]) -> str:
    for subject in subjects:
        if _normalize_subject(subject) not in _GENERIC_SUBJECTS:
            return subject.strip()
    return ""


def _normalize_subject(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _infer_language(text: str) -> str | None:
    if _HANGUL_PATTERN.search(text):
        return "ko"
    if _LATIN_PATTERN.search(text):
        return "en"
    return None


def _broad_page_type(claim_type: str) -> str | None:
    normalized = _normalize_subject(claim_type)
    return normalized if normalized in {"decision", "practice", "question", "project", "source"} else None
