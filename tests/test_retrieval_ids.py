from __future__ import annotations

import pytest

from agent_context_substrate.retrieval_ids import decode_hit_id, encode_hit_id


def test_retrieval_hit_id_round_trips_sorted_json_payload() -> None:
    payload = {
        "source_type": "wiki",
        "source_path": "01 지식/검색.md",
        "title": "검색",
        "provenance": ["wiki:01 지식/검색.md"],
    }

    hit_id = encode_hit_id(payload)

    assert decode_hit_id(hit_id) == payload
    assert "=" not in hit_id


def test_decode_hit_id_rejects_non_object_payload() -> None:
    hit_id = encode_hit_id(["not", "an", "object"])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid retrieval hit id"):
        decode_hit_id(hit_id)


def test_decode_hit_id_rejects_malformed_base64() -> None:
    with pytest.raises(ValueError, match="Invalid retrieval hit id"):
        decode_hit_id("not a hit id")
