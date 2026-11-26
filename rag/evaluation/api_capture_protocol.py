"""Pure JSON/SSE decoding for the external ATLAS capture helper.

This module performs no file or network I/O and imports no repository code.
Protocol validity is separate from factual accuracy or citation support.
"""

from __future__ import annotations

import codecs
import copy
import json
import math

_MESSAGES = {
    "protocol_error": "Respuesta incompatible con el protocolo de captura.",
    "invalid_utf8": "La respuesta no contiene UTF-8 válido.",
    "invalid_json": "La respuesta no contiene JSON válido.",
    "duplicate_json_key": "El JSON contiene una clave duplicada.",
    "non_finite_json": "El JSON contiene un número no finito.",
    "invalid_payload": "La respuesta no tiene la estructura JSON esperada.",
    "invalid_answer": "La respuesta no contiene un texto de respuesta válido.",
    "invalid_sources": "La respuesta no contiene una lista de fuentes válida.",
    "invalid_source_group": "Un grupo de fuentes es incompatible con el contrato.",
    "invalid_source_fragment": "Un fragmento de fuente es incompatible con el contrato.",
    "invalid_source_indices": "Los índices globales de fuentes son incompatibles.",
    "invalid_route": "La ruta de consulta no es un valor admitido.",
    "invalid_context": "Los campos de contexto de la API son incompatibles.",
    "invalid_limits": "Los límites del capturador deben ser enteros positivos.",
    "invalid_chunk": "El capturador SSE requiere bloques de bytes.",
    "event_too_large": "Un evento SSE excedió el tamaño permitido.",
    "too_many_events": "El flujo SSE excedió la cantidad permitida de eventos.",
    "invalid_sse_event": "Un evento SSE no tiene la estructura esperada.",
    "unknown_sse_type": "El flujo contiene un tipo de evento SSE desconocido.",
    "sse_error_event": "La API emitió un evento SSE de error.",
    "duplicate_sources": "El flujo SSE contiene más de un evento de fuentes.",
    "tokens_after_sources": "El flujo SSE contiene texto después de las fuentes.",
    "missing_sources": "El flujo SSE no contiene el evento de fuentes requerido.",
    "missing_done": "El flujo SSE terminó sin el marcador de finalización.",
    "data_after_done": "El flujo SSE contiene datos después de la finalización.",
    "incomplete_event": "El flujo SSE terminó con un evento de datos incompleto.",
    "capture_failed": "El capturador SSE ya registró un error de protocolo.",
    "capture_finished": "El capturador SSE ya fue finalizado.",
}


class ProtocolError(Exception):
    """A protocol failure with a stable code and a fixed, content-free message."""

    def __init__(self, code: str = "protocol_error") -> None:
        self.code = code if code in _MESSAGES else "protocol_error"
        super().__init__(_MESSAGES[self.code])


def _parse_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ProtocolError("non_finite_json")
    return number


def _reject_constant(_value: str) -> None:
    raise ProtocolError("non_finite_json")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate_json_key")
        result[key] = value
    return result


def _load_json(text: str) -> object:
    try:
        value = json.loads(
            text,
            parse_float=_parse_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        if not _is_json(value):
            raise ProtocolError("invalid_json")
        return value
    except ProtocolError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ProtocolError("invalid_json") from None


def _is_json(value: object) -> bool:
    """Also reject non-finite numbers in directly supplied Python payloads."""
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            return False
        return True
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json(key) and _is_json(item) for key, item in value.items()
        )
    return False


def _metadata(value: object, error: str) -> dict:
    if not isinstance(value, dict):
        raise ProtocolError(error)
    return value


