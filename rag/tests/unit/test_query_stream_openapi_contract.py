"""Contrato OpenAPI de `/api/query/stream`: el 200 debe declarar
`text/event-stream`, no `application/json`.

Antes de esta corrección, `app.openapi()` declaraba el `200` de esta ruta
como `application/json` con un schema vacío (`{}`) — un artefacto del
comportamiento por defecto de FastAPI cuando una ruta no tiene
`response_model` ni anotación de retorno, que nunca reflejó lo que el
endpoint realmente envía (`media_type="text/event-stream"`, ver
`_ResourceManagedStreamingResponse` en `rag/api/main.py`). Esta corrección
es puramente de documentación: no cambia rutas, parámetros, payloads,
código de estado, ni los eventos SSE reales.

Estas pruebas fijan el contrato esperado — no comparan contra un JSON
capturado externamente (frágil, no reproducible en CI) — para que un
cambio futuro que reintroduzca `application/json` en el 200 de streaming,
o que borre por accidente una respuesta de error en otra ruta, rompa aquí.
"""

from __future__ import annotations

from rag.api.main import app

# Conjunto de rutas confirmado en la línea base (capturada antes de tocar
# código productivo): 17 rutas, 21 operaciones.
_EXPECTED_ROUTES: dict[str, set[str]] = {
    "/api/admin/feedback": {"get"},
    "/api/admin/message-feedback": {"get"},
    "/api/admin/users": {"get", "post"},
    "/api/admin/users/{uid}/password": {"patch"},
    "/api/auth/login": {"post"},
    "/api/auth/me": {"get"},
    "/api/auth/register": {"post"},
    "/api/conversations": {"get", "post"},
    "/api/conversations/generate-title": {"post"},
    "/api/conversations/{conversation_id}": {"delete", "patch"},
    "/api/conversations/{conversation_id}/messages": {"get", "post"},
    "/api/feedback": {"post"},
    "/api/feedback/message": {"post"},
    "/api/health": {"get"},
    "/api/query": {"post"},
    "/api/query/stream": {"post"},
    "/api/ready": {"get"},
}


def _schema() -> dict:
    return app.openapi()


def test_route_and_operation_count_matches_expected_contract() -> None:
    schema = _schema()
    paths = schema["paths"]

    actual_routes = {path: set(methods.keys()) for path, methods in paths.items()}
    assert actual_routes == _EXPECTED_ROUTES

    operation_count = sum(len(methods) for methods in paths.values())
    assert operation_count == 21


def test_query_stream_declares_text_event_stream_and_not_json() -> None:
    schema = _schema()
    responses = schema["paths"]["/api/query/stream"]["post"]["responses"]

    assert "200" in responses
    content = responses["200"]["content"]
    assert content == {"text/event-stream": {"schema": {"type": "string"}}}
    assert "application/json" not in content


def test_query_stream_keeps_its_validation_error_response() -> None:
    schema = _schema()
    responses = schema["paths"]["/api/query/stream"]["post"]["responses"]

    assert "422" in responses
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }


def test_query_stream_request_schema_is_unchanged() -> None:
    """El único cambio esperado es la respuesta; el payload que el cliente
    envía (`QueryRequest`) debe seguir siendo exactamente el mismo."""
    schema = _schema()
    request_body = schema["paths"]["/api/query/stream"]["post"]["requestBody"]

    assert request_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/QueryRequest"
    }


def test_sibling_json_endpoint_is_unaffected() -> None:
    """`/api/query` (no-streaming, hermano directo de `/api/query/stream`)
    debe seguir declarando `application/json` con su schema real — la
    corrección del 200 de streaming no debe filtrarse a ninguna otra ruta."""
    schema = _schema()
    responses = schema["paths"]["/api/query"]["post"]["responses"]

    assert responses["200"]["content"] == {
        "application/json": {"schema": {"$ref": "#/components/schemas/QueryResponse"}}
    }
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }


def test_no_error_response_disappeared_from_any_operation() -> None:
    """Ninguna operación pierde su respuesta 422 existente por el cambio en
    `/api/query/stream` (p. ej. por un `responses=` mal fusionado)."""
    schema = _schema()
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"post", "patch"}:
                continue
            # Las rutas con parámetros/JSON validado por pydantic siempre
            # deben conservar su 422 autogenerado por FastAPI.
            assert "422" in operation["responses"], f"{method.upper()} {path} perdió su 422"
