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
# código productivo): 17 rutas, 21 operaciones. El panel de administración
# (routes/panel.py) agregó 5 rutas GET de solo lectura: 22 rutas, 26 operaciones.
# El ejercicio de validación (routes/participantes.py) agregó 5 rutas y 5
# operaciones: 27 rutas, 31 operaciones. La evaluación (routes/evaluacion.py)
# agregó 9 rutas y 9 operaciones: 36 rutas, 40 operaciones. El CSV de encuestas
# del panel suma 1: 37 rutas, 41 operaciones. Validar concordantes en lote
# (decisión 9 del orquestador) suma 1: 38 rutas, 42 operaciones. Auditoría (GET) y
# privacidad (GET y POST) suman 2 rutas y 3 operaciones: 40 rutas, 45 operaciones.
# Reunión del 20-oct: sale validar-concordantes (1) y entra la validación por
# evaluación (5 rutas, 6 operaciones): 44 rutas, 50 operaciones. Reasignar
# pendientes (E1) suma 1: 45 rutas, 51 operaciones. Práctica (T7): estado y
# archivar, 2 rutas: 47 rutas, 53 operaciones. Calendario (T5): GET/PUT del
# calendario y la ventana del participante: 49 rutas, 56 operaciones. Cierre del
# ejercicio (E6): 50 rutas, 57 operaciones. Encuesta ya respondida (J5-5): 51
# rutas, 58 operaciones.
_EXPECTED_ROUTES: dict[str, set[str]] = {
    "/api/admin/feedback": {"get"},
    "/api/admin/auditoria": {"get"},
    "/api/privacidad": {"get", "post"},
    "/api/admin/message-feedback": {"get"},
    "/api/admin/panel/conversaciones/{conversation_id}": {"get"},
    "/api/admin/panel/preguntas": {"get"},
    "/api/admin/panel/preguntas.csv": {"get"},
    "/api/admin/panel/resumen": {"get"},
    "/api/admin/panel/encuestas": {"get"},
    "/api/admin/panel/encuestas.csv": {"get"},
    "/api/admin/participantes": {"get"},
    "/api/evaluacion/bandeja": {"get"},
    "/api/evaluacion/catalogo": {"get"},
    "/api/evaluacion/reasignar": {"post"},
    "/api/evaluacion/practica": {"get"},
    "/api/evaluacion/calendario": {"get", "put"},
    "/api/evaluacion/cierre": {"post"},
    "/api/ejercicio/ventana": {"get"},
    "/api/ejercicio/encuesta": {"get"},
    "/api/evaluacion/practica/archivar": {"post"},
    "/api/evaluacion/validacion/bandeja": {"get"},
    "/api/evaluacion/validacion/evaluaciones/{evaluation_id}": {"get", "put"},
    "/api/evaluacion/validacion/evaluaciones/{evaluation_id}/comentarios": {"post"},
    "/api/evaluacion/validacion/lote": {"post"},
    "/api/evaluacion/validacion/preguntas/{message_id}/pertinencia": {"put"},
    "/api/evaluacion/exportar.xlsx": {"get"},
    "/api/evaluacion/premios": {"get"},
    "/api/evaluacion/premios/{nivel}/ganadora": {"put"},
    "/api/evaluacion/preguntas/{message_id}": {"get"},
    "/api/evaluacion/preguntas/{message_id}/final": {"put"},
    "/api/evaluacion/preguntas/{message_id}/mia": {"put"},
    "/api/evaluacion/resumen": {"get"},
    "/api/admin/participantes/catalogo": {"get"},
    "/api/admin/participantes/lote": {"post"},
    "/api/admin/participantes/{uid}": {"patch"},
    "/api/admin/participantes/{uid}/clave": {"post"},
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
    assert operation_count == 58


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
