"""Endpoints del panel de administración.

Solo accesibles para usuarios con rol 'admin' o 'super-admin'.

  GET  /api/admin/feedback          — lista paginada de feedback
  GET  /api/admin/message-feedback  — lista paginada de feedback de mensajes
  GET  /api/admin/users             — lista de usuarios
  POST /api/admin/users             — crea usuario
  PATCH /api/admin/users/{uid}/password — cambia contraseña
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from rag.api.auth import require_admin
from rag.api.database import get_session
from rag.api.models import Feedback, MessageFeedback, User
from rag.api.passwords import hash_password_async
from rag.api.schemas import (
    AdminFeedbackItem,
    AdminFeedbackResponse,
    AdminMessageFeedbackItem,
    AdminMessageFeedbackResponse,
    AdminUserItem,
    AdminUsersResponse,
    CreateUserRequest,
    MessageFeedbackRatings,
    RatingDimensions,
    RatingDimensionsFloat,
    UpdatePasswordRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _parse_date_filter_utc(value: str, field_name: str) -> datetime:
    """Convierte un filtro de fecha ISO 8601 a un ``datetime`` consciente de UTC.

    Si ``value`` incluye información de huso horario, se convierte el
    instante a UTC preservando su valor real (equivalente a
    ``astimezone(UTC)``) en lugar de sobrescribir el offset original. Si
    ``value`` no incluye huso horario, se asume UTC — comportamiento
    documentado para valores ambiguos, no una conversión real.
    """
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, f"{field_name} inválido: {value!r}") from exc
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _rating_dim(ratings_column: InstrumentedAttribute, key: str) -> ColumnElement[int]:
    """A4.1 — extrae una dimensión de una columna JSON `ratings` de forma
    portable entre SQLite y PostgreSQL, con el mismo default que usaba el
    filtrado en Python (``(doc.ratings or {}).get(key, 0)``).

    ``Column[key]`` es la indexación JSON genérica de SQLAlchemy — en
    SQLite compila a ``JSON_EXTRACT(...)``, en PostgreSQL a ``ratings ->>
    'key'`` seguido del cast que pide ``.as_integer()`` — ambas rutas están
    documentadas como parte del tipo `JSON` genérico, precisamente para no
    tener que escribir SQL específico por dialecto aquí. ``coalesce(..., 0)``
    reproduce el ``.get(key, 0)`` de antes: una fila cuyo `ratings` no tiene
    esa clave cuenta como 0, igual que antes — sin este coalesce, extraer
    una clave ausente da NULL y una comparación contra NULL se evalúa como
    "no cumple" en SQL, lo que habría excluido de max_overall/max_* filas
    que antes sí calificaban.

    Asume que todo valor presente ya es un entero pequeño (1-5): el único
    productor de `ratings` (`routes/feedback.py`) siempre lo construye desde
    `RatingDimensions`/`MessageFeedbackRatings`, ambos `int` validados
    `ge=1, le=5` — no hay una ruta de escritura que persista un valor no
    numérico, así que no hace falta manejar ese caso aquí.
    """
    return func.coalesce(ratings_column[key].as_integer(), 0)


@router.get("/feedback", response_model=AdminFeedbackResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Ítems por página"),
    min_overall: int | None = Query(default=None, ge=1, le=5),
    max_overall: int | None = Query(default=None, ge=1, le=5),
    start_date: str | None = Query(default=None, description="ISO 8601 — fecha mínima"),
    end_date: str | None = Query(default=None, description="ISO 8601 — fecha máxima"),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminFeedbackResponse:
    """Lista el feedback de conversación ordenado por fecha descendente."""
    # A4.1 — filtros, conteo, orden, LIMIT/OFFSET y la agregación
    # (promedio/distribución) se ejecutan en SQL sobre el conjunto filtrado
    # COMPLETO, no solo sobre la página: antes se cargaba toda la tabla
    # filtrada por fecha a Python y se hacía ahí el resto (filtro de rating,
    # conteo, promedio, distribución, paginado) — con miles de filas eso
    # recorre toda la tabla en cada solicitud independientemente de
    # `page_size`. Las tres consultas de abajo comparten exactamente las
    # mismas condiciones `where` (`overall_expr = _rating_dim(...)` incluida)
    # para que conteo/agregación y la página paginada describan el mismo
    # conjunto filtrado. Comentario fuera del docstring a propósito: FastAPI
    # usa el docstring como `description` en OpenAPI, y este punto no debe
    # alterar el schema publicado (ver el checkpoint de A3: los únicos
    # cambios de OpenAPI autorizados hasta ahora fueron el tipado de
    # `sources` y los `min_length` de A3.5).
    overall_expr = _rating_dim(Feedback.ratings, "overall")
    conditions: list[ColumnElement[bool]] = []
    if start_date:
        dt = _parse_date_filter_utc(start_date, "start_date")
        conditions.append(Feedback.created_at >= dt)
    if end_date:
        dt = _parse_date_filter_utc(end_date, "end_date")
        conditions.append(Feedback.created_at <= dt)
    if min_overall is not None:
        conditions.append(overall_expr >= min_overall)
    if max_overall is not None:
        conditions.append(overall_expr <= max_overall)

    total = (
        await session.execute(select(func.count()).select_from(Feedback).where(*conditions))
    ).scalar_one()

    dims = ["tone", "length", "usability", "overall"]
    agg_columns = []
    for d in dims:
        dim_expr = _rating_dim(Feedback.ratings, d)
        valid_expr = case((dim_expr.between(1, 5), dim_expr), else_=0)
        agg_columns.append(func.sum(valid_expr).label(f"sum_{d}"))
        for v in range(1, 6):
            agg_columns.append(func.count().filter(dim_expr == v).label(f"{d}_{v}"))
    agg_row = (
        await session.execute(select(*agg_columns).select_from(Feedback).where(*conditions))
    ).one()

    sums = {d: (getattr(agg_row, f"sum_{d}") or 0) for d in dims}
    distributions: dict[str, dict[str, int]] = {
        d: {str(v): (getattr(agg_row, f"{d}_{v}") or 0) for v in range(1, 6)} for d in dims
    }
    avg_ratings = RatingDimensionsFloat(
        **{d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in dims}
    )

    # C5 — desempate estable por `id` cuando varias filas comparten el mismo
    # `created_at`: sin él, el orden entre esas filas queda a discreción del
    # motor (no garantizado estable entre solicitudes con el mismo LIMIT/
    # OFFSET), lo que puede repetir o saltar registros entre páginas
    # consecutivas. `id` es la clave primaria (string UUID) — desempate
    # arbitrario pero determinista, no un criterio de negocio.
    page_stmt = (
        select(Feedback)
        .where(*conditions)
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    docs = (await session.execute(page_stmt)).scalars().all()
    items = [
        AdminFeedbackItem(
            id=doc.id,
            userId=doc.user_id,
            userEmail=doc.user_email,
            ratings=RatingDimensions(
                tone=(doc.ratings or {}).get("tone", 0),
                length=(doc.ratings or {}).get("length", 0),
                usability=(doc.ratings or {}).get("usability", 0),
                overall=(doc.ratings or {}).get("overall", 0),
            ),
            comment=doc.comment,
            conversationId=doc.conversation_id,
            conversationTitle=doc.conversation_title,
            createdAt=doc.created_at.isoformat() if doc.created_at else "",
        )
        for doc in docs
    ]

    return AdminFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/message-feedback", response_model=AdminMessageFeedbackResponse)
async def list_message_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    min_pertinence: int | None = Query(default=None, ge=1, le=5),
    max_pertinence: int | None = Query(default=None, ge=1, le=5),
    min_accuracy: int | None = Query(default=None, ge=1, le=5),
    max_accuracy: int | None = Query(default=None, ge=1, le=5),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminMessageFeedbackResponse:
    """Lista el feedback de mensajes ordenado por fecha descendente."""
    # A4.1 — mismo tratamiento que `list_feedback`: filtros, conteo, orden,
    # LIMIT/OFFSET y agregación en SQL sobre el conjunto filtrado completo,
    # con las mismas condiciones `where` reutilizadas en las tres consultas.
    # Fuera del docstring por la misma razón que en `list_feedback`.
    pertinence_expr = _rating_dim(MessageFeedback.ratings, "pertinence")
    accuracy_expr = _rating_dim(MessageFeedback.ratings, "accuracy")
    conditions: list[ColumnElement[bool]] = []
    if start_date:
        dt = _parse_date_filter_utc(start_date, "start_date")
        conditions.append(MessageFeedback.created_at >= dt)
    if end_date:
        dt = _parse_date_filter_utc(end_date, "end_date")
        conditions.append(MessageFeedback.created_at <= dt)
    if min_pertinence is not None:
        conditions.append(pertinence_expr >= min_pertinence)
    if max_pertinence is not None:
        conditions.append(pertinence_expr <= max_pertinence)
    if min_accuracy is not None:
        conditions.append(accuracy_expr >= min_accuracy)
    if max_accuracy is not None:
        conditions.append(accuracy_expr <= max_accuracy)

    total = (
        await session.execute(select(func.count()).select_from(MessageFeedback).where(*conditions))
    ).scalar_one()

    msg_dims = ["pertinence", "accuracy"]
    agg_columns = []
    for d in msg_dims:
        dim_expr = _rating_dim(MessageFeedback.ratings, d)
        valid_expr = case((dim_expr.between(1, 5), dim_expr), else_=0)
        agg_columns.append(func.sum(valid_expr).label(f"sum_{d}"))
        for v in range(1, 6):
            agg_columns.append(func.count().filter(dim_expr == v).label(f"{d}_{v}"))
    agg_row = (
        await session.execute(select(*agg_columns).select_from(MessageFeedback).where(*conditions))
    ).one()

    sums = {d: (getattr(agg_row, f"sum_{d}") or 0) for d in msg_dims}
    distributions: dict[str, dict[str, int]] = {
        d: {str(v): (getattr(agg_row, f"{d}_{v}") or 0) for v in range(1, 6)} for d in msg_dims
    }
    avg_ratings = {d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in msg_dims}

    # C5 — mismo desempate estable que en list_feedback (ver comentario ahí).
    page_stmt = (
        select(MessageFeedback)
        .where(*conditions)
        .order_by(MessageFeedback.created_at.desc(), MessageFeedback.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    docs = (await session.execute(page_stmt)).scalars().all()
    items = [
        AdminMessageFeedbackItem(
            id=doc.id,
            userId=doc.user_id,
            userEmail=doc.user_email,
            conversationId=doc.conversation_id,
            messageId=doc.message_id,
            ratings=MessageFeedbackRatings(
                pertinence=(doc.ratings or {}).get("pertinence", 0),
                accuracy=(doc.ratings or {}).get("accuracy", 0),
            ),
            expectedAnswer=doc.expected_answer,
            createdAt=doc.created_at.isoformat() if doc.created_at else "",
        )
        for doc in docs
    ]

    return AdminMessageFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUsersResponse:
    """Lista todos los usuarios registrados con su rol y fecha de registro."""
    users = list(
        (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    )
    items = [
        AdminUserItem(
            uid=u.id,
            email=u.email,
            displayName=u.display_name,
            role=u.role,
            createdAt=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]
    return AdminUsersResponse(items=items, total=len(items))


@router.post("/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserItem:
    """Crea una cuenta con rol 'user'. No envía email de verificación."""
    normalized_email = payload.email.strip().lower()
    existing = await session.execute(select(User).where(func.lower(User.email) == normalized_email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese email ya está registrado.",
        )
    password_hash = await hash_password_async(payload.password)
    user = User(
        id=str(uuid.uuid4()),
        email=normalized_email,
        password_hash=password_hash,
        display_name=payload.displayName,
        role="user",
        created_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Misma condición de carrera que en el registro público (ver
        # routes/auth.py:register): la comprobación de existencia de arriba no
        # es atómica con este commit. Se revierte y se confirma si el email ya
        # existe antes de relanzar cualquier otro error de integridad.
        await session.rollback()
        existing_after_race = await session.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        )
        if existing_after_race.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ese email ya está registrado.",
            ) from None
        raise
    return AdminUserItem(
        uid=user.id,
        email=user.email,
        displayName=user.display_name,
        role=user.role,
        createdAt=user.created_at.isoformat(),
    )


@router.patch("/users/{uid}/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_user_password(
    uid: str,
    payload: UpdatePasswordRequest,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Cambia la contraseña de un usuario existente."""
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    user.password_hash = await hash_password_async(payload.password)
    await session.commit()
