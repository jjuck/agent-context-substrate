from agent_context_substrate.retrieval_types import RetrievalHit, RetrievalHitDetail


def test_retrieval_hit_round_trips_to_dict_without_mutating_provenance():
    provenance = ["wiki:page.md"]
    hit = RetrievalHit(
        hit_id="hit-1",
        source_type="wiki",
        source_path="page.md",
        title="Page",
        snippet="snippet",
        score=2.5,
        provenance=provenance,
    )

    payload = hit.to_dict()
    provenance.append("later")

    assert payload == {
        "hit_id": "hit-1",
        "source_type": "wiki",
        "source_path": "page.md",
        "title": "Page",
        "snippet": "snippet",
        "score": 2.5,
        "provenance": ["wiki:page.md"],
    }


def test_retrieval_hit_detail_to_dict_contains_hit_content_and_metadata_copy():
    hit = RetrievalHit(
        hit_id="hit-1",
        source_type="packet",
        source_path="data/exports/context_packets/packet.json",
        title="Packet",
        snippet="packet snippet",
        score=1.0,
        provenance=["packet:packet-1"],
    )
    metadata = {"packet_id": "packet-1"}
    detail = RetrievalHitDetail(hit=hit, content="full content", metadata=metadata)

    payload = detail.to_dict()
    metadata["extra"] = "later"

    assert payload["hit"] == hit.to_dict()
    assert payload["content"] == "full content"
    assert payload["metadata"] == {"packet_id": "packet-1"}
