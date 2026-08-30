"""Filtros de fecha `start_date`/`end_date` del panel de administración.

`_parse_date_filter_utc` (en `rag.api.routes.admin`) corrige un bug de
conversión de huso horario: el código anterior hacía
`datetime.fromisoformat(value).replace(tzinfo=UTC)`, que **sobrescribe**
`tzinfo` sin convertir el instante — un valor con offset explícito (p. ej.
`-05:00`) se trataba como si ya estuviera en UTC, desplazando el filtro
efectivo por la magnitud del offset. La versión corregida usa
`astimezone(UTC)` cuando el valor trae huso horario, y solo asume UTC
(documentado) cuando el valor es naive (sin huso horario).

Estas pruebas cubren la función auxiliar de forma aislada y, con una base de
datos SQLite real, los cuatro filtros de fecha que la usan (`start_date`/
`end_date` en `list_feedback` y en `list_message_feedback`), incluyendo la
inclusividad de los límites y el caso de valor inválido.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rag.api.models import Base, Feedback, MessageFeedback
from rag.api.routes.admin import _parse_date_filter_utc, list_feedback, list_message_feedback

_ADMIN = {"sub": "admin-1", "role": "admin"}
_RATINGS = {"tone": 5, "length": 5, "usability": 5, "overall": 5}
_MSG_RATINGS = {"pertinence": 5, "accuracy": 5}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _fresh_engine_and_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


# ── _parse_date_filter_utc(): unidad aislada ────────────────────────────────


def test_parse_date_filter_utc_converts_negative_offset_to_equivalent_instant() -> None:
    # 05:00 en -05:00 es el mismo instante que 10:00 UTC; el bug anterior lo
    # habría dejado en 05:00 UTC (5 horas de error).
    dt = _parse_date_filter_utc("2024-06-01T05:00:00-05:00", "start_date")
    assert dt == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_date_filter_utc_converts_positive_offset_to_equivalent_instant() -> None:
    dt = _parse_date_filter_utc("2024-06-01T12:00:00+02:00", "end_date")
    assert dt == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_date_filter_utc_accepts_z_suffix() -> None:
    dt = _parse_date_filter_utc("2024-06-01T10:00:00Z", "start_date")
    assert dt == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_date_filter_utc_accepts_explicit_utc_offset() -> None:
    dt = _parse_date_filter_utc("2024-06-01T10:00:00+00:00", "end_date")
    assert dt == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_date_filter_utc_assumes_utc_when_naive() -> None:
    dt = _parse_date_filter_utc("2024-06-01T10:00:00", "start_date")
    assert dt == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def test_parse_date_filter_utc_raises_422_on_invalid_value() -> None:
    with pytest.raises(HTTPException) as error:
        _parse_date_filter_utc("not-a-date", "start_date")
    assert error.value.status_code == 422
    assert error.value.detail == "start_date inválido: 'not-a-date'"


def test_parse_date_filter_utc_uses_field_name_in_error() -> None:
    with pytest.raises(HTTPException) as error:
        _parse_date_filter_utc("not-a-date", "end_date")
    assert error.value.detail == "end_date inválido: 'not-a-date'"


# ── list_feedback(): filtrado real por fecha, vía SQLite ────────────────────


@pytest.mark.anyio
async def test_list_feedback_start_date_offset_excludes_row_before_equivalent_instant() -> None:
    """Con el bug anterior, un `start_date` con offset `-05:00` se trataba
    como UTC directo y habría incluido erróneamente la fila anterior al
    instante real. Aquí debe excluirse."""
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add_all(
            [
                Feedback(
                    id="before",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 9, 59, 59, tzinfo=UTC),
                ),
                Feedback(
                    id="at-boundary",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
                ),
                Feedback(
                    id="after",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 15, 0, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=None,
            max_overall=None,
            start_date="2024-06-01T05:00:00-05:00",  # == 2024-06-01T10:00:00Z
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    ids = {item.id for item in response.items}
    assert ids == {"at-boundary", "after"}
    assert response.total == 2


@pytest.mark.anyio
async def test_list_feedback_start_date_is_inclusive() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add_all(
            [
                Feedback(
                    id="just-before",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 9, 59, 59, tzinfo=UTC),
                ),
                Feedback(
                    id="exact",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=None,
            max_overall=None,
            start_date="2024-06-01T10:00:00Z",
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    ids = {item.id for item in response.items}
    assert ids == {"exact"}


@pytest.mark.anyio
async def test_list_feedback_end_date_is_inclusive() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add_all(
            [
                Feedback(
                    id="exact",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
                ),
                Feedback(
                    id="just-after",
                    user_id="u1",
                    ratings=_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 1, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=None,
            max_overall=None,
            start_date=None,
            end_date="2024-06-01T10:00:00+00:00",
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    ids = {item.id for item in response.items}
    assert ids == {"exact"}


@pytest.mark.anyio
async def test_list_feedback_naive_start_date_assumed_utc() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add(
            Feedback(
                id="exact",
                user_id="u1",
                ratings=_RATINGS,
                created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
            )
        )
        await session.commit()

        response = await list_feedback(
            page=1,
            page_size=20,
            min_overall=None,
            max_overall=None,
            start_date="2024-06-01T10:00:00",
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    assert {item.id for item in response.items} == {"exact"}


@pytest.mark.anyio
async def test_list_feedback_invalid_start_date_raises_422() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            await list_feedback(
                page=1,
                page_size=20,
                min_overall=None,
                max_overall=None,
                start_date="not-a-date",
                end_date=None,
                _admin=_ADMIN,
                session=session,
            )
    await engine.dispose()

    assert error.value.status_code == 422
    assert error.value.detail == "start_date inválido: 'not-a-date'"


@pytest.mark.anyio
async def test_list_feedback_invalid_end_date_raises_422() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            await list_feedback(
                page=1,
                page_size=20,
                min_overall=None,
                max_overall=None,
                start_date=None,
                end_date="not-a-date",
                _admin=_ADMIN,
                session=session,
            )
    await engine.dispose()

    assert error.value.status_code == 422
    assert error.value.detail == "end_date inválido: 'not-a-date'"


# ── list_message_feedback(): mismo filtro, mismo modelo de auxiliar ─────────


@pytest.mark.anyio
async def test_list_message_feedback_start_date_offset_excludes_row_before_equivalent_instant() -> (
    None
):
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add_all(
            [
                MessageFeedback(
                    id="before",
                    user_id="u1",
                    conversation_id="c1",
                    message_id="m1",
                    ratings=_MSG_RATINGS,
                    created_at=datetime(2024, 6, 1, 9, 59, 59, tzinfo=UTC),
                ),
                MessageFeedback(
                    id="after",
                    user_id="u1",
                    conversation_id="c1",
                    message_id="m2",
                    ratings=_MSG_RATINGS,
                    created_at=datetime(2024, 6, 1, 15, 0, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

        response = await list_message_feedback(
            page=1,
            page_size=20,
            min_pertinence=None,
            max_pertinence=None,
            min_accuracy=None,
            max_accuracy=None,
            start_date="2024-06-01T05:00:00-05:00",  # == 2024-06-01T10:00:00Z
            end_date=None,
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    ids = {item.id for item in response.items}
    assert ids == {"after"}
    assert response.total == 1


@pytest.mark.anyio
async def test_list_message_feedback_end_date_is_inclusive() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        session.add_all(
            [
                MessageFeedback(
                    id="exact",
                    user_id="u1",
                    conversation_id="c1",
                    message_id="m1",
                    ratings=_MSG_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
                ),
                MessageFeedback(
                    id="just-after",
                    user_id="u1",
                    conversation_id="c1",
                    message_id="m2",
                    ratings=_MSG_RATINGS,
                    created_at=datetime(2024, 6, 1, 10, 0, 1, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

        response = await list_message_feedback(
            page=1,
            page_size=20,
            min_pertinence=None,
            max_pertinence=None,
            min_accuracy=None,
            max_accuracy=None,
            start_date=None,
            end_date="2024-06-01T10:00:00+00:00",
            _admin=_ADMIN,
            session=session,
        )

    await engine.dispose()

    assert {item.id for item in response.items} == {"exact"}


@pytest.mark.anyio
async def test_list_message_feedback_invalid_date_raises_422() -> None:
    engine, session_factory = await _fresh_engine_and_factory()
    async with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            await list_message_feedback(
                page=1,
                page_size=20,
                min_pertinence=None,
                max_pertinence=None,
                min_accuracy=None,
                max_accuracy=None,
                start_date="not-a-date",
                end_date=None,
                _admin=_ADMIN,
                session=session,
            )
    await engine.dispose()

    assert error.value.status_code == 422
    assert error.value.detail == "start_date inválido: 'not-a-date'"
