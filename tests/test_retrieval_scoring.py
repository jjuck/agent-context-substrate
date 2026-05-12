from types import SimpleNamespace

import pytest

from agent_context_substrate.retrieval_scoring import (
    make_snippet,
    rank_hits,
    score_text,
    source_rank,
    tokenize_query,
)


def test_tokenize_query_keeps_korean_words_and_drops_single_character_tokens():
    assert tokenize_query("A 그래프 retrieval.py b") == ["그래프", "retrieval.py"]


def test_score_text_weights_repeated_terms_and_all_terms_bonus():
    score = score_text("alpha alpha beta", ["alpha", "beta"])

    assert score == pytest.approx(4.25)


def test_make_snippet_centers_first_matching_term_and_compacts_whitespace():
    snippet = make_snippet("intro\n" + "x" * 20 + " target " + "y" * 20, ["target"], radius=8)

    assert snippet.startswith("...")
    assert snippet.endswith("...")
    assert "target" in snippet
    assert "\n" not in snippet


def test_rank_hits_orders_by_score_then_source_rank_title_and_hit_id():
    hits = [
        SimpleNamespace(source_type="raw_message", score=10.0, title="z", hit_id="3"),
        SimpleNamespace(source_type="wiki", score=10.0, title="b", hit_id="2"),
        SimpleNamespace(source_type="packet", score=11.0, title="a", hit_id="1"),
    ]

    ranked = rank_hits(hits)

    assert [hit.hit_id for hit in ranked] == ["1", "2", "3"]


def test_rank_hits_can_prioritize_recovery_source_order_before_score():
    hits = [
        SimpleNamespace(source_type="recovery_packet", score=99.0, title="packet", hit_id="2"),
        SimpleNamespace(source_type="recovery_brief", score=1.0, title="brief", hit_id="1"),
    ]

    ranked = rank_hits(hits, source_priority_first=True)

    assert [hit.hit_id for hit in ranked] == ["1", "2"]
    assert source_rank("unknown") == 99
