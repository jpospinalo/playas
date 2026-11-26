"""Synthetic public-capture contracts; no services, models or local servers."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import socket
import stat
import time
from pathlib import Path

import pytest
from evaluation import api_capture as capture
from evaluation.api_capture_protocol import ProtocolError

from rag.core.tools import CITATION_RE


def _json(path: Path, value: object) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    path.write_bytes(raw)
    return raw


def _payload() -> dict:
    return {
        "answer": "Actuación completa. [DOC3]",
        "sources": [
            {
                "source": "source.jsonl",
                "title": "Título",
                "doc_type": "jurisprudencia",
                "metadata": {"identity": "explicit"},
                "fragments": [
                    {
                        "index": i,
                        "content": f"Pasaje íntegro {i}",
                        "metadata": {
                            "chunk_id": f"id-{i}",
                            "summary": "Auxiliar",
                            "unknown": [1, None],
                        },
                    }
                    for i in range(1, 4)
                ],
            }
        ],
        "query_route": "in_scope",
        "enriched_query": "Consulta íntegra",
        "context_tokens": 10,
        "context_limit": 200000,
    }


def _configuration(tmp_path: Path, *, conversational: bool = False) -> tuple[Path, dict]:
    if conversational:
        bank = {
            "items": [
                {
                    "id": "c-1",
                    "categoria": "conversacion",
                    "persona": "fixture",
                    "turnos": [
                        {"pregunta": f"Turno {i}", "esperado": f"Criterio {i}"} for i in range(1, 4)
                    ],
                }
            ]
        }
    else:
        bank = {
            "cases": [
                {
                    "id": "same",
                    "pregunta": "Pregunta íntegra",
                    "respuesta": "Esperada",
                    "documentos_esperados": ["Título"],
                    "revisado": True,
                }
            ]
        }
    raw = _json(tmp_path / "bank.json", bank)
    now = dt.datetime.now(dt.UTC)
    values: dict = dict.fromkeys(capture.IDENTITY_FIELDS, "confirmed")
    values.update(
        {
            "backend_commit": "a" * 40,
            "image_digest": "sha256:" + "b" * 64,
            "gold_payload_sha256": "c" * 64,
            "embedding_digest": "d" * 64,
            "embedding_recipe_sha256": "e" * 64,
            "embedding_dimension": 768,
            "generation_parameters": {},
            "query_enrichment_enabled": False,
            "chroma_query_transport": "rest_async",
            "legal_resolution_state": "snapshot_verified",
            "legal_resolution_provenance_sha256": "f" * 64,
        }
    )
    token = tmp_path / "token"
    token.write_text("synthetic-not-a-real-credential")
    token.chmod(0o600)
    cfg = {
        "schema_version": 1,
        "datasets": [
            {"name": "bank-a", "path": "bank.json", "sha256": hashlib.sha256(raw).hexdigest()}
        ],
        "channels": ["JSON", "SSE"],
        "base_url": "https://capture.invalid",
        "bearer_token_file": "token",
        "output_dir": str(tmp_path / "new-output"),
        "expected": values,
        "runtime_confirmation": {
            "values": values.copy(),
            "confirmed_at_utc": now.isoformat(),
            "evidence_reference": "synthetic-receipt",
        },
        "authorization": {
            "approved": True,
            "no_concurrent_changes_confirmed": True,
            "valid_until_utc": (now + dt.timedelta(hours=1)).isoformat(),
            "external_deadline_seconds": 3600,
            "cleanup_reference": "synthetic-supervisor",
        },
        "conversation": {
            "single_process": True,
            "stable_backend": True,
            "user_reference": "synthetic-user",
            "retirement_reference": "synthetic-retirement",
        },
    }
    path = tmp_path / "config.json"
    _json(path, cfg)
    return path, cfg


def _complete_transport(seen: list):
    def transport(plan, channel, body, token, raw_path, deadline, observed):
        intent = json.loads(raw_path.with_suffix(".intent.json").read_text())
        assert intent["state"] == "intent_before_send"
        assert intent["request_sha256"] == hashlib.sha256(body).hexdigest()
        assert deadline <= time.monotonic() + plan["limits"]["request_budget_seconds"]
        seen.append((channel, json.loads(body), token))
        raw = json.dumps(_payload(), ensure_ascii=False).encode()
        raw_path.write_bytes(raw)
        raw_path.chmod(0o600)
        observed.update({"http_status": 200, "bytes": len(raw)})
        return capture.decode_json(raw)

    return transport


def test_global_fragment_citations_preserve_public_metadata_and_answer() -> None:
    payload = _payload()
    payload["answer"] = "Sin limpiar. [DOC3] [doc0] [doc4]"
    response = capture.decode_json(json.dumps(payload).encode())
    observation = capture.structural_observations(response)
    assert capture.CITATION_RE is CITATION_RE
    assert observation == {
        "citation_indices": [0, 3, 4],
        "invalid_citation_indices": [0, 4],
        "fragment_count": 3,
        "semantic_assessment": "not_performed",
    }
    assert response["source_groups"] == payload["sources"]
    assert response["answer"] == payload["answer"]


def test_default_cli_never_reads_token_connects_or_creates_output(
    tmp_path, monkeypatch, capsys
) -> None:
    config_path, _ = _configuration(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected_credential_or_network_access")

    monkeypatch.setattr(capture, "read_token", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(capture.http.client.HTTPSConnection, "connect", forbidden)
    assert capture.main(["--config", str(config_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "validated_not_executed"
    assert output["network_calls"] == 0 and output["token_read"] is False
    assert not (tmp_path / "new-output").exists()


def test_execution_requires_confirmations_even_with_execute_flag(
    tmp_path, monkeypatch, capsys
) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["authorization"]["approved"] = False
    _json(path, cfg)
    monkeypatch.setattr(
        capture, "read_token", lambda *_: pytest.fail("token read before authorization")
    )
    assert capture.main(["--config", str(path), "--execute"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["error_code"] == "execution_has_pending_confirmations"
    )
    assert not (tmp_path / "new-output").exists()


def test_pending_identity_is_preserved_but_mismatch_is_rejected(tmp_path) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["runtime_confirmation"]["values"]["collection"] = None
    _json(path, cfg)
    plan = capture.load_plan(path)
    assert "runtime.collection" in plan["pending"]
    assert plan["config"]["runtime_confirmation"]["values"]["collection"] is None
    cfg["runtime_confirmation"]["values"]["collection"] = "other-collection"
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="runtime_identity_mismatch"):
        capture.load_plan(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("embedding_dimension", True),
        ("query_enrichment_enabled", "false"),
        ("generation_parameters", "unknown"),
        ("embedding_recipe_sha256", "invalid"),
    ],
)
def test_invalid_runtime_identity_cannot_be_confirmed_by_repeating_it(
    tmp_path, field, value
) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["expected"][field] = value
    cfg["runtime_confirmation"]["values"][field] = value
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="invalid_identity"):
        capture.load_plan(path)


def test_recipe_and_enrichment_configuration_are_required_separately(tmp_path) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["expected"]["query_enrichment_enabled"] = True
    cfg["runtime_confirmation"]["values"]["query_enrichment_enabled"] = True
    del cfg["expected"]["embedding_recipe_sha256"]
    _json(path, cfg)
    plan = capture.load_plan(path)
    assert "expected.embedding_recipe_sha256" in plan["pending"]
    for key in ("enricher_provider", "enricher_model", "enricher_parameters"):
        assert "expected." + key in plan["pending"]
        assert "runtime." + key in plan["pending"]


def test_individual_cases_omit_all_session_fields_and_keep_case_identity(tmp_path) -> None:
    path, cfg = _configuration(tmp_path)
    second = {
        "items": [
            {"id": "same", "categoria": "vaga", "pregunta": "Otra pregunta", "esperado": "Aclarar"}
        ]
    }
    raw = _json(tmp_path / "second.json", second)
    cfg["datasets"].append(
        {"name": "bank-b", "path": "second.json", "sha256": hashlib.sha256(raw).hexdigest()}
    )
    _json(path, cfg)
    plan = capture.load_plan(path)
    seen = []
    summary = capture.execute(plan, _complete_transport(seen))
    assert summary["status"] == "complete" and summary["requests_attempted"] == 4
    assert {(row["dataset"], row["id"], row["channel"]) for row in summary["results"]} == {
        (bank, "same", channel) for bank in ("bank-a", "bank-b") for channel in ("JSON", "SSE")
    }
    assert all(
        not ({"thread_id", "conversation_id", "current_message_id"} & set(body))
        for _, body, _ in seen
    )
    assert len({token for _, _, token in seen}) == 1
    assert all(
        t["response"]["source_groups"] == _payload()["sources"]
        for r in summary["results"]
        for t in r["turns"]
    )
    for file in plan["output"].iterdir():
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert stat.S_IMODE(plan["output"].stat().st_mode) == 0o700
    manifest = json.loads((plan["output"] / "MANIFEST.json").read_text())
    assert manifest["expected"] == cfg["expected"]
    assert manifest["runtime_confirmation"] == cfg["runtime_confirmation"]
    assert manifest["semantic_assessment"] == "not_performed"


def test_conversation_threads_are_stable_only_within_case_channel_and_run(tmp_path) -> None:
    path, cfg = _configuration(tmp_path, conversational=True)
    plan = capture.load_plan(path)
    seen = []
    summary = capture.execute(plan, _complete_transport(seen))
    assert summary["requests_attempted"] == 6
    per_channel = {
        channel: [body for c, body, _ in seen if c == channel] for channel in ("JSON", "SSE")
    }
    for bodies in per_channel.values():
        assert [body["question"] for body in bodies] == ["Turno 1", "Turno 2", "Turno 3"]
        assert len({body["thread_id"] for body in bodies}) == 1
        assert all(not ({"conversation_id", "current_message_id"} & set(body)) for body in bodies)
    assert per_channel["JSON"][0]["thread_id"] != per_channel["SSE"][0]["thread_id"]
    cfg["output_dir"] = str(tmp_path / "next-run")
    _json(path, cfg)
    second_seen = []
    capture.execute(capture.load_plan(path), _complete_transport(second_seen))
    assert {b["thread_id"] for _, b, _ in seen}.isdisjoint(
        {b["thread_id"] for _, b, _ in second_seen}
    )


def test_uncertain_turn_consumes_attempt_without_resend_or_next_turn(tmp_path) -> None:
    path, _ = _configuration(tmp_path, conversational=True)
    plan = capture.load_plan(path)
    seen = []
    complete = _complete_transport(seen)

    def transport(plan, channel, body, token, raw_path, deadline, observed):
        if json.loads(body)["question"] == "Turno 2":
            seen.append((channel, json.loads(body), token))
            raw_path.write_bytes(b"partial-body")
            raw_path.chmod(0o600)
            raise OSError("secret-should-never-be-saved")
        return complete(plan, channel, body, token, raw_path, deadline, observed)

    summary = capture.execute(plan, transport)
    assert summary["status"] == "partial" and summary["requests_attempted"] == 4
    for row in summary["results"]:
        assert [t["status"] for t in row["turns"]] == ["complete", "uncertain", "not_executed"]
        assert row["turns"][1]["attempt_consumed"] is True
        assert row["turns"][2]["reason"] == "previous_turn_uncertain"
    assert all(b["question"] != "Turno 3" for _, b, _ in seen)
    assert sum(f.read_bytes() == b"partial-body" for f in plan["output"].glob("*.raw")) == 2
    assert all(
        b"secret-should-never-be-saved" not in f.read_bytes() for f in plan["output"].glob("*.json")
    )


def test_existing_output_rejected_before_token_read_or_new_requests(tmp_path, monkeypatch) -> None:
    path, _ = _configuration(tmp_path)
    plan = capture.load_plan(path)
    plan["output"].mkdir()
    original = plan["output"] / "preserved"
    original.write_text("existing evidence")
    monkeypatch.setattr(capture, "read_token", lambda *_: pytest.fail("existing output read token"))
    with pytest.raises(FileExistsError):
        capture.execute(plan, lambda *_: pytest.fail("existing output sent request"))
    assert original.read_text() == "existing evidence"
    with pytest.raises(capture.CaptureError, match="output_already_exists"):
        capture.load_plan(path)


def test_bank_hash_and_exact_selection_are_validated(tmp_path) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["datasets"][0]["case_ids"] = ["absent"]
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="invalid_case_selection"):
        capture.load_plan(path)
    cfg["datasets"][0].pop("case_ids")
    cfg["datasets"][0]["sha256"] = "0" * 64
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="dataset_hash_mismatch"):
        capture.load_plan(path)


def test_both_trusted_banks_keep_106_cases_118_turns_and_236_planned_requests(
    tmp_path, monkeypatch, capsys
) -> None:
    data_dir = Path(capture.__file__).parent / "data"
    known = {
        "legal-ground-truth-v0.2.json": "edb4ecdaa7655a3505025c159eae471fcb2088be9442187870b35b951dbf8225",
        "preguntas-reales-v1.json": "2b1562f973f5eaaa611f30241396a3761e6e2c50bafdca64e357d8974d789597",
    }
    specs = []
    originals = {}
    for filename, expected_sha in known.items():
        source = data_dir / filename
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected_sha
        dataset = json.loads(raw)
        name = "legal-v02" if filename.startswith("legal-") else "preguntas-reales-v1"
        originals[name] = dataset.get("cases", dataset.get("items"))
        specs.append({"name": name, "path": str(source), "sha256": expected_sha})
    cfg = {
        "schema_version": 1,
        "datasets": specs,
        "channels": ["JSON", "SSE"],
        "output_dir": str(tmp_path / "not-executed"),
        "base_url": None,
        "bearer_token_file": None,
        "expected": {},
        "runtime_confirmation": {},
        "conversation": {},
        "authorization": {},
    }
    config_path = tmp_path / "technical-inventory.json"
    _json(config_path, cfg)

    def forbidden(*args, **kwargs):
        pytest.fail("technical inventory attempted credential or service access")

    monkeypatch.setattr(capture, "read_token", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(capture.http.client.HTTPSConnection, "connect", forbidden)
    plan = capture.load_plan(config_path)
    assert sum(len(bank["cases"]) for bank in plan["banks"]) == 106
    assert sum(len(case["turns"]) for bank in plan["banks"] for case in bank["cases"]) == 118
    assert plan["requests"] == 236 and plan["pending"]
    for bank in plan["banks"]:
        assert [case["id"] for case in bank["cases"]] == [
            case["id"] for case in originals[bank["name"]]
        ]
        assert [case["reference_case"] for case in bank["cases"]] == originals[bank["name"]]
    assert capture.main(["--config", str(config_path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["cases"] == 106 and receipt["requests"] == 236
    assert receipt["status"] == "validated_not_executed" and receipt["pending"]
    assert receipt["network_calls"] == 0 and receipt["token_read"] is False
    assert not (tmp_path / "not-executed").exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@capture.invalid",
        "https://capture.invalid/path",
        "https://capture.invalid?token=secret",
        "file:///tmp/input",
    ],
)
def test_target_is_one_origin_without_credentials_paths_or_queries(tmp_path, url) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["base_url"] = url
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="base_url_must_be_origin_without_credentials"):
        capture.load_plan(path)


def test_http_opt_in_and_private_nonsymlink_token(tmp_path) -> None:
    path, cfg = _configuration(tmp_path)
    cfg["base_url"] = "http://capture.invalid"
    _json(path, cfg)
    assert "allow_plain_http" in capture.load_plan(path)["pending"]
    (tmp_path / "token").chmod(0o644)
    with pytest.raises(capture.CaptureError, match="token_must_be_regular_private_file"):
        capture.load_plan(path)
    (tmp_path / "token").chmod(0o600)
    (tmp_path / "token-link").symlink_to(tmp_path / "token")
    cfg["bearer_token_file"] = "token-link"
    _json(path, cfg)
    with pytest.raises(capture.CaptureError, match="token_must_be_regular_private_file"):
        capture.load_plan(path)


def test_conversation_and_external_deadline_confirmations_cannot_be_omitted(tmp_path) -> None:
    path, cfg = _configuration(tmp_path, conversational=True)
    cfg["conversation"] = {}
    cfg["authorization"].pop("external_deadline_seconds")
    cfg["authorization"].pop("cleanup_reference")
    _json(path, cfg)
    pending = capture.load_plan(path)["pending"]
    assert {
        "conversation.single_process",
        "conversation.stable_backend",
        "conversation.user_reference",
        "conversation.retirement_reference",
        "authorization.external_deadline_seconds",
        "authorization.cleanup_reference",
    } <= set(pending)


class _Socket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, seconds):
        self.timeouts.append(seconds)


class _Response:
    def __init__(self, raw, *, status=200, media="application/json", extra_length=0):
        self.raw = raw
        self.length = len(raw) + extra_length
        self.status = status
        self.media = media
        self.closed = False
        self.calls = 0

    def getheader(self, name, default):
        return self.media if name == "Content-Type" else default

    def isclosed(self):
        return self.closed

    def read1(self, limit):
        assert not self.closed, "read after transport auto-closed"
        self.calls += 1
        chunk, self.raw = self.raw[:limit], self.raw[limit:]
        self.length -= len(chunk)
        if not self.raw:
            self.closed = True
        return chunk

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, response):
        self.response = response
        self.sock = _Socket()
        self.closed = False
        self.requests = []

    def connect(self):
        pass

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def _exchange_setup(tmp_path, monkeypatch, raw, *, status=200, extra_length=0):
    path, cfg = _configuration(tmp_path)
    cfg["base_url"] = "http://capture.invalid"
    cfg["allow_plain_http"] = True
    _json(path, cfg)
    plan = capture.load_plan(path)
    response = _Response(raw, status=status, extra_length=extra_length)
    connection = _Connection(response)
    monkeypatch.setattr(capture.http.client, "HTTPConnection", lambda *a, **kw: connection)
    return plan, response, connection


def test_transport_preserves_body_and_closes_after_content_length_auto_close(
    tmp_path, monkeypatch
) -> None:
    raw = json.dumps(_payload()).encode()
    plan, response, connection = _exchange_setup(tmp_path, monkeypatch, raw)
    observed = {"http_status": None, "bytes": 0}
    result = capture.exchange(
        plan, "JSON", b"{}", "synthetic", tmp_path / "capture.raw", time.monotonic() + 60, observed
    )
    assert result["answer"] == _payload()["answer"]
    assert (tmp_path / "capture.raw").read_bytes() == raw
    assert response.closed and connection.closed and response.calls == 1
    assert len(connection.requests) == 1
    assert all(
        0 < value <= plan["limits"]["socket_timeout_seconds"] for value in connection.sock.timeouts
    )


def test_transport_error_body_is_never_saved_or_echoed(tmp_path, monkeypatch) -> None:
    plan, response, connection = _exchange_setup(
        tmp_path, monkeypatch, b"external-secret", status=500
    )
    with pytest.raises(capture.CaptureError, match="http_status_not_200") as error:
        capture.exchange(
            plan,
            "JSON",
            b"{}",
            "synthetic",
            tmp_path / "capture.raw",
            time.monotonic() + 60,
            {"http_status": None, "bytes": 0},
        )
    assert "external-secret" not in str(error.value)
    assert (tmp_path / "capture.raw").read_bytes() == b""
    assert response.calls == 0 and response.closed and connection.closed


def test_sse_transport_uses_its_parser_and_public_endpoint(tmp_path, monkeypatch) -> None:
    payload = _payload()
    sources = {key: value for key, value in payload.items() if key != "answer"}
    raw = (
        "data: "
        + json.dumps({"type": "token", "content": payload["answer"]})
        + "\n\n"
        + "data: "
        + json.dumps({"type": "sources", **sources})
        + "\n\n"
        + "data: [DONE]\n\n"
    ).encode()
    plan, response, connection = _exchange_setup(tmp_path, monkeypatch, raw)
    response.media = "text/event-stream"
    result = capture.exchange(
        plan,
        "SSE",
        b"{}",
        "synthetic",
        tmp_path / "capture.raw",
        time.monotonic() + 60,
        {"http_status": None, "bytes": 0},
    )
    assert result["sse_done"] is True and result["answer"] == payload["answer"]
    assert result["source_groups"] == payload["sources"]
    assert connection.requests[0][0] == ("POST", "/api/query/stream")
    assert connection.requests[0][1]["headers"]["Accept"] == "text/event-stream"
    assert response.closed and connection.closed


def test_received_partial_bytes_survive_read_error_and_both_close_paths(
    tmp_path, monkeypatch
) -> None:
    plan, response, connection = _exchange_setup(tmp_path, monkeypatch, b"unused")
    chunks = iter([b"received-partial"])

    def fail_after_first_chunk(limit):
        try:
            return next(chunks)
        except StopIteration:
            raise OSError("read-secret") from None

    def failed_response_close():
        response.closed = True
        raise OSError("close-secret")

    monkeypatch.setattr(response, "read1", fail_after_first_chunk)
    monkeypatch.setattr(response, "close", failed_response_close)
    with pytest.raises(OSError):
        capture.exchange(
            plan,
            "JSON",
            b"{}",
            "synthetic",
            tmp_path / "capture.raw",
            time.monotonic() + 60,
            {"http_status": None, "bytes": 0},
        )
    assert (tmp_path / "capture.raw").read_bytes() == b"received-partial"
    assert response.closed and connection.closed and len(connection.requests) == 1


@pytest.mark.parametrize("fault", ["invalid_json", "truncated_http", "byte_limit"])
def test_partial_transport_evidence_survives_failure_and_cleanup(
    tmp_path, monkeypatch, fault
) -> None:
    raw = b'{"answer":"partial"' if fault == "invalid_json" else json.dumps(_payload()).encode()
    plan, response, connection = _exchange_setup(
        tmp_path, monkeypatch, raw, extra_length=5 if fault == "truncated_http" else 0
    )
    if fault == "byte_limit":
        plan["limits"]["max_response_bytes"] = 10
    with pytest.raises((capture.CaptureError, ProtocolError)):
        capture.exchange(
            plan,
            "JSON",
            b"{}",
            "synthetic",
            tmp_path / "capture.raw",
            time.monotonic() + 60,
            {"http_status": None, "bytes": 0},
        )
    evidence = (tmp_path / "capture.raw").read_bytes()
    assert evidence == (raw[:11] if fault == "byte_limit" else raw)
    assert response.closed and connection.closed and len(connection.requests) == 1


def test_expired_cooperative_budget_stops_before_connect(tmp_path, monkeypatch) -> None:
    plan, response, connection = _exchange_setup(tmp_path, monkeypatch, b"unused")
    monkeypatch.setattr(connection, "connect", lambda: pytest.fail("expired budget connected"))
    with pytest.raises(capture.CaptureError, match="request_budget_exhausted"):
        capture.exchange(
            plan,
            "JSON",
            b"{}",
            "synthetic",
            tmp_path / "capture.raw",
            time.monotonic() - 1,
            {"http_status": None, "bytes": 0},
        )
    assert connection.closed and connection.requests == []


def test_capture_import_does_not_load_the_agent_or_api() -> None:
    import sys

    assert not any(name in sys.modules for name in ["rag.core.agent", "rag.api.main", "chromadb"])
