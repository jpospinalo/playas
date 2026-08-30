"""A4.1 — filtros, conteo, paginación y agregación de feedback en SQL.

Antes: `list_feedback`/`list_message_feedback` cargaban a Python toda la
tabla ya filtrada por fecha, y ahí hacían el resto — filtro de rating,
conteo, promedio/distribución y el `[start:start+page_size]` de paginación.
Con miles de filas eso recorre toda la tabla en cada solicitud sin importar
`page_size`. Ahora los tres se ejecutan en SQL (`_rating_dim` en
`routes/admin.py`) sobre EXACTAMENTE las mismas condiciones `where`, y el
promedio/distribución se calculan sobre el conjunto filtrado COMPLETO, no
solo sobre la página — este archivo prueba justamente eso: que paginar no
cambia `total`/`avg_ratings`/`distributions`, y que estos coinciden con un
cálculo de referencia hecho en Python sobre los datos sembrados.

La equivalencia SQLite/PostgreSQL en sí (mismo resultado en ambos motores
para las mismas condiciones JSON, incluyendo el `coalesce(..., 0)` para una
clave de rating ausente) se verificó aparte, manualmente, contra un
PostgreSQL real levantado para esa verificación — no vive en este archivo
porque CI no tiene PostgreSQL disponible (ver .github/workflows/ci.yml);
este archivo cubre el comportamiento real contra SQLite, el motor que sí
corre en CI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from rag.api.models import Base, Feedback, MessageFeedback, User
from rag.api.routes.admin import list_feedback, list_message_feedback

_ADMIN = {"sub": "admin-1", "role": "admin"}
_BASE = datetime(2024, 6, 1, tzinfo=UTC)

_pending_engines: list[AsyncEngine] = []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _dispose_test_db_engines() -> Iterator[None]:
    yield
    if not _pending_engines:
        return
    engines, _pending_engines[:] = list(_pending_engines), []

    async def _dispose_all() -> None:
        for engine in engines:
            await engine.dispose()

    asyncio.run(_dispose_all())


async def _fresh_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


# 12 filas con ratings variados — deliberadamente NO en orden de `overall`
# ni agrupadas, para que un bug de filtro/orden/paginado no pase
# desapercibido por casualidad del orden de siembra.
_FEEDBACK_RATINGS = [
    {"tone": 5, "length": 5, "usability": 5, "overall": 5},
    {"tone": 1, "length": 2, "usability": 3, "overall": 1},
    {"tone": 3, "length": 3, "usability": 3, "overall": 3},
    {"tone": 4, "length": 4, "usability": 4, "overall": 4},
    {"tone": 2, "length": 2, "usability": 2, "overall": 2},
    {"tone": 5, "length": 5, "usability": 5, "overall": 5},
    {"tone": 1, "length": 1, "usability": 1, "overall": 1},
    {"tone": 3, "length": 4, "usability": 5, "overall": 4},
    {"tone": 2, "length": 3, "usability": 4, "overall": 3},
    {"tone": 5, "length": 4, "usability": 3, "overall": 4},
    {"tone": 4, "length": 5, "usability": 4, "overall": 5},
    {"tone": 2, "length": 2, "usability": 2, "overall": 2},
]


def _reference_aggregation(ratings_list: list[dict], dims: list[str]) -> tuple[dict, dict]:
    """Mismo cálculo que el código Python ANTERIOR a A4.1 — usado aquí solo
    como oráculo independiente para verificar que la versión SQL da el
    mismo resultado, no como implementación."""
    total = len(ratings_list)
    distributions = {d: {str(v): 0 for v in range(1, 6)} for d in dims}
    sums = {d: 0.0 for d in dims}
    for ratings in ratings_list:
        for d in dims:
            val = (ratings or {}).get(d, 0)
            if 1 <= val <= 5:
                distributions[d][str(val)] += 1
                sums[d] += val
    avg = {d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in dims}
    return avg, distributions


async def _seed_feedback(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        session.add(User(id="u1", email="u1@example.com", password_hash="x", role="user"))
        await session.commit()
    async with session_factory() as session:
        session.add_all(
            [
                Feedback(
                    id=f"fb-{i}",
                    user_id="u1",
                    ratings=ratings,
                    created_at=_BASE + timedelta(hours=i),
                )
                for i, ratings in enumerate(_FEEDBACK_RATINGS)
            ]
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Filtro de rating en SQL (min_overall/max_overall)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_min_overall_filters_in_sql_not_just_in_python() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=4,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    expected_ids = {f"fb-{i}" for i, r in enumerate(_FEEDBACK_RATINGS) if r["overall"] >= 4}
    assert {item.id for item in response.items} == expected_ids
    assert response.total == len(expected_ids)


@pytest.mark.anyio
async def test_max_overall_filters_in_sql() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=None,
            max_overall=2,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    expected_ids = {f"fb-{i}" for i, r in enumerate(_FEEDBACK_RATINGS) if r["overall"] <= 2}
    assert {item.id for item in response.items} == expected_ids


@pytest.mark.anyio
async def test_min_and_max_overall_combine_as_a_range() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=2,
            max_overall=4,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    expected_ids = {f"fb-{i}" for i, r in enumerate(_FEEDBACK_RATINGS) if 2 <= r["overall"] <= 4}
    assert {item.id for item in response.items} == expected_ids


# ---------------------------------------------------------------------------
# total/avg_ratings/distributions sobre el conjunto filtrado COMPLETO, no
# solo la página — el núcleo de A4.1.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_total_avg_and_distributions_cover_the_full_filtered_set_not_the_page() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        response = await list_feedback(
            page=1,
            page_size=3,  # página pequeña — el total sembrado es 12
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    assert len(response.items) == 3  # la página sí respeta page_size
    assert response.total == 12  # pero total cuenta TODO el conjunto filtrado

    expected_avg, expected_dist = _reference_aggregation(
        _FEEDBACK_RATINGS, ["tone", "length", "usability", "overall"]
    )
    assert response.avg_ratings.model_dump() == expected_avg
    assert response.distributions == expected_dist


@pytest.mark.anyio
async def test_avg_and_distributions_are_identical_across_different_pages() -> None:
    """Si la agregación estuviera calculada sobre la página (bug que A4.1
    corrige) en vez del conjunto filtrado completo, páginas distintas darían
    promedios/distribuciones distintos. Deben ser idénticos."""
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        page1 = await list_feedback(
            page=1,
            page_size=5,
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )
        page2 = await list_feedback(
            page=2,
            page_size=5,
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    assert {item.id for item in page1.items} != {item.id for item in page2.items}
    assert page1.total == page2.total == 12
    assert page1.avg_ratings.model_dump() == page2.avg_ratings.model_dump()
    assert page1.distributions == page2.distributions


@pytest.mark.anyio
async def test_avg_and_distributions_reflect_the_rating_filter_not_the_unfiltered_table() -> None:
    """La agregación debe calcularse sobre el conjunto YA filtrado por
    rating, no sobre toda la tabla."""
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=4,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    filtered_ratings = [r for r in _FEEDBACK_RATINGS if r["overall"] >= 4]
    expected_avg, expected_dist = _reference_aggregation(
        filtered_ratings, ["tone", "length", "usability", "overall"]
    )
    assert response.total == len(filtered_ratings)
    assert response.avg_ratings.model_dump() == expected_avg
    assert response.distributions == expected_dist


# ---------------------------------------------------------------------------
# Paginación LIMIT/OFFSET en SQL — orden y no-superposición entre páginas.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pagination_pages_do_not_overlap_and_cover_the_full_set() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    seen_ids: list[str] = []
    async with session_factory() as session:
        for page in (1, 2, 3):
            response = await list_feedback(
                page=page,
                page_size=5,
                min_overall=None,
                max_overall=None,
                start_date=None,
                end_date=None,
                _admin=_ADMIN,
                session=session,
            )
            seen_ids.extend(item.id for item in response.items)

    assert len(seen_ids) == len(set(seen_ids)) == 12  # sin duplicados, cubre todo
    assert {f"fb-{i}" for i in range(12)} == set(seen_ids)


@pytest.mark.anyio
async def test_pagination_preserves_descending_date_order_across_pages() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback(session_factory)

    async with session_factory() as session:
        page1 = await list_feedback(
            page=1,
            page_size=5,
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )
        page2 = await list_feedback(
            page=2,
            page_size=5,
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    # Sembrado con created_at creciente (fb-0 el más antiguo, fb-11 el más
    # nuevo); el orden es descendente, así que la página 1 debe traer los
    # más recientes (fb-11..fb-7) y la página 2 los siguientes (fb-6..fb-2).
    assert [item.id for item in page1.items] == [f"fb-{i}" for i in range(11, 6, -1)]
    assert [item.id for item in page2.items] == [f"fb-{i}" for i in range(6, 1, -1)]


# ---------------------------------------------------------------------------
# Mismo tratamiento para message-feedback (pertinence/accuracy).
# ---------------------------------------------------------------------------

_MSG_RATINGS = [
    {"pertinence": 5, "accuracy": 5},
    {"pertinence": 1, "accuracy": 2},
    {"pertinence": 3, "accuracy": 3},
    {"pertinence": 4, "accuracy": 4},
    {"pertinence": 2, "accuracy": 1},
    {"pertinence": 5, "accuracy": 1},
    {"pertinence": 2, "accuracy": 4},
    {"pertinence": 3, "accuracy": 5},
]


async def _seed_message_feedback(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        session.add(User(id="u1", email="u1@example.com", password_hash="x", role="user"))
        await session.commit()
    async with session_factory() as session:
        session.add_all(
            [
                MessageFeedback(
                    id=f"mf-{i}",
                    user_id="u1",
                    conversation_id=f"conv-{i}",
                    message_id=f"msg-{i}",
                    ratings=ratings,
                    created_at=_BASE + timedelta(hours=i),
                )
                for i, ratings in enumerate(_MSG_RATINGS)
            ]
        )
        await session.commit()


@pytest.mark.anyio
async def test_message_feedback_pertinence_and_accuracy_filters_combine_as_and() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_message_feedback(session_factory)

    async with session_factory() as session:
        response = await list_message_feedback(
            page=1,
            page_size=20,
            min_pertinence=3,
            max_pertinence=None,
            min_accuracy=None,
            max_accuracy=3,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    expected_ids = {
        f"mf-{i}" for i, r in enumerate(_MSG_RATINGS) if r["pertinence"] >= 3 and r["accuracy"] <= 3
    }
    assert {item.id for item in response.items} == expected_ids
    assert response.total == len(expected_ids)


@pytest.mark.anyio
async def test_message_feedback_total_and_avg_cover_full_filtered_set_not_the_page() -> None:
    session_factory = await _fresh_session_factory()
    await _seed_message_feedback(session_factory)

    async with session_factory() as session:
        response = await list_message_feedback(
            page=1,
            page_size=2,
            min_pertinence=None,
            max_pertinence=None,
            min_accuracy=None,
            max_accuracy=None,
            start_date=None,
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    assert len(response.items) == 2
    assert response.total == 8

    expected_avg, expected_dist = _reference_aggregation(_MSG_RATINGS, ["pertinence", "accuracy"])
    assert response.avg_ratings == expected_avg
    assert response.distributions == expected_dist


# ---------------------------------------------------------------------------
# C5 — desempate estable por `id` cuando varias filas comparten exactamente
# el mismo `created_at`. Sin un segundo criterio de orden, el orden relativo
# entre esas filas queda a discreción del motor — no garantizado estable
# entre solicitudes con el mismo LIMIT/OFFSET — lo que puede repetir o
# saltar registros al paginar. `.order_by(created_at.desc(), id.desc())`
# lo hace determinista.
# ---------------------------------------------------------------------------

# Deliberadamente TODAS con el mismo created_at (a diferencia de
# _FEEDBACK_RATINGS/_MSG_RATINGS de arriba, que usan timestamps distintos por
# fila): es precisamente el caso en el que un orden por fecha únicamente es
# ambiguo.
_SAME_TIMESTAMP_FEEDBACK_COUNT = 15


async def _seed_feedback_with_identical_created_at(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        session.add(
            User(id="u-same-ts", email="same-ts@example.com", password_hash="x", role="user")
        )
        await session.commit()
    async with session_factory() as session:
        session.add_all(
            [
                Feedback(
                    id=f"fb-same-ts-{i}",
                    user_id="u-same-ts",
                    ratings={"tone": 3, "length": 3, "usability": 3, "overall": 3},
                    created_at=_BASE,  # EXACTAMENTE el mismo instante para todas
                )
                for i in range(_SAME_TIMESTAMP_FEEDBACK_COUNT)
            ]
        )
        await session.commit()


@pytest.mark.anyio
async def test_feedback_pagination_is_stable_when_created_at_ties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = await _fresh_session_factory()
    await _seed_feedback_with_identical_created_at(session_factory)

    async def _all_pages() -> list[str]:
        seen: list[str] = []
        async with session_factory() as session:
            for page in (1, 2, 3, 4):
                response = await list_feedback(
                    page=page,
                    page_size=4,
                    min_overall=None,
                    max_overall=None,
                    start_date=None,
                    end_date=None,
                    _admin=_ADMIN,
                    session=session,
                )
                seen.extend(item.id for item in response.items)
        return seen

    first_pass = await _all_pages()
    second_pass = await _all_pages()

    expected_ids = {f"fb-same-ts-{i}" for i in range(_SAME_TIMESTAMP_FEEDBACK_COUNT)}
    assert len(first_pass) == len(set(first_pass)) == _SAME_TIMESTAMP_FEEDBACK_COUNT, (
        "no debía haber duplicados ni registros faltantes al paginar filas con el mismo created_at"
    )
    assert set(first_pass) == expected_ids
    # Estable: repetir la misma secuencia de páginas produce EXACTAMENTE el
    # mismo orden — sin el desempate por `id`, esto no está garantizado.
    assert first_pass == second_pass


@pytest.mark.anyio
async def test_message_feedback_pagination_is_stable_when_created_at_ties() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(
            User(
                id="u-msg-same-ts", email="msg-same-ts@example.com", password_hash="x", role="user"
            )
        )
        await session.commit()
    async with session_factory() as session:
        session.add_all(
            [
                MessageFeedback(
                    id=f"mf-same-ts-{i}",
                    user_id="u-msg-same-ts",
                    conversation_id=f"conv-same-ts-{i}",
                    message_id=f"msg-same-ts-{i}",
                    ratings={"pertinence": 3, "accuracy": 3},
                    created_at=_BASE,
                )
                for i in range(10)
            ]
        )
        await session.commit()

    async def _all_pages() -> list[str]:
        seen: list[str] = []
        async with session_factory() as session:
            for page in (1, 2, 3):
                response = await list_message_feedback(
                    page=page,
                    page_size=4,
                    min_pertinence=None,
                    max_pertinence=None,
                    min_accuracy=None,
                    max_accuracy=None,
                    start_date=None,
                    end_date=None,
                    _admin=_ADMIN,
                    session=session,
                )
                seen.extend(item.id for item in response.items)
        return seen

    first_pass = await _all_pages()
    second_pass = await _all_pages()

    expected_ids = {f"mf-same-ts-{i}" for i in range(10)}
    assert len(first_pass) == len(set(first_pass)) == 10
    assert set(first_pass) == expected_ids
    assert first_pass == second_pass