def normalize_payload(payload: object) -> dict:
    """Preserve public content and order fragments by their global index.

    No answer cleaning, semantic scoring, route inference or ID inference is
    performed. ``route_observed`` means a non-null route was actually provided.
    ``source_groups`` retains all original group/fragment metadata and fields.
    A missing or unusable metadata ID stays null in the convenience fields;
    its original value remains available in ``fragment_metadata``.
    """
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload")
    try:
        json_compatible = _is_json(payload)
    except RecursionError:
        raise ProtocolError("invalid_payload") from None
    if not json_compatible:
        raise ProtocolError("invalid_payload")

    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise ProtocolError("invalid_answer")
    groups = payload.get("sources")
    if not isinstance(groups, list):
        raise ProtocolError("invalid_sources")
    route = payload.get("query_route")
    if route is not None and (
        not isinstance(route, str)
        or route not in {"in_scope", "out_of_scope", "conversation", "needs_clarification"}
    ):
        raise ProtocolError("invalid_route")
    enriched = payload.get("enriched_query")
    if enriched is not None and not isinstance(enriched, str):
        raise ProtocolError("invalid_payload")
    for key in ("context_tokens", "context_limit"):
        if key in payload and type(payload[key]) is not int:
            raise ProtocolError("invalid_context")

    fragments: list[dict] = []
    indices: set[int] = set()
    for group in groups:
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("source"), str)
            or not isinstance(group.get("title"), str)
            or not isinstance(group.get("fragments"), list)
            or not group["fragments"]
        ):
            raise ProtocolError("invalid_source_group")
        doc_type = group.get("doc_type")
        if doc_type is not None and not isinstance(doc_type, str):
            raise ProtocolError("invalid_source_group")
        group_meta = _metadata(group.get("metadata", {}), "invalid_source_group")
        for fragment in group["fragments"]:
            if not isinstance(fragment, dict) or not isinstance(fragment.get("content"), str):
                raise ProtocolError("invalid_source_fragment")
            index = fragment.get("index")
            if type(index) is not int or index <= 0 or index in indices:
                raise ProtocolError("invalid_source_indices")
            indices.add(index)
            fragment_meta = _metadata(fragment.get("metadata", {}), "invalid_source_fragment")
            chunk_id = fragment_meta.get("chunk_id")
            metadata_id = fragment_meta.get("id")
            fragments.append(
                {
                    "index": index,
                    "source": group["source"],
                    "title": group["title"],
                    "doc_type": doc_type,
                    "group_metadata": copy.deepcopy(group_meta),
                    "fragment_metadata": copy.deepcopy(fragment_meta),
                    "content": fragment["content"],
                    "chunk_id": chunk_id if isinstance(chunk_id, str) and chunk_id else None,
                    "metadata_id": metadata_id
                    if isinstance(metadata_id, str) and metadata_id
                    else None,
                }
            )
    if indices != set(range(1, len(fragments) + 1)):
        raise ProtocolError("invalid_source_indices")
    fragments.sort(key=lambda item: item["index"])
    return {
        "answer": answer,
        "query_route": route,
        "route_observed": route is not None,
        "route_field_present": "query_route" in payload,
        "source_groups": copy.deepcopy(groups),
        "ordered_fragments": fragments,
        "enriched_query": enriched,
        "context_tokens": payload.get("context_tokens"),
        "context_limit": payload.get("context_limit"),
        "context_fields_present": [
            key for key in ("context_tokens", "context_limit") if key in payload
        ],
        "context_metric_scope": "api_history_estimate_not_full_prompt",
    }


def decode_json(raw: bytes) -> dict:
    """Decode a complete UTF-8 JSON response; do not accept duplicate keys."""
    if not isinstance(raw, bytes):
        raise ProtocolError("invalid_json")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ProtocolError("invalid_utf8") from None
    return normalize_payload(_load_json(text))


