from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalHit:
    hit_id: str
    source_type: str
    source_path: str
    title: str
    snippet: str
    score: float
    provenance: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "hit_id": self.hit_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class RetrievalHitDetail:
    hit: RetrievalHit
    content: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "hit": self.hit.to_dict(),
            "content": self.content,
            "metadata": dict(self.metadata),
        }
