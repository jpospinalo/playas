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

from unittest.mock import AsyncMock, MagicMock

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
    yield
    main_module.app.state.graph = original


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