class SSECapture:
    """Incrementally decode a complete API SSE response without I/O.

    UTF-8 may be split across chunks. One initial BOM is accepted. LF, CRLF
    and CR line endings are accepted, including CRLF split across chunks.
    Size limits cover UTF-8 frame bytes including separators, excluding the
    optional stream BOM. ``event_count`` counts data frames, including DONE;
    comment/metadata-only frames do not count as data events. The transport
    driver must independently bound total response bytes and elapsed time.
    """

    def __init__(self, max_event_bytes: int = 262144, max_events: int = 4096) -> None:
        if (
            type(max_event_bytes) is not int
            or max_event_bytes <= 0
            or type(max_events) is not int
            or max_events <= 0
        ):
            raise ProtocolError("invalid_limits")
        self.max_event_bytes = max_event_bytes
        self.max_events = max_events
        self.event_count = 0
        self.done = False
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
        self._line_parts: list[str] = []
        self._pending_cr = False
        self._frame_bytes = 0
        self._data_lines: list[str] = []
        self._tokens: list[str] = []
        self._sources: dict | None = None
        self._statuses: list[dict] = []
        self._failed = False
        self._finished = False

    def _charge(self, byte_count: int) -> None:
        self._frame_bytes += byte_count
        if self._frame_bytes > self.max_event_bytes:
            raise ProtocolError("event_too_large")

    def _dispatch(self) -> None:
        if not self._data_lines:
            return
        data = "\n".join(self._data_lines)
        self._data_lines.clear()
        if self.done:
            raise ProtocolError("data_after_done")
        self.event_count += 1
        if self.event_count > self.max_events:
            raise ProtocolError("too_many_events")
        if data.strip() == "[DONE]":
            if self._sources is None:
                raise ProtocolError("missing_sources")
            self.done = True
            return
        payload = _load_json(data)
        if not isinstance(payload, dict):
            raise ProtocolError("invalid_sse_event")
        event_type = payload.get("type")
        if event_type == "error":
            raise ProtocolError("sse_error_event")
        if event_type == "token":
            if self._sources is not None:
                raise ProtocolError("tokens_after_sources")
            if not isinstance(payload.get("content"), str):
                raise ProtocolError("invalid_sse_event")
            self._tokens.append(payload["content"])
        elif event_type == "sources":
            if self._sources is not None:
                raise ProtocolError("duplicate_sources")
            if not isinstance(payload.get("sources"), list):
                raise ProtocolError("invalid_sources")
            self._sources = payload
        elif event_type == "status":
            self._statuses.append(payload)
        else:
            raise ProtocolError("unknown_sse_type")

    def _end_line(self, newline_bytes: int) -> None:
        self._charge(newline_bytes)
        line = "".join(self._line_parts)
        self._line_parts.clear()
        if not line:
            self._dispatch()
            self._frame_bytes = 0
            return
        if line.startswith(":"):
            return
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data_lines.append(value)
        # SSE event/id/retry and unknown SSE fields do not alter API data.

    def _consume(self, text: str) -> None:
        for char in text:
            if self._pending_cr:
                self._pending_cr = False
                self._end_line(2 if char == "\n" else 1)
                if char == "\n":
                    continue
            if char == "\r":
                self._pending_cr = True
            elif char == "\n":
                self._end_line(1)
            else:
                self._charge(1 if ord(char) < 128 else len(char.encode("utf-8")))
                self._line_parts.append(char)

    def _check_open(self) -> None:
        if self._failed:
            raise ProtocolError("capture_failed")
        if self._finished:
            raise ProtocolError("capture_finished")

    def feed(self, chunk: bytes) -> None:
        self._check_open()
        try:
            if not isinstance(chunk, bytes):
                raise ProtocolError("invalid_chunk")
            self._consume(self._decoder.decode(chunk, final=False))
        except UnicodeDecodeError:
            self._failed = True
            raise ProtocolError("invalid_utf8") from None
        except ProtocolError:
            self._failed = True
            raise

    def finish(self) -> dict:
        self._check_open()
        try:
            self._consume(self._decoder.decode(b"", final=True))
            if self._pending_cr:
                self._pending_cr = False
                self._end_line(1)
            if self._line_parts:
                # Process a final metadata/comment line but never dispatch an
                # unterminated data frame as a complete protocol event.
                self._end_line(0)
            if self._data_lines:
                raise ProtocolError("incomplete_event")
            if not self.done:
                raise ProtocolError("missing_done")
            if self._sources is None:
                raise ProtocolError("missing_sources")
            payload = {key: value for key, value in self._sources.items() if key != "type"}
            payload["answer"] = "".join(self._tokens)
            result = normalize_payload(payload)
            result.update(
                {
                    "sse_done": True,
                    "sse_event_count": self.event_count,
                    "sse_token_block_count": len(self._tokens),
                    "sse_status_events": copy.deepcopy(self._statuses),
                }
            )
            self._finished = True
            return result
        except UnicodeDecodeError:
            self._failed = True
            raise ProtocolError("invalid_utf8") from None
        except ProtocolError:
            self._failed = True
            raise
