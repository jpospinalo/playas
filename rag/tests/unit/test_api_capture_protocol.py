"""Pure protocol contracts; no clients, runtime imports, files or services."""

from __future__ import annotations

import copy
import json

import pytest
from evaluation.api_capture_protocol import (
    ProtocolError,
    SSECapture,
    decode_json,
    normalize_payload,
)


def payload() -> dict:
    return {
        "answer": "La decisión mantiene el término [DOC3].\nRazón: protección marítima.",
        "query_route": "in_scope",
        "enriched_query": "consulta marítima autónoma",
        "context_tokens": 19,
        "context_limit": 2048,
        "sources": [
            {
                "source": "fallo-a.jsonl",
                "title": "Decisión A",
                "doc_type": "jurisprudencia",
                "metadata": {"summary": "Resumen A", "nested": {"labels": ["á", 3]}},
                "public_extension": ["conservar"],
                "fragments": [
                    {
                        "index": 3,
                        "content": "Tercero. Inicio después de notificación.\nTexto íntegro.",
                        "metadata": {"id": "a-3", "chunk_id": "chunk-a-3", "section": "resuelve"},
                        "public_extension": {"keep": True},
                    },
                    {"index": 1, "content": "Primero.\nNo truncar este cuerpo.", "metadata": {}},
                ],
            },
            {
                "source": "fallo-b.jsonl",
                "title": "Decisión B",
                "doc_type": None,
                "metadata": {"keywords": ["costa", "término"]},
                "fragments": [
                    {"index": 2, "content": "Segundo. Responsable expreso.", "metadata": {"id": 42}}
                ],
            },
        ],
    }


def frame(value: dict | list | str, newline: str = "\n") -> bytes:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return ("data: " + text + newline + newline).encode("utf-8")


def stream_for(body: dict, newline: str = "\n") -> bytes:
    answer = body["answer"]
    sources = {key: value for key, value in body.items() if key != "answer"}
    return b"".join(
        [
            frame({"type": "status", "stage": "generate", "message": "Preparación"}, newline),
            frame({"type": "token", "content": answer[:24]}, newline),
            frame({"type": "token", "content": answer[24:]}, newline),
            frame({"type": "sources", **sources}, newline),
            frame("[DONE]", newline),
        ]
    )


def decode_stream(raw: bytes, chunk_size: int = 1, **limits: int) -> dict:
    capture = SSECapture(**limits)
    for start in range(0, len(raw), chunk_size):
        capture.feed(raw[start : start + chunk_size])
    return capture.finish()


def test_json_preserves_public_fields_and_global_fragment_order_without_mutation() -> None:
    body = payload()
    original = copy.deepcopy(body)
    result = decode_json(json.dumps(body, ensure_ascii=False).encode())
    assert result["answer"] == original["answer"]
    assert result["source_groups"] == original["sources"]
    assert [fragment["index"] for fragment in result["ordered_fragments"]] == [1, 2, 3]
    assert [fragment["content"] for fragment in result["ordered_fragments"]] == [
        original["sources"][0]["fragments"][1]["content"],
        original["sources"][1]["fragments"][0]["content"],
        original["sources"][0]["fragments"][0]["content"],
    ]
    assert result["ordered_fragments"][2]["group_metadata"] == original["sources"][0]["metadata"]
    assert result["ordered_fragments"][2]["chunk_id"] == "chunk-a-3"
    assert result["ordered_fragments"][1]["metadata_id"] is None
    assert result["ordered_fragments"][1]["fragment_metadata"]["id"] == 42
    assert body == original
    result["source_groups"][0]["metadata"]["nested"]["labels"].append("new")
    assert body == original


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("chunk_size", [1, 7, 65536])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_json_sse_equivalence_with_fragmented_utf8_and_line_endings(
    newline: str, chunk_size: int, bom: bytes
) -> None:
    body = payload()
    expected = normalize_payload(body)
    actual = decode_stream(bom + stream_for(body, newline), chunk_size)
    assert {key: actual[key] for key in expected} == expected
    assert actual["sse_done"] is True
    assert actual["sse_event_count"] == 5
    assert actual["sse_token_block_count"] == 2
    assert actual["sse_status_events"] == [
        {"type": "status", "stage": "generate", "message": "Preparación"}
    ]


def test_missing_optional_metadata_and_route_are_not_inferred() -> None:
    body = {"answer": "Sin evidencia.", "sources": []}
    result = normalize_payload(body)
    assert result["query_route"] is None
    assert result["route_observed"] is False
    assert result["route_field_present"] is False
    assert result["context_fields_present"] == []
    assert result["enriched_query"] is None
    assert result["ordered_fragments"] == []
    assert decode_stream(stream_for(body))["source_groups"] == []


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"answer":"a","answer":"b","sources":[]}', "duplicate_json_key"),
        (b'{"answer":"a","sources":[],"metadata":{"x":1,"x":2}}', "duplicate_json_key"),
        (b'{"answer":"a","sources":[],"x":NaN}', "non_finite_json"),
        (b'{"answer":"a","sources":[],"x":Infinity}', "non_finite_json"),
        (b'{"answer":"a","sources":[],"x":-Infinity}', "non_finite_json"),
        (b'{"answer":"a","sources":[],"x":1e9999}', "non_finite_json"),
        (b'{"answer":"\xff","sources":[]}', "invalid_utf8"),
        (b'{"answer":"a","sources":[]', "invalid_json"),
        (b"[]", "invalid_payload"),
    ],
)
def test_json_rejects_invalid_or_ambiguous_inputs(raw: bytes, code: str) -> None:
    with pytest.raises(ProtocolError) as caught:
        decode_json(raw)
    assert caught.value.code == code


