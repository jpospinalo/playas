"""Endpoints del panel de administración.

Solo accesibles para usuarios con rol 'admin' o 'super-admin'.

  GET /api/admin/feedback  — lista paginada de feedback con filtros y estadísticas
  GET /api/admin/users     — lista de usuarios registrados con rol y fecha
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from rag.api.auth import require_admin
from rag.api.firebase_admin import get_db
from rag.api.schemas import (
    AdminFeedbackItem,
    AdminFeedbackResponse,
    AdminUserItem,
    AdminUsersResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ts_to_iso(ts) -> str:
    """Convierte un Firestore DatetimeWithNanoseconds a ISO 8601."""
    if ts is None:
        return ""
    try:
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return str(ts)
    except Exception:
        return ""


@router.get("/feedback", response_model=AdminFeedbackResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Ítems por página"),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    max_rating: int | None = Query(default=None, ge=1, le=5),
    start_date: str | None = Query(default=None, description="ISO 8601 — fecha mínima"),
    end_date: str | None = Query(default=None, description="ISO 8601 — fecha máxima"),
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminFeedbackResponse:
    """Lista el feedback ordenado por fecha descendente, con filtros opcionales.

    Retorna también el total, promedio de rating y distribución 1-5.
    """
    db = get_db()

    query = db.collection("feedback").order_by(
        "createdAt", direction="DESCENDING"
    )

    if min_rating is not None:
        query = query.where("rating", ">=", min_rating)
    if max_rating is not None:
        query = query.where("rating", "<=", max_rating)
    if start_date is not None:
        try:
            dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
            query = query.where("createdAt", ">=", dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"start_date inválido: {start_date!r}",
            ) from exc
    if end_date is not None:
        try:
            dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)
            query = query.where("createdAt", "<=", dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"end_date inválido: {end_date!r}",
            ) from exc

    try:
        docs = [doc async for doc in query.stream()]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error leyendo feedback de Firestore: {exc}",
        ) from exc

    total = len(docs)
    distribution: dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    rating_sum = 0

    for doc in docs:
        data = doc.to_dict() or {}
        r = data.get("rating", 0)
        if 1 <= r <= 5:
            distribution[str(r)] += 1
            rating_sum += r

    avg_rating = round(rating_sum / total, 2) if total > 0 else 0.0

    # Paginación en memoria (Firestore no tiene offset nativo simple sin cursor)
    start = (page - 1) * page_size
    page_docs = docs[start : start + page_size]

    items: list[AdminFeedbackItem] = []
    for doc in page_docs:
        data = doc.to_dict() or {}
        items.append(
            AdminFeedbackItem(
                id=doc.id,
                userId=data.get("userId", ""),
                userEmail=data.get("userEmail", ""),
                rating=data.get("rating", 0),
                comment=data.get("comment"),
                conversationId=data.get("conversationId"),
                conversationTitle=data.get("conversationTitle"),
                createdAt=_ts_to_iso(data.get("createdAt")),
            )
        )

    return AdminFeedbackResponse(
        items=items,
        total=total,
        avg_rating=avg_rating,
        distribution=distribution,
    )


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminUsersResponse:
    """Lista todos los usuarios registrados con su rol y fecha de registro."""
    db = get_db()

    try:
        docs = [doc async for doc in db.collection("users").order_by("createdAt", direction="DESCENDING").stream()]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error leyendo usuarios de Firestore: {exc}",
        ) from exc

    items: list[AdminUserItem] = []
    for doc in docs:
        data = doc.to_dict() or {}
        items.append(
            AdminUserItem(
                uid=doc.id,
                email=data.get("email", ""),
                displayName=data.get("displayName"),
                role=data.get("role", "user"),
                createdAt=_ts_to_iso(data.get("createdAt")),
            )
        )

    return AdminUsersResponse(items=items, total=len(items))
