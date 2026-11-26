"""Capture the public JSON/SSE API using either trusted question bank.

``python -m evaluation.api_capture --config /external/config.json`` only
validates local inputs. ``--execute`` additionally requires complete runtime
confirmations and a separate, unexpired authorization. No result is resumed.
See ``docs/SCRIPTS.md`` for configuration, limits and semantic review scope.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import math
import os
import re
import ssl
import stat
import time
import uuid
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from evaluation import api_capture_protocol
from evaluation.api_capture_protocol import ProtocolError, SSECapture, decode_json
from rag.core.tools import CITATION_RE

PATHS = {"JSON": "/api/query", "SSE": "/api/query/stream"}
REPO = Path(__file__).resolve().parents[2]
IDENTITY_FIELDS = (
    "backend_commit",
    "image_digest",
    "gold_version",
    "gold_payload_sha256",
    "collection",
    "tenant",
    "database",
    "embedding_model",
    "embedding_digest",
    "embedding_dimension",
    "embedding_recipe_sha256",
    "generation_provider",
    "generation_model",
    "generation_parameters",
    "query_enrichment_enabled",
    "chroma_query_transport",
    "legal_resolution_provenance_sha256",
    "legal_resolution_state",
)
DEFAULT_LIMITS = {
    "connect_timeout_seconds": 10,
    "socket_timeout_seconds": 120,
    "request_budget_seconds": 180,
    "run_budget_seconds": 3600,
    "max_response_bytes": 8388608,
    "max_sse_events": 10000,
    "max_sse_event_bytes": 1048576,
}
CEILINGS = {
    **DEFAULT_LIMITS,
    "connect_timeout_seconds": 30,
    "socket_timeout_seconds": 360,
    "request_budget_seconds": 360,
}


class CaptureError(ValueError):
    """Fixed control codes; never copy credentials or external error bodies."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def save(path: Path, value: object) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _unique(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("duplicate_json_key")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise CaptureError("nonfinite_json")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise CaptureError("nonfinite_json")
    return number


def load_object(path: Path, limit: int = 1048576) -> tuple[dict, bytes]:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise CaptureError("local_input_too_large")
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=_constant,
            parse_float=_float,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CaptureError("invalid_local_json") from exc
    if not isinstance(result, dict):
        raise CaptureError("local_object_required")
    return result, raw