@pytest.mark.parametrize("indices", [[1, 1, 2], [0, 1, 2], [-1, 1, 2], [True, 2, 3], [1, 2, 4]])
def test_global_indices_must_be_unique_positive_contiguous_integers(indices: list) -> None:
    body = payload()
    fragments = [fragment for group in body["sources"] for fragment in group["fragments"]]
    for fragment, index in zip(fragments, indices, strict=True):
        fragment["index"] = index
    with pytest.raises(ProtocolError) as caught:
        normalize_payload(body)
    assert caught.value.code == "invalid_source_indices"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"answer": None}, "invalid_answer"),
        ({"sources": {}}, "invalid_sources"),
        ({"query_route": "invented"}, "invalid_route"),
        ({"context_tokens": True}, "invalid_context"),
        ({"enriched_query": 12}, "invalid_payload"),
        ({"non_finite": float("nan")}, "invalid_payload"),
    ],
)
def test_direct_payload_rejects_invalid_public_types(changes: dict, code: str) -> None:
    body = payload()
    body.update(changes)
    with pytest.raises(ProtocolError) as caught:
        normalize_payload(body)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("group", "code"),
    [
        ({"source": "a", "fragments": []}, "invalid_source_group"),
        ({"source": "a", "title": "A", "fragments": []}, "invalid_source_group"),
        (
            {"source": "a", "title": "A", "fragments": [{"index": 1, "content": 5}]},
            "invalid_source_fragment",
        ),
        (
            {
                "source": "a",
                "title": "A",
                "metadata": [],
                "fragments": [{"index": 1, "content": "x"}],
            },
            "invalid_source_group",
        ),
    ],
)
def test_malformed_groups_or_fragments_are_rejected(group: dict, code: str) -> None:
    with pytest.raises(ProtocolError) as caught:
        normalize_payload({"answer": "x", "sources": [group]})
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (frame("[DONE]"), "missing_sources"),
        (frame({"type": "sources", "sources": []}), "missing_done"),
        (b'data: {"type":"sources","sources":[]}\n', "incomplete_event"),
        (frame({"type": "sources", "sources": []}) + b"data: [DONE]", "incomplete_event"),
        (frame({"type": "sources", "sources": []}) * 2, "duplicate_sources"),
        (
            frame({"type": "sources", "sources": []}) + frame({"type": "token", "content": "late"}),
            "tokens_after_sources",
        ),
        (frame({"type": "error", "detail": "private-upstream-content"}), "sse_error_event"),
        (frame({"type": "unexpected"}), "unknown_sse_type"),
        (frame(["not-an-object"]), "invalid_sse_event"),
        (frame({"type": "token", "content": 4}), "invalid_sse_event"),
        (frame({"type": "sources", "sources": {}}), "invalid_sources"),
        (b'data: {"type":"status","type":"token","content":"x"}\n\n', "duplicate_json_key"),
        (b'data: {"type":"status","x":NaN}\n\n', "non_finite_json"),
        (b'data: {"type":"token","content":"\xff"}\n\n', "invalid_utf8"),
        (
            frame({"type": "sources", "sources": []}) + frame("[DONE]") + frame("[DONE]"),
            "data_after_done",
        ),
        (
            frame({"type": "sources", "sources": []})
            + frame("[DONE]")
            + frame({"type": "token", "content": "late"}),
            "data_after_done",
        ),
    ],
)
def test_sse_error_truncation_and_trailing_data_are_never_success(raw: bytes, code: str) -> None:
    with pytest.raises(ProtocolError) as caught:
        decode_stream(raw)
    assert caught.value.code == code
    assert "private-upstream-content" not in str(caught.value)


def test_sse_eof_checks_incomplete_utf8_even_after_done() -> None:
    raw = frame({"type": "sources", "sources": []}) + frame("[DONE]") + b"\xc3"
    with pytest.raises(ProtocolError) as caught:
        decode_stream(raw)
    assert caught.value.code == "invalid_utf8"


@pytest.mark.parametrize(
    "limits", [{"max_event_bytes": 0}, {"max_events": -1}, {"max_events": True}]
)
def test_sse_limits_require_positive_integers(limits: dict) -> None:
    with pytest.raises(ProtocolError) as caught:
        SSECapture(**limits)
    assert caught.value.code == "invalid_limits"


def test_sse_event_bytes_are_bounded_before_dispatch() -> None:
    with pytest.raises(ProtocolError) as caught:
        decode_stream(frame({"type": "token", "content": "é" * 30}), max_event_bytes=32)
    assert caught.value.code == "event_too_large"


def test_sse_event_count_includes_done() -> None:
    raw = frame({"type": "sources", "sources": []}) + frame("[DONE]")
    with pytest.raises(ProtocolError) as caught:
        decode_stream(raw, max_events=1)
    assert caught.value.code == "too_many_events"


def test_sse_comment_and_transport_fields_do_not_become_answer_data() -> None:
    prefix = b": keepalive\r\nevent: message\r\nid: 42\r\nretry: 100\r\n\r\n"
    result = decode_stream(prefix + stream_for(payload()))
    assert result["answer"] == payload()["answer"]
    assert result["sse_event_count"] == 5


def test_sse_rejects_reuse_after_protocol_failure_or_completion() -> None:
    failed = SSECapture()
    with pytest.raises(ProtocolError):
        failed.feed(frame({"type": "error"}))
    with pytest.raises(ProtocolError) as caught:
        failed.finish()
    assert caught.value.code == "capture_failed"
    complete = SSECapture()
    complete.feed(stream_for(payload()))
    complete.finish()
    with pytest.raises(ProtocolError) as caught:
        complete.finish()
    assert caught.value.code == "capture_finished"
