from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SessionMessage:
    """Typed boundary for one raw agent conversation message."""

    id: int
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SessionMessage":
        metadata = {
            str(key): value
            for key, value in payload.items()
            if key not in {"id", "role", "content"}
        }
        return cls(
            id=int(payload["id"]),
            role=str(payload.get("role") or ""),
            content=str(payload.get("content") or ""),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            **dict(self.metadata),
        }


@dataclass(frozen=True)
class SessionBundle:
    """Typed core representation of a session slice.

    Dict conversion remains explicit so raw Hermes/state.db shapes stay at
    adapter and artifact boundaries.
    """

    session_id: str
    messages: list[SessionMessage]
    source: str = "unknown"
    title: str | None = None
    started_at: Any | None = None
    ended_at: Any | None = None
    slice_start_message_id: int | None = None
    slice_end_message_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw_bundle(cls, raw_bundle: Mapping[str, Any]) -> "SessionBundle":
        session = raw_bundle.get("session")
        if not isinstance(session, Mapping):
            raise ValueError("raw session bundle must include a session object")
        raw_messages = raw_bundle.get("messages", [])
        if not isinstance(raw_messages, list):
            raise ValueError("raw session bundle messages must be a list")
        slice_payload = raw_bundle.get("slice", {})
        if not isinstance(slice_payload, Mapping):
            slice_payload = {}
        session_metadata = {
            str(key): value
            for key, value in session.items()
            if key not in {"id", "source", "title", "started_at", "ended_at"}
        }
        return cls(
            session_id=str(session["id"]),
            source=str(session.get("source") or "unknown"),
            title=(str(session.get("title")) if session.get("title") is not None else None),
            started_at=session.get("started_at"),
            ended_at=session.get("ended_at"),
            messages=[SessionMessage.from_dict(message) for message in raw_messages],
            slice_start_message_id=_optional_int(slice_payload.get("start_message_id")),
            slice_end_message_id=_optional_int(slice_payload.get("end_message_id")),
            metadata=session_metadata,
        )

    def to_raw_bundle(self) -> dict[str, Any]:
        session = {
            "id": self.session_id,
            "source": self.source,
            **dict(self.metadata),
        }
        if self.title is not None:
            session["title"] = self.title
        if self.started_at is not None:
            session["started_at"] = self.started_at
        if self.ended_at is not None:
            session["ended_at"] = self.ended_at
        return {
            "session": session,
            "messages": [message.to_dict() for message in self.messages],
            "slice": {
                "start_message_id": self.slice_start_message_id,
                "end_message_id": self.slice_end_message_id,
            },
            "message_count": len(self.messages),
        }


def ensure_session_bundle(raw_bundle: Mapping[str, Any] | SessionBundle) -> SessionBundle:
    if isinstance(raw_bundle, SessionBundle):
        return raw_bundle
    return SessionBundle.from_raw_bundle(raw_bundle)


def resolve_session_bundle(
    raw_bundle: Mapping[str, Any] | SessionBundle | None = None,
    *,
    session_bundle: Mapping[str, Any] | SessionBundle | None = None,
) -> SessionBundle:
    """Resolve legacy raw-bundle and preferred typed-session keyword inputs."""

    if raw_bundle is None and session_bundle is None:
        raise TypeError("session_bundle is required")
    if raw_bundle is not None and session_bundle is not None:
        raise TypeError("pass either session_bundle or raw_bundle, not both")
    return ensure_session_bundle(session_bundle if session_bundle is not None else raw_bundle)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
