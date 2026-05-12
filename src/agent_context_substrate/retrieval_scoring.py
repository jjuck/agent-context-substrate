from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar
import re


class _RankableHit(Protocol):
    source_type: str
    score: float
    title: str
    hit_id: str


T = TypeVar("T", bound=_RankableHit)


def tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[\w가-힣.-]+", query.lower())
    return [token for token in tokens if len(token) > 1]


def score_text(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for term in terms:
        count = lower.count(term)
        if count:
            score += 1.0 + min(count - 1, 3) * 0.25
    if terms and all(term in lower for term in terms):
        score += 2.0
    return score


def make_snippet(text: str, terms: list[str], radius: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    lower = compact.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if not positions:
        return compact[: radius * 2]
    center = min(positions)
    start = max(0, center - radius)
    end = min(len(compact), center + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def source_rank(source_type: str) -> int:
    return {
        "recovery_brief": 0,
        "recovery_packet": 1,
        "wiki": 2,
        "packet": 3,
        "unit_summary": 4,
        "micro_summary": 5,
        "topic_map_node": 6,
        "topic_map_edge": 7,
        "topic_map_path": 8,
        "promotion_candidate": 9,
        "wiki_patch": 10,
        "applied_patch": 11,
        "raw_message": 12,
    }.get(source_type, 99)


def rank_hits(hits: Iterable[T], *, source_priority_first: bool = False) -> list[T]:
    if source_priority_first:
        return sorted(hits, key=lambda hit: (source_rank(hit.source_type), -hit.score, hit.title, hit.hit_id))
    return sorted(hits, key=lambda hit: (-hit.score, source_rank(hit.source_type), hit.title, hit.hit_id))
