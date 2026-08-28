"""T0 §5.4 — salvaguardas del script de carga (``scripts/load_test.py``).

Nunca abre una conexión de red real: ``usuario()``/``main()`` se ejercitan
con un cliente HTTP falso que imita la forma async-context-manager de
``httpx.AsyncClient.stream()``.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import load_test  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# _is_local / confirm_remote_target
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://0.0.0.0:8080",
        "http://[::1]:8080",
    ],
)
def test_is_local_recognizes_local_hosts(url: str) -> None:
    assert load_test._is_local(url) is True


def test_is_local_rejects_remote_host() -> None:
    assert load_test._is_local("http://rag-playas-prod-alb.example.com") is False


def test_confirm_remote_target_always_allows_local_host() -> None:
    ok = load_test.confirm_remote_target(
        "http://localhost:8080", allow_remote=False, interactive=False
    )
    assert ok is True


def test_confirm_remote_target_cancels_without_allow_remote() -> None:
    calls: list[str] = []
    ok = load_test.confirm_remote_target(
        "http://example.com",
        allow_remote=False,
        interactive=True,
        read_input=lambda p: calls.append(p) or "example.com",
    )
    assert ok is False
    assert calls == []  # ni siquiera se pregunta


def test_confirm_remote_target_cancels_when_not_interactive() -> None:
    calls: list[str] = []
    ok = load_test.confirm_remote_target(
        "http://example.com",
        allow_remote=True,
        interactive=False,
        read_input=lambda p: calls.append(p) or "example.com",
    )
    assert ok is False
    assert calls == []


def test_confirm_remote_target_cancels_on_mismatched_confirmation() -> None:
    ok = load_test.confirm_remote_target(
        "http://example.com",
        allow_remote=True,
        interactive=True,
        read_input=lambda _: "otro-host.com",
    )
    assert ok is False


def test_confirm_remote_target_accepts_exact_host_match() -> None:
    ok = load_test.confirm_remote_target(
        "http://example.com",
        allow_remote=True,
        interactive=True,
        read_input=lambda _: "example.com",
    )
    assert ok is True


# ---------------------------------------------------------------------------
# _resolve_token
# ---------------------------------------------------------------------------


def test_resolve_token_prefers_cli_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_LOAD_TEST_TOKEN", "env-token")
    assert load_test._resolve_token("cli-token", allow_unauthenticated=False) == "cli-token"


def test_resolve_token_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_LOAD_TEST_TOKEN", "env-token")
    assert load_test._resolve_token(None, allow_unauthenticated=False) == "env-token"


def test_resolve_token_missing_without_override_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_LOAD_TEST_TOKEN", raising=False)
    assert load_test._resolve_token(None, allow_unauthenticated=False) is None


def test_resolve_token_missing_with_override_returns_none_but_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_LOAD_TEST_TOKEN", raising=False)
    assert load_test._resolve_token(None, allow_unauthenticated=True) is None


# ---------------------------------------------------------------------------
# _percentiles
# ---------------------------------------------------------------------------


def test_percentiles_empty() -> None:
    assert load_test._percentiles([]) == {}


def test_percentiles_single_value() -> None:
    assert load_test._percentiles([2.5]) == {"p50": 2.5, "p95": 2.5, "p99": 2.5}


def test_percentiles_monotonic_order() -> None:
    valores = [float(v) for v in range(1, 101)]  # 1..100
    p = load_test._percentiles(valores)
    assert p["p50"] <= p["p95"] <= p["p99"]
    assert min(valores) <= p["p50"]
    assert p["p99"] <= max(valores)


# ---------------------------------------------------------------------------
# usuario() / main() — cliente HTTP falso, nunca red real
# ---------------------------------------------------------------------------


class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def __aenter__(self) -> _FakeStreamResponse:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeAsyncClient:
    """Sustituye a httpx.AsyncClient: nunca abre una conexión real.

    ``stream()`` es un método normal (no async) que devuelve un async
    context manager, igual que en httpx real.
    """

    def __init__(self, response: _FakeStreamResponse | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kwargs})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _sse(payload: str) -> str:
    return f"data: {payload}"


@pytest.mark.anyio
async def test_usuario_completo_reports_status_and_token_timings() -> None:
    lines = [
        _sse('{"type": "status", "stage": "retrieve"}'),
        _sse('{"type": "token", "content": "hola"}'),
        _sse('{"type": "sources", "sources": []}'),
        "data: [DONE]",
    ]
    response = _FakeStreamResponse(200, lines)
    client = _FakeAsyncClient(response)

    result = await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token="tok"
    )

    assert result["completo"] is True
    assert result["status"] == 200
    assert result["primer_evento_estado"] is not None
    assert result["primera_fraccion_respuesta"] is not None
    assert result["error"] is None
    # el header de autorización se envía cuando hay token
    assert client.calls[0]["headers"] == {"Authorization": "Bearer tok"}


@pytest.mark.anyio
async def test_usuario_without_token_sends_no_authorization_header() -> None:
    response = _FakeStreamResponse(200, ["data: [DONE]"])
    client = _FakeAsyncClient(response)

    await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token=None
    )

    assert client.calls[0]["headers"] == {}


@pytest.mark.anyio
async def test_usuario_http_401_reports_error_without_raising() -> None:
    response = _FakeStreamResponse(401, [])
    client = _FakeAsyncClient(response)

    result = await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token=None
    )

    assert result["completo"] is False
    assert result["error"] == "HTTP 401"


@pytest.mark.anyio
async def test_usuario_incomplete_stream_without_done_or_error() -> None:
    lines = [_sse('{"type": "token", "content": "hola"}')]
    response = _FakeStreamResponse(200, lines)
    client = _FakeAsyncClient(response)

    result = await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token="tok"
    )

    assert result["completo"] is False
    assert result["error"] is None


@pytest.mark.anyio
async def test_usuario_stream_error_event_marks_failure() -> None:
    lines = [_sse('{"type": "error", "detail": "boom"}')]
    response = _FakeStreamResponse(200, lines)
    client = _FakeAsyncClient(response)

    result = await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token="tok"
    )

    assert result["completo"] is False
    assert result["error"] is not None
    assert "boom" in result["error"]


@pytest.mark.anyio
async def test_usuario_connection_exception_is_captured_as_error() -> None:
    client = _FakeAsyncClient(RuntimeError("conexión rechazada"))

    result = await load_test.usuario(
        0, client, timeout=5.0, stream_url="http://x/api/query/stream", token="tok"
    )

    assert result["completo"] is False
    assert "conexión rechazada" in (result["error"] or "")


# ---------------------------------------------------------------------------
# run_cli — orquestación de flags de seguridad, sin red real
# ---------------------------------------------------------------------------


def test_run_cli_requires_url_argument() -> None:
    with pytest.raises(SystemExit):
        load_test.run_cli([])


def test_run_cli_cancels_on_remote_host_without_allow_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_LOAD_TEST_TOKEN", "tok")
    exit_code = load_test.run_cli(["--url", "http://example.com", "--users", "1"])
    assert exit_code == 1


def test_run_cli_cancels_when_token_missing_and_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_LOAD_TEST_TOKEN", raising=False)
    exit_code = load_test.run_cli(["--url", "http://localhost:8080", "--users", "1"])
    assert exit_code == 1
