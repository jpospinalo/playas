"""A1.4 — liberación de recursos propios al apagar la aplicación.

Antes de esta entrega, el ``lifespan`` de ``api/main.py`` no liberaba nada al
terminar: ni la sesión HTTP compartida del cliente de embeddings de Ollama
(``core/embeddings.py``), ni los singletons de retriever (cliente Chroma,
vectorstore, índice BM25 — ``core/retriever.py``), ni el engine SQLAlchemy
(``api/database.py``, dueño del pool de conexiones a la base de datos).

Estas pruebas cubren dos capas por separado:

  - ``close_retrievers()`` (``core/retriever.py``): resetea los tres
    singletons de módulo y cierra la sesión HTTP del cliente de embeddings
    compartido (``EMBEDDINGS``) — sin invocar ningún método privado o no
    documentado del cliente de Chroma, y sin fallar si se llama dos veces.
  - ``lifespan()`` (``api/main.py``): al terminar el bloque ``yield``
    (apagado normal) o al propagarse una excepción durante ese bloque
    (apagado por error), el ``try/finally`` debe llamar siempre a
    ``close_retrievers()`` y a ``engine.dispose()``.

Ninguna prueba aquí toca la red real: ``init_db``/``init_retrievers``/
``build_graph`` se sustituyen por dobles, y la sesión HTTP del cliente de
embeddings se reemplaza por un ``MagicMock`` antes de cualquier cierre.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import rag.api.main as main_module
import rag.core.retriever as retriever_module
from rag.core.retriever import close_retrievers


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_retriever_singletons():
    """Los tres singletons de retriever son estado de módulo compartido
    entre pruebas — se guardan y se restauran para no filtrar estado."""
    original_client = retriever_module._chroma_client
    original_vectorstore = retriever_module._chroma_vectorstore
    original_bm25 = retriever_module._bm25_base
    yield
    retriever_module._chroma_client = original_client
    retriever_module._chroma_vectorstore = original_vectorstore
    retriever_module._bm25_base = original_bm25


@pytest.fixture(autouse=True)
def _mock_embeddings_session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Reemplaza la sesión HTTP real del cliente de embeddings compartido por
    un mock — ninguna prueba de este archivo debe abrir una conexión real."""
    mock_session = MagicMock()
    monkeypatch.setattr(retriever_module.EMBEDDINGS._client, "_session", mock_session)
    return mock_session


@pytest.fixture(autouse=True)
def _reset_graph_singleton():
    """``main_module._graph`` es estado de módulo compartido entre pruebas
    (mismo patrón que ``test_readiness_endpoint.py``)."""
    original = main_module._graph
    yield
    main_module._graph = original


@pytest.fixture(autouse=True)
def _reset_app_state_graph():
    """C3 — ``main_module.app`` es el mismo singleton de FastAPI compartido
    por todo el proceso de pruebas; ``app.state.graph`` (poblado/reseteado
    por ``lifespan()``, ver C3) es estado mutable de ese singleton, con el
    mismo riesgo de fuga entre pruebas que ``_graph`` de arriba."""
    original = getattr(main_module.app.state, "graph", None)
    original_locks = getattr(main_module.app.state, "conversation_locks", None)
    yield
    main_module.app.state.graph = original
    main_module.app.state.conversation_locks = original_locks


@pytest.fixture(autouse=True)
def _mock_chroma_query_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def open_query():
        yield None

    monkeypatch.setattr(main_module, "open_chroma_query", open_query)


