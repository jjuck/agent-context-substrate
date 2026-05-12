from __future__ import annotations

import json

import pytest

from agent_context_substrate.retrieval_sources import (
    iter_jsonl_objects,
    json_search_text,
    load_json_list,
    load_json_object,
    load_jsonl_record,
    read_text_lossy,
)


def test_retrieval_json_source_loaders_return_expected_shapes(tmp_path) -> None:
    object_path = tmp_path / "object.json"
    object_path.write_text('{"b": 2, "a": "alpha"}', encoding="utf-8")
    list_path = tmp_path / "list.json"
    list_path.write_text('[{"id": "one"}, {"id": "two"}]', encoding="utf-8")
    scalar_path = tmp_path / "scalar.json"
    scalar_path.write_text('"not an object"', encoding="utf-8")
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{', encoding="utf-8")

    assert load_json_object(object_path) == {"b": 2, "a": "alpha"}
    assert load_json_list(list_path) == [{"id": "one"}, {"id": "two"}]
    assert load_json_object(scalar_path) is None
    assert load_json_list(object_path) is None
    assert load_json_object(invalid_path) is None
    assert load_json_list(invalid_path) is None
    assert json_search_text({"b": 2, "a": "alpha"}) == '{"a": "alpha", "b": 2}'


def test_retrieval_jsonl_source_loader_skips_invalid_lines_and_expands_specific_records(tmp_path) -> None:
    path = tmp_path / "applied.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"patch_id": "p1"}),
                "not-json",
                json.dumps(["not", "object"]),
                json.dumps({"patch_id": "p2"}),
            ]
        ),
        encoding="utf-8",
    )

    assert list(iter_jsonl_objects(path)) == [(0, {"patch_id": "p1"}), (3, {"patch_id": "p2"})]
    assert load_jsonl_record(path, 3) == {"patch_id": "p2"}

    with pytest.raises(KeyError):
        load_jsonl_record(path, -1)
    with pytest.raises(KeyError):
        load_jsonl_record(path, 99)
    with pytest.raises(ValueError):
        load_jsonl_record(path, 2)


def test_read_text_lossy_falls_back_for_invalid_utf8(tmp_path) -> None:
    path = tmp_path / "note.md"
    path.write_bytes(b"valid\xff text")

    assert read_text_lossy(path) == "valid text"