def local_path(value: object, parent: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError("invalid_local_path")
    result = Path(value).expanduser()
    return result if result.is_absolute() else parent / result


def timestamp(value: object) -> dt.datetime:
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(dt.UTC)
    except ValueError as exc:
        raise CaptureError("invalid_utc_timestamp") from exc


def token_metadata(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise CaptureError("token_must_be_regular_private_file")
    if not 1 <= info.st_size <= 8192:
        raise CaptureError("token_size")


def read_token(path: Path) -> str:
    token_metadata(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise CaptureError("token_must_be_regular_private_file")
        raw = os.read(fd, 8193)
    finally:
        os.close(fd)
    try:
        token = raw.decode("ascii").strip()
    except UnicodeError as exc:
        raise CaptureError("invalid_bearer_token") from exc
    if len(raw) > 8192 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token):
        raise CaptureError("invalid_bearer_token")
    return token


def load_bank(spec: dict, parent: Path) -> dict:
    name = spec.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        raise CaptureError("invalid_dataset_name")
    path = local_path(spec.get("path"), parent)
    data, raw = load_object(path)
    if spec.get("sha256") != sha256(raw):
        raise CaptureError("dataset_hash_mismatch")
    if "cases" in data and "items" not in data:
        original = data["cases"]
        schema = "legal-ground-truth-v0.2"
    elif "items" in data and "cases" not in data:
        original = data["items"]
        schema = "preguntas-reales-v1"
    else:
        raise CaptureError("unsupported_dataset_schema")
    if not isinstance(original, list) or not original:
        raise CaptureError("empty_dataset")
    cases = []
    seen = set()
    for item in original:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise CaptureError("invalid_case_id")
        if item["id"] in seen:
            raise CaptureError("duplicate_case_id")
        seen.add(item["id"])
        conversation = schema == "preguntas-reales-v1" and item.get("categoria") == "conversacion"
        turns = item.get("turnos") if conversation else [item]
        if not isinstance(turns, list) or not turns:
            raise CaptureError("empty_conversation")
        for turn in turns:
            if (
                not isinstance(turn, dict)
                or not isinstance(turn.get("pregunta"), str)
                or not 1 <= len(turn["pregunta"].strip()) <= 4000
            ):
                raise CaptureError("invalid_bank_question")
        cases.append(
            {"id": item["id"], "conversation": conversation, "turns": turns, "reference_case": item}
        )
    selection = spec.get("case_ids")
    if selection is not None:
        if (
            not isinstance(selection, list)
            or not selection
            or any(not isinstance(x, str) for x in selection)
            or len(selection) != len(set(selection))
            or not set(selection) <= seen
        ):
            raise CaptureError("invalid_case_selection")
        cases = [case for case in cases if case["id"] in selection]
    return {"name": name, "schema": schema, "sha256": sha256(raw), "cases": cases}


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _validate_identity(values: dict) -> None:
    for key in (*IDENTITY_FIELDS, "enricher_provider", "enricher_model", "enricher_parameters"):
        value = values.get(key)
        if _missing(value):
            continue
        if key == "embedding_dimension":
            valid = type(value) is int and value > 0
        elif key == "query_enrichment_enabled":
            valid = type(value) is bool
        elif key.endswith("_parameters"):
            valid = isinstance(value, dict)
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            raise CaptureError("invalid_identity_field")
        if key in {
            "backend_commit",
            "gold_payload_sha256",
            "embedding_digest",
            "embedding_recipe_sha256",
            "legal_resolution_provenance_sha256",
        }:
            length = 40 if key == "backend_commit" else 64
            if not re.fullmatch(r"[0-9a-fA-F]{" + str(length) + "}", cast(str, value)):
                raise CaptureError("invalid_identity_digest")
        if key == "image_digest" and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", cast(str, value)):
            raise CaptureError("invalid_image_digest")
    if values.get("chroma_query_transport") not in {None, "rest_async", "sdk_fallback"}:
        raise CaptureError("invalid_chroma_transport")
    if values.get("legal_resolution_state") not in {None, "snapshot_verified"}:
        raise CaptureError("invalid_provenance_state")


def load_plan(config_path: Path) -> dict:
    """Validate local inputs; no DNS, service calls or credential-content reads."""
    cfg, raw = load_object(config_path, 65536)
    if cfg.get("schema_version") != 1:
        raise CaptureError("configuration_version")
    specs = cfg.get("datasets")
    if (
        not isinstance(specs, list)
        or not 1 <= len(specs) <= 2
        or any(not isinstance(x, dict) for x in specs)
    ):
        raise CaptureError("invalid_datasets")
    banks = [load_bank(spec, config_path.parent) for spec in specs]
    if len({x["name"] for x in banks}) != len(banks):
        raise CaptureError("duplicate_dataset_name")
    channels = cfg.get("channels", ["JSON", "SSE"])
    if (
        not isinstance(channels, list)
        or not channels
        or any(x not in PATHS for x in channels)
        or len(set(channels)) != len(channels)
    ):
        raise CaptureError("invalid_channels")
    params = cfg.get("query_parameters", {"k": 4, "k_candidates": 8, "doc_types": None})
    if (
        not isinstance(params, dict)
        or set(params) != {"k", "k_candidates", "doc_types"}
        or type(params["k"]) is not int
        or not 1 <= params["k"] <= 8
        or type(params["k_candidates"]) is not int
        or not max(4, params["k"]) <= params["k_candidates"] <= 20
    ):
        raise CaptureError("invalid_query_parameters")
    filters = params["doc_types"]
    if filters is not None and (
        not isinstance(filters, list)
        or not 1 <= len(filters) <= 2
        or any(x not in {"normativa", "jurisprudencia"} for x in filters)
        or len(set(filters)) != len(filters)
    ):
        raise CaptureError("invalid_doc_types")
    supplied_limits = cfg.get("limits", {})
    if not isinstance(supplied_limits, dict) or set(supplied_limits) - (
        set(CEILINGS) | {"max_requests"}
    ):
        raise CaptureError("invalid_limit_fields")
    limits = {**DEFAULT_LIMITS, **supplied_limits}
    requests = sum(len(c["turns"]) for bank in banks for c in bank["cases"]) * len(channels)
    limits.setdefault("max_requests", requests)
    for key, ceiling in {**CEILINGS, "max_requests": 236}.items():
        if type(limits[key]) is not int or not 1 <= limits[key] <= ceiling:
            raise CaptureError("invalid_limits")
    if limits["max_requests"] != requests:
        raise CaptureError("request_count_mismatch")
    pending = []
    target = None
    if cfg.get("base_url") is None:
        pending.append("base_url")
    else:
        value = cfg["base_url"]
        if not isinstance(value, str) or any(ord(c) < 33 for c in value):
            raise CaptureError("invalid_base_url")
        target = urlsplit(value)
        if (
            target.scheme not in {"http", "https"}
            or not target.hostname
            or target.username is not None
            or target.password is not None
            or target.path not in {"", "/"}
            or target.query
            or target.fragment
        ):
            raise CaptureError("base_url_must_be_origin_without_credentials")
        try:
            _ = target.port
        except ValueError as exc:
            raise CaptureError("invalid_port") from exc
        if target.scheme == "http" and cfg.get("allow_plain_http") is not True:
            pending.append("allow_plain_http")
    token_path = None
    if cfg.get("bearer_token_file") is None:
        pending.append("bearer_token_file")
    else:
        token_path = local_path(cfg["bearer_token_file"], config_path.parent)
        token_metadata(token_path)
    output = local_path(cfg.get("output_dir"), config_path.parent)
    if output.resolve().is_relative_to(REPO.resolve()):
        raise CaptureError("output_must_be_outside_repository")
    if output.exists() or output.is_symlink():
        raise CaptureError("output_already_exists")
    expected = cfg.get("expected", {})
    confirmation = cfg.get("runtime_confirmation", {})
    if not isinstance(expected, dict) or not isinstance(confirmation, dict):
        raise CaptureError("invalid_runtime_identity")
    actual = confirmation.get("values", {})
    if not isinstance(actual, dict):
        raise CaptureError("invalid_runtime_identity")
    _validate_identity(expected)
    _validate_identity(actual)
    fields = list(IDENTITY_FIELDS)
    if expected.get("query_enrichment_enabled") is True:
        fields += ["enricher_provider", "enricher_model", "enricher_parameters"]
    for key in fields:
        declared, confirmed = expected.get(key), actual.get(key)
        if _missing(declared):
            pending.append("expected." + key)
        if _missing(confirmed):
            pending.append("runtime." + key)
        if not _missing(declared) and not _missing(confirmed):
            if type(declared) is not type(confirmed) or declared != confirmed:
                raise CaptureError("runtime_identity_mismatch")
    for key in ("confirmed_at_utc", "evidence_reference"):
        if _missing(confirmation.get(key)):
            pending.append("runtime_confirmation." + key)
    now = dt.datetime.now(dt.UTC)
    if confirmation.get("confirmed_at_utc") and timestamp(confirmation["confirmed_at_utc"]) > now:
        raise CaptureError("runtime_confirmation_in_future")
    if any(c["conversation"] for bank in banks for c in bank["cases"]):
        conversation = cfg.get("conversation", {})
        if not isinstance(conversation, dict):
            raise CaptureError("invalid_conversation_confirmation")
        for key in ("single_process", "stable_backend"):
            if conversation.get(key) is not True:
                pending.append("conversation." + key)
        for key in ("user_reference", "retirement_reference"):
            if not isinstance(conversation.get(key), str) or not conversation[key].strip():
                pending.append("conversation." + key)
    approval = cfg.get("authorization", {})
    if not isinstance(approval, dict):
        raise CaptureError("invalid_authorization")
    for key in ("approved", "no_concurrent_changes_confirmed"):
        if approval.get(key) is not True:
            pending.append("authorization." + key)
    if not approval.get("valid_until_utc"):
        pending.append("authorization.valid_until_utc")
    elif timestamp(approval["valid_until_utc"]) <= now:
        pending.append("authorization.expired")
    external = approval.get("external_deadline_seconds")
    if type(external) is not int or not limits["run_budget_seconds"] <= external <= 3660:
        pending.append("authorization.external_deadline_seconds")
    if (
        not isinstance(approval.get("cleanup_reference"), str)
        or not approval["cleanup_reference"].strip()
    ):
        pending.append("authorization.cleanup_reference")
    return {
        "config": cfg,
        "config_sha256": sha256(raw),
        "banks": banks,
        "channels": channels,
        "params": params,
        "limits": limits,
        "requests": requests,
        "pending": pending,
        "target": target,
        "token_path": token_path,
        "output": output,
    }


def exchange(
    plan: dict,
    channel: str,
    body: bytes,
    token: str,
    raw_path: Path,
    deadline: float,
    observed: dict,
) -> dict:
    """One exchange; socket deadlines are cooperative, not a DNS wall-clock cap."""
    target, limits = plan["target"], plan["limits"]
    connection_type = (
        http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    )
    kwargs = {
        "timeout": min(limits["connect_timeout_seconds"], max(0.001, deadline - time.monotonic()))
    }
    if target.scheme == "https":
        kwargs["context"] = ssl.create_default_context()
    connection = connection_type(target.hostname, port=target.port, **kwargs)
    response = None
    parser = (
        SSECapture(limits["max_sse_event_bytes"], limits["max_sse_events"])
        if channel == "SSE"
        else None
    )
    fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", buffering=0) as evidence:

            def remaining() -> float:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise CaptureError("request_budget_exhausted")
                return min(limits["socket_timeout_seconds"], left)

            remaining()
            connection.connect()
            transport_socket = connection.sock
            transport_socket.settimeout(remaining())
            connection.request(
                "POST",
                PATHS[channel],
                body=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "Accept": "application/json" if channel == "JSON" else "text/event-stream",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            transport_socket.settimeout(remaining())
            response = connection.getresponse()
            observed["http_status"] = response.status
            media = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if response.status != 200:
                raise CaptureError("http_status_not_200")
            if media != ("application/json" if channel == "JSON" else "text/event-stream"):
                raise CaptureError("unexpected_content_type")
            if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
                raise CaptureError("unexpected_content_encoding")
            parts = []
            try:
                while True:
                    if response.isclosed():
                        if response.length not in {None, 0}:
                            raise CaptureError("http_body_truncated")
                        break
                    transport_socket.settimeout(remaining())
                    block = response.read1(
                        min(65536, limits["max_response_bytes"] - observed["bytes"] + 1)
                    )
                    if not block:
                        if response.length not in {None, 0}:
                            raise CaptureError("http_body_truncated")
                        break
                    evidence.write(block)
                    observed["bytes"] += len(block)
                    if observed["bytes"] > limits["max_response_bytes"]:
                        raise CaptureError("response_byte_limit")
                    if parser is None:
                        parts.append(block)
                    else:
                        parser.feed(block)
                remaining()
                return parser.finish() if parser else decode_json(b"".join(parts))
            finally:
                os.fsync(evidence.fileno())
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            connection.close()


def structural_observations(response: dict) -> dict:
    indices = sorted({int(x) for x in CITATION_RE.findall(response["answer"])})
    available = {f["index"] for f in response["ordered_fragments"]}
    return {
        "citation_indices": indices,
        "invalid_citation_indices": [i for i in indices if i not in available],
        "fragment_count": len(available),
        "semantic_assessment": "not_performed",
    }


def execute(plan: dict, exchange_fn=None) -> dict:
    """Run once using reviewed runtime confirmations; test transports stay in memory."""
    if plan["pending"]:
        raise CaptureError("execution_has_pending_confirmations")
    output = plan["output"]
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    token = read_token(plan["token_path"])
    run_id = uuid.uuid4().hex
    transport = exchange if exchange_fn is None else exchange_fn
    save(
        output / "MANIFEST.json",
        {
            "run_id": run_id,
            "configuration_sha256": plan["config_sha256"],
            "capture_sha256": sha256(Path(__file__).read_bytes()),
            "protocol_sha256": sha256(Path(api_capture_protocol.__file__).read_bytes()),
            "datasets": [
                {
                    "name": b["name"],
                    "schema": b["schema"],
                    "sha256": b["sha256"],
                    "case_ids": [c["id"] for c in b["cases"]],
                }
                for b in plan["banks"]
            ],
            "expected": plan["config"].get("expected", {}),
            "runtime_confirmation": plan["config"].get("runtime_confirmation", {}),
            "channels": plan["channels"],
            "query_parameters": plan["params"],
            "limits": plan["limits"],
            "semantic_assessment": "not_performed",
        },
    )
    end = min(
        time.monotonic() + plan["limits"]["run_budget_seconds"],
        time.monotonic()
        + (
            timestamp(plan["config"]["authorization"]["valid_until_utc"]) - dt.datetime.now(dt.UTC)
        ).total_seconds(),
    )
    results: list[dict] = []
    requests = 0
    stop_run = False
    for bank in plan["banks"]:
        for case in bank["cases"]:
            for channel in plan["channels"]:
                stopped = False
                thread = f"capture-{run_id}-{len(results):03d}-{channel.lower()}"
                row = {
                    "dataset": bank["name"],
                    "id": case["id"],
                    "channel": channel,
                    "reference_case": case["reference_case"],
                    "turns": [],
                }
                for index, turn in enumerate(case["turns"], 1):
                    record = {"turn": index, "reference_turn": turn, "status": "not_executed"}
                    if stopped or stop_run:
                        record["reason"] = "previous_turn_uncertain" if stopped else "run_stopped"
                        row["turns"].append(record)
                        continue
                    if time.monotonic() >= end or requests >= plan["limits"]["max_requests"]:
                        stop_run = True
                        record["reason"] = "run_budget_exhausted"
                        row["turns"].append(record)
                        continue
                    stem = f"{len(results):03d}-{channel.lower()}-{index:02d}"
                    body = {"question": turn["pregunta"], **plan["params"]}
                    if case["conversation"]:
                        body["thread_id"] = thread
                    deadline = min(end, time.monotonic() + plan["limits"]["request_budget_seconds"])
                    save(
                        output / (stem + ".intent.json"),
                        {
                            "run_id": run_id,
                            "dataset": bank["name"],
                            "id": case["id"],
                            "turn": index,
                            "channel": channel,
                            "state": "intent_before_send",
                            "request_sha256": sha256(json_bytes(body)),
                        },
                    )
                    requests += 1
                    observed = {"http_status": None, "bytes": 0}
                    started = time.monotonic()
                    try:
                        response = transport(
                            plan,
                            channel,
                            json_bytes(body),
                            token,
                            output / (stem + ".raw"),
                            deadline,
                            observed,
                        )
                        record.update(
                            {
                                "status": "complete",
                                "response": response,
                                "structural_observations": structural_observations(response),
                            }
                        )
                    except (Exception, KeyboardInterrupt) as exc:
                        code = (
                            exc.code
                            if isinstance(exc, ProtocolError)
                            else (str(exc) if isinstance(exc, CaptureError) else "transport_error")
                        )
                        record.update({"status": "uncertain", "error_code": code})
                        stopped = True
                        if isinstance(exc, KeyboardInterrupt):
                            stop_run = True
                    record.update(
                        {
                            "attempt_consumed": True,
                            "duration_seconds": time.monotonic() - started,
                            "observed": observed,
                        }
                    )
                    save(output / (stem + ".result.json"), record)
                    row["turns"].append(record)
                results.append(row)
    summary = {
        "run_id": run_id,
        "requests_attempted": requests,
        "planned_requests": plan["requests"],
        "status": "complete"
        if all(t["status"] == "complete" for r in results for t in r["turns"])
        else "partial",
        "semantic_assessment": "not_performed",
        "results": results,
    }
    save(output / "SUMMARY.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.config)
        if not args.execute:
            print(
                json.dumps(
                    {
                        "status": "validated_not_executed",
                        "pending": plan["pending"],
                        "cases": sum(len(b["cases"]) for b in plan["banks"]),
                        "requests": plan["requests"],
                        "network_calls": 0,
                        "token_read": False,
                    }
                )
            )
            return 0
        result = execute(plan)
        print(
            json.dumps(
                {"status": result["status"], "requests_attempted": result["requests_attempted"]}
            )
        )
        return 0 if result["status"] == "complete" else 2
    except (CaptureError, ProtocolError, OSError, ValueError, KeyError, TypeError) as exc:
        code = (
            exc.code
            if isinstance(exc, ProtocolError)
            else (str(exc) if isinstance(exc, CaptureError) else "local_input_or_execution_error")
        )
        print(json.dumps({"status": "blocked", "error_code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