@pytest.fixture
def _chroma_http(monkeypatch: pytest.MonkeyPatch):
    """Ejercita el contexto HTTPX real con el catálogo de Chroma en memoria."""
    settings = SimpleNamespace(
        chroma_client_auth_provider=None,
        chroma_server_host="chroma.invalid",
        chroma_server_http_port=8000,
        chroma_server_ssl_enabled=False,
        chroma_server_ssl_verify=None,
        chroma_server_headers=None,
        chroma_server_api_default_path="/api/v2",
        chroma_http_max_connections=None,
        chroma_http_max_keepalive_connections=None,
        chroma_http_keepalive_secs=40.0,
    )
    sdk = SimpleNamespace(
        tenant="tenant-fixture", database="database-fixture", get_settings=lambda: settings
    )
    clients: list[httpx.AsyncClient] = []
    lookup = MagicMock(
        side_effect=lambda request: httpx.Response(
            200, json={"id": "11111111-2222-4333-8444-555555555555"}
        )
    )
    close = AsyncMock()
    async_client = httpx.AsyncClient

    def create_client(**options):
        transport = httpx.MockTransport(lookup)
        monkeypatch.setattr(transport, "aclose", close)
        client = async_client(**options, transport=transport)
        clients.append(client)
        return client

    monkeypatch.setattr(retriever_module, "_get_chroma_client", lambda: sdk)
    monkeypatch.setattr(retriever_module, "CHROMA_HOST", "chroma.invalid")
    monkeypatch.setattr(retriever_module, "CHROMA_PORT", 8000)
    monkeypatch.setattr(retriever_module, "CHROMA_COLLECTION_NAME", "collection-fixture")
    monkeypatch.setattr(retriever_module, "CHROMA_QUERY_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(retriever_module.httpx, "AsyncClient", create_client)
    monkeypatch.setattr(main_module, "open_chroma_query", retriever_module.open_chroma_query)
    return settings, clients, lookup, close


# ---------------------------------------------------------------------------
# close_retrievers() — retriever.py
# ---------------------------------------------------------------------------


def test_close_retrievers_resets_all_three_singletons(_mock_embeddings_session) -> None:
    retriever_module._chroma_client = object()
    retriever_module._chroma_vectorstore = object()
    retriever_module._bm25_base = object()

    close_retrievers()

    assert retriever_module._chroma_client is None
    assert retriever_module._chroma_vectorstore is None
    assert retriever_module._bm25_base is None


def test_close_retrievers_closes_the_embeddings_http_session(
    _mock_embeddings_session: MagicMock,
) -> None:
    close_retrievers()

    _mock_embeddings_session.close.assert_called_once()


def test_close_retrievers_is_idempotent(_mock_embeddings_session: MagicMock) -> None:
    """Llamar dos veces (p.ej. un doble apagado) no debe fallar."""
    close_retrievers()
    close_retrievers()

    assert retriever_module._chroma_client is None
    assert retriever_module._chroma_vectorstore is None
    assert retriever_module._bm25_base is None
    assert _mock_embeddings_session.close.call_count == 2


def test_close_retrievers_works_when_singletons_were_never_initialized(
    _mock_embeddings_session: MagicMock,
) -> None:
    """Apagar un proceso que nunca llegó a llamar init_retrievers() (p.ej.
    falló antes) no debe fallar por desreferenciar un singleton en None."""
    retriever_module._chroma_client = None
    retriever_module._chroma_vectorstore = None
    retriever_module._bm25_base = None

    close_retrievers()  # no debe lanzar

    assert retriever_module._chroma_client is None


def test_close_retrievers_makes_no_network_call(_mock_embeddings_session: MagicMock) -> None:
    close_retrievers()

    _mock_embeddings_session.post.assert_not_called()
    _mock_embeddings_session.get.assert_not_called()


# ---------------------------------------------------------------------------
# lifespan() — main.py: apagado normal
# ---------------------------------------------------------------------------


def _patch_lifespan_startup(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    """Sustituye las tres llamadas de arranque del lifespan por dobles que no
    tocan red/DB real, y devuelve (init_db_mock, engine_dispose_mock) para
    que cada prueba pueda inspeccionarlos.

    ``init_db`` y ``engine`` se importan de forma perezosa DENTRO de
    ``lifespan()`` (``from rag.api.database import engine, init_db``), así
    que parchear el módulo real (``rag.api.database``) sí los intercepta.
    ``init_retrievers``, en cambio, se importó a nivel de módulo en
    ``api/main.py`` (``from rag.core.retriever import ... init_retrievers``)
    — el nombre que ``lifespan()`` resuelve en tiempo de ejecución vive en el
    namespace de ``main_module``, no en ``retriever_module``, así que hay que
    parchearlo ahí para que surta efecto.

    ``AsyncEngine.dispose`` no se puede parchear como atributo de instancia
    (SQLAlchemy lo expone de solo lectura); en su lugar se sustituye el
    objeto ``engine`` completo por un doble mínimo con un ``dispose()``
    async — la importación perezosa dentro de ``lifespan()`` recoge el
    reemplazo en la siguiente llamada.
    """
    import rag.api.database as database_module
    import rag.core.agent as agent_module

    init_db_mock = AsyncMock()
    monkeypatch.setattr(database_module, "init_db", init_db_mock)
    monkeypatch.setattr(main_module, "init_retrievers", MagicMock())
    monkeypatch.setattr(agent_module, "build_graph", MagicMock(return_value=object()))

    engine_dispose_mock = AsyncMock()
    fake_engine = MagicMock()
    fake_engine.dispose = engine_dispose_mock
    monkeypatch.setattr(database_module, "engine", fake_engine)

    return init_db_mock, engine_dispose_mock


@pytest.mark.anyio
async def test_lifespan_normal_shutdown_disposes_engine_and_closes_retrievers(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    _patch_lifespan_startup(monkeypatch)
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)

    async with main_module.lifespan(main_module.app):
        pass  # apagado limpio: sale del bloque `async with` sin excepción

    close_retrievers_mock.assert_called_once()


@pytest.mark.anyio
async def test_lifespan_calls_engine_dispose_on_normal_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    _init_db_mock, engine_dispose_mock = _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        pass

    engine_dispose_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_lifespan_still_disposes_engine_when_server_body_raises(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    """Si algo dentro del bloque `async with lifespan(app): ...` (el
    "cuerpo del servidor", entre el arranque y el apagado) lanza una
    excepción, el try/finally debe liberar los recursos igual — no solo en
    el camino feliz."""
    _init_db_mock, engine_dispose_mock = _patch_lifespan_startup(monkeypatch)
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)

    with pytest.raises(RuntimeError, match="fallo simulado del servidor"):
        async with main_module.lifespan(main_module.app):
            raise RuntimeError("fallo simulado del servidor")

    engine_dispose_mock.assert_awaited_once()
    close_retrievers_mock.assert_called_once()


@pytest.mark.anyio
async def test_lifespan_double_shutdown_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    """Dos ciclos completos de arranque/apagado consecutivos (como podría
    ocurrir entre pruebas que reutilizan la misma app) no deben fallar por
    liberar dos veces los mismos recursos."""
    _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        pass
    async with main_module.lifespan(main_module.app):
        pass  # no debe lanzar


@pytest.mark.anyio
async def test_lifespan_makes_no_real_network_or_db_call(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    """Confirma que el arranque/apagado completo de esta prueba pasa
    exclusivamente por los dobles — ninguna llamada real a Chroma, Ollama o
    la base de datos."""
    init_db_mock, engine_dispose_mock = _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        pass

    init_db_mock.assert_awaited_once()
    engine_dispose_mock.assert_awaited_once()
    _mock_embeddings_session.post.assert_not_called()
    _mock_embeddings_session.get.assert_not_called()


# ---------------------------------------------------------------------------
# C3 — el try/finally cubre TODO el arranque, no solo el bloque yield: un
# fallo en cualquiera de los tres pasos (init_db, init_retrievers,
# build_graph) debe liberar igual lo que ya se hubiera abierto.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lifespan_releases_resources_when_init_db_fails(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    import rag.api.database as database_module
    import rag.core.agent as agent_module

    monkeypatch.setattr(
        database_module, "init_db", AsyncMock(side_effect=RuntimeError("fallo simulado init_db"))
    )
    monkeypatch.setattr(main_module, "init_retrievers", MagicMock())
    monkeypatch.setattr(agent_module, "build_graph", MagicMock(return_value=object()))
    engine_dispose_mock = AsyncMock()
    fake_engine = MagicMock()
    fake_engine.dispose = engine_dispose_mock
    monkeypatch.setattr(database_module, "engine", fake_engine)
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)

    with pytest.raises(RuntimeError, match="fallo simulado init_db"):
        async with main_module.lifespan(main_module.app):
            pytest.fail("no debía llegar al yield: init_db falló antes")

    close_retrievers_mock.assert_called_once()
    engine_dispose_mock.assert_awaited_once()
    assert main_module._graph is None
    assert main_module.app.state.graph is None


@pytest.mark.anyio
async def test_lifespan_releases_resources_when_init_retrievers_fails(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    import rag.api.database as database_module
    import rag.core.agent as agent_module

    monkeypatch.setattr(database_module, "init_db", AsyncMock())
    monkeypatch.setattr(
        main_module,
        "init_retrievers",
        MagicMock(side_effect=RuntimeError("fallo simulado init_retrievers")),
    )
    monkeypatch.setattr(agent_module, "build_graph", MagicMock(return_value=object()))
    engine_dispose_mock = AsyncMock()
    fake_engine = MagicMock()
    fake_engine.dispose = engine_dispose_mock
    monkeypatch.setattr(database_module, "engine", fake_engine)
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)

    with pytest.raises(RuntimeError, match="fallo simulado init_retrievers"):
        async with main_module.lifespan(main_module.app):
            pytest.fail("no debía llegar al yield: init_retrievers falló antes")

    close_retrievers_mock.assert_called_once()
    engine_dispose_mock.assert_awaited_once()
    assert main_module._graph is None
    assert main_module.app.state.graph is None


@pytest.mark.anyio
async def test_lifespan_releases_resources_when_build_graph_fails(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    import rag.api.database as database_module
    import rag.core.agent as agent_module

    monkeypatch.setattr(database_module, "init_db", AsyncMock())
    monkeypatch.setattr(main_module, "init_retrievers", MagicMock())
    monkeypatch.setattr(
        agent_module,
        "build_graph",
        MagicMock(side_effect=RuntimeError("fallo simulado build_graph")),
    )
    engine_dispose_mock = AsyncMock()
    fake_engine = MagicMock()
    fake_engine.dispose = engine_dispose_mock
    monkeypatch.setattr(database_module, "engine", fake_engine)
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)

    with pytest.raises(RuntimeError, match="fallo simulado build_graph"):
        async with main_module.lifespan(main_module.app):
            pytest.fail("no debía llegar al yield: build_graph falló antes")

    close_retrievers_mock.assert_called_once()
    engine_dispose_mock.assert_awaited_once()
    assert main_module._graph is None
    assert main_module.app.state.graph is None


@pytest.mark.anyio
async def test_lifespan_still_disposes_engine_when_close_retrievers_itself_fails(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    """C3 — engine.dispose() debe ejecutarse incluso si close_retrievers()
    falla: su propio try/finally anidado no debe dejar que un fallo ahí
    impida cerrar el pool de conexiones a la base de datos."""
    _init_db_mock, engine_dispose_mock = _patch_lifespan_startup(monkeypatch)
    monkeypatch.setattr(
        main_module,
        "close_retrievers",
        MagicMock(side_effect=RuntimeError("fallo simulado close_retrievers")),
    )

    with pytest.raises(RuntimeError, match="fallo simulado close_retrievers"):
        async with main_module.lifespan(main_module.app):
            pass

    engine_dispose_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# C3 — _graph y app.state.graph: mismo objeto durante el lifespan, ambos
# None al salir por cualquier camino.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lifespan_sets_app_state_graph_to_the_same_object_as_module_graph(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        assert main_module._graph is not None
        assert main_module.app.state.graph is main_module._graph
        assert main_module.app.state.conversation_locks is main_module.CONVERSATION_LOCKS


@pytest.mark.anyio
async def test_lifespan_resets_both_graph_references_to_none_after_normal_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        pass

    assert main_module._graph is None
    assert main_module.app.state.graph is None
    assert main_module.app.state.conversation_locks is None


@pytest.mark.anyio
async def test_lifespan_resets_both_graph_references_to_none_when_server_body_raises(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    _patch_lifespan_startup(monkeypatch)

    with pytest.raises(RuntimeError, match="fallo simulado del servidor"):
        async with main_module.lifespan(main_module.app):
            raise RuntimeError("fallo simulado del servidor")

    assert main_module._graph is None
    assert main_module.app.state.graph is None
    assert main_module.app.state.conversation_locks is None


@pytest.mark.anyio
async def test_lifespan_double_cycle_does_not_reuse_a_closed_graph(
    monkeypatch: pytest.MonkeyPatch,
    _mock_embeddings_session: MagicMock,
) -> None:
    """Dos ciclos consecutivos de arranque/apagado no deben fallar. Tras el
    primer ciclo, ambas referencias quedan en ``None`` (nada "cerrado" queda
    accesible); el segundo ciclo vuelve a compilar y a poblar ambas
    referencias con normalidad, sin heredar estado del primero."""
    _patch_lifespan_startup(monkeypatch)

    async with main_module.lifespan(main_module.app):
        pass
    assert main_module._graph is None
    assert main_module.app.state.graph is None

    async with main_module.lifespan(main_module.app):
        second_graph = main_module._graph
        assert second_graph is not None
        assert main_module.app.state.graph is second_graph
    assert main_module._graph is None
    assert main_module.app.state.graph is None


def test_chroma_http_lifespan_uses_distinct_clients_across_event_loops(
    monkeypatch: pytest.MonkeyPatch, _chroma_http
) -> None:
    import rag.core.agent as agent_module

    _init_db_mock, engine_dispose = _patch_lifespan_startup(monkeypatch)
    _settings, clients, lookup, close = _chroma_http

    async def cycle() -> None:
        async with main_module.lifespan(main_module.app):
            adapter = agent_module.build_graph.call_args.kwargs["chroma_query"]
            assert adapter.client is clients[-1]
            assert adapter.collection_url == (
                "tenants/tenant-fixture/databases/database-fixture/collections/"
                "11111111-2222-4333-8444-555555555555/query"
            )
            assert not clients[-1].is_closed
        assert clients[-1].is_closed
        assert main_module._graph is None
        assert main_module.app.state.graph is None

    asyncio.run(cycle())
    asyncio.run(cycle())

    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert lookup.call_count == close.await_count == engine_dispose.await_count == 2
    for call in lookup.call_args_list:
        (request,) = call.args
        assert request.method == "GET"
        assert (
            request.url.path
            == "/api/v2/tenants/tenant-fixture/databases/database-fixture/collections/collection-fixture"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["catálogo", "compilación", "cierre HTTP"])
async def test_chroma_http_lifespan_frees_resources_after_failure(
    monkeypatch: pytest.MonkeyPatch, _chroma_http, failure: str
) -> None:
    import rag.core.agent as agent_module

    _init_db_mock, engine_dispose = _patch_lifespan_startup(monkeypatch)
    _settings, clients, lookup, close = _chroma_http
    close_retrievers_mock = MagicMock()
    monkeypatch.setattr(main_module, "close_retrievers", close_retrievers_mock)
    error = RuntimeError(f"fallo simulado de {failure}")
    if failure == "catálogo":
        lookup.side_effect = error
    elif failure == "compilación":
        agent_module.build_graph.side_effect = error
    else:
        close.side_effect = error

    with pytest.raises(RuntimeError, match=str(error)):
        async with main_module.lifespan(main_module.app):
            assert failure == "cierre HTTP"

    (client,) = clients
    assert client.is_closed
    close.assert_awaited_once()
    close_retrievers_mock.assert_called_once()
    engine_dispose.assert_awaited_once()
    assert main_module._graph is None
    assert main_module.app.state.graph is None


@pytest.mark.anyio
async def test_lifespan_with_sdk_auth_keeps_legacy_graph(
    monkeypatch: pytest.MonkeyPatch, _chroma_http
) -> None:
    import rag.core.agent as agent_module

    _patch_lifespan_startup(monkeypatch)
    settings, clients, lookup, close = _chroma_http
    settings.chroma_client_auth_provider = "auth-fixture"

    async with main_module.lifespan(main_module.app):
        agent_module.build_graph.assert_called_once_with(chroma_query=None)

    assert clients == []
    lookup.assert_not_called()
    close.assert_not_awaited()
