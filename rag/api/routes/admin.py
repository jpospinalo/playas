"""Endpoints del panel de administración.

Solo accesibles para usuarios con rol 'admin' o 'super-admin'.

  GET /api/admin/feedback  — lista paginada de feedback con filtros y estadísticas
  GET /api/admin/users     — lista de usuarios registrados con rol y fecha
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from firebase_admin import auth as firebase_auth
from google.cloud.firestore import SERVER_TIMESTAMP

from rag.api.auth import require_admin
from rag.api.firebase_admin import (
    create_user_async,
    get_db,
    update_user_password_async,
)
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
    min_overall: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por calificación general mínima"
    ),
    max_overall: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por calificación general máxima"
    ),
    start_date: str | None = Query(default=None, description="ISO 8601 — fecha mínima"),
    end_date: str | None = Query(default=None, description="ISO 8601 — fecha máxima"),
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminFeedbackResponse:
    """Lista el feedback de conversación ordenado por fecha descendente.

    Retorna también el total, promedios por dimensión y distribuciones por dimensión.
    """
    db = get_db()

    query = db.collection("feedback").order_by("createdAt", direction="DESCENDING")

    if min_overall is not None:
        query = query.where("ratings.overall", ">=", min_overall)
    if max_overall is not None:
        query = query.where("ratings.overall", "<=", max_overall)
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

    # Aggregate per-dimension averages and distributions
    dims = ["tone", "length", "usability", "overall"]
    distributions: dict[str, dict[str, int]] = {
        d: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0} for d in dims
    }
    sums: dict[str, float] = {d: 0.0 for d in dims}

    for doc in docs:
        data = doc.to_dict() or {}
        ratings_data = data.get("ratings", {})
        # Fallback para documentos legacy que aún tienen "rating" en vez de "ratings"
        if not ratings_data and "rating" in data:
            legacy_r = data["rating"]
            ratings_data = {
                "tone": legacy_r,
                "length": legacy_r,
                "usability": legacy_r,
                "overall": legacy_r,
            }
        for d in dims:
            val = ratings_data.get(d, 0)
            if 1 <= val <= 5:
                distributions[d][str(val)] += 1
                sums[d] += val

    avg_ratings = RatingDimensionsFloat(
        **{d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in dims}
    )

    # Paginación en memoria
    start = (page - 1) * page_size
    page_docs = docs[start : start + page_size]

    items: list[AdminFeedbackItem] = []
    for doc in page_docs:
        data = doc.to_dict() or {}
        ratings_data = data.get("ratings", {})
        if not ratings_data and "rating" in data:
            legacy_r = data["rating"]
            ratings_data = {
                "tone": legacy_r,
                "length": legacy_r,
                "usability": legacy_r,
                "overall": legacy_r,
            }
        items.append(
            AdminFeedbackItem(
                id=doc.id,
                userId=data.get("userId", ""),
                userEmail=data.get("userEmail", ""),
                ratings=RatingDimensions(
                    tone=ratings_data.get("tone", 0),
                    length=ratings_data.get("length", 0),
                    usability=ratings_data.get("usability", 0),
                    overall=ratings_data.get("overall", 0),
                ),
                comment=data.get("comment"),
                conversationId=data.get("conversationId"),
                conversationTitle=data.get("conversationTitle"),
                createdAt=_ts_to_iso(data.get("createdAt")),
            )
        )

    return AdminFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/message-feedback", response_model=AdminMessageFeedbackResponse)
async def list_message_feedback(
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Ítems por página"),
    min_pertinence: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por pertinencia mínima"
    ),
    max_pertinence: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por pertinencia máxima"
    ),
    min_accuracy: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por precisión mínima"
    ),
    max_accuracy: int | None = Query(
        default=None, ge=1, le=5, description="Filtrar por precisión máxima"
    ),
    start_date: str | None = Query(default=None, description="ISO 8601 — fecha mínima"),
    end_date: str | None = Query(default=None, description="ISO 8601 — fecha máxima"),
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminMessageFeedbackResponse:
    """Lista el feedback de mensajes ordenado por fecha descendente.

    Retorna también el total, promedios por dimensión y distribuciones.
    """
    db = get_db()

    query = db.collection("message_feedback").order_by("createdAt", direction="DESCENDING")

    if min_pertinence is not None:
        query = query.where("ratings.pertinence", ">=", min_pertinence)
    if max_pertinence is not None:
        query = query.where("ratings.pertinence", "<=", max_pertinence)
    if min_accuracy is not None:
        query = query.where("ratings.accuracy", ">=", min_accuracy)
    if max_accuracy is not None:
        query = query.where("ratings.accuracy", "<=", max_accuracy)
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
            detail=f"Error leyendo feedback de mensajes de Firestore: {exc}",
        ) from exc

    total = len(docs)

    # Aggregate per-dimension averages and distributions
    msg_dims = ["pertinence", "accuracy"]
    distributions: dict[str, dict[str, int]] = {
        d: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0} for d in msg_dims
    }
    sums: dict[str, float] = {d: 0.0 for d in msg_dims}

    for doc in docs:
        data = doc.to_dict() or {}
        ratings_data = data.get("ratings", {})
        for d in msg_dims:
            val = ratings_data.get(d, 0)
            if 1 <= val <= 5:
                distributions[d][str(val)] += 1
                sums[d] += val

    avg_ratings = {d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in msg_dims}

    # Paginación en memoria
    start = (page - 1) * page_size
    page_docs = docs[start : start + page_size]

    items: list[AdminMessageFeedbackItem] = []
    for doc in page_docs:
        data = doc.to_dict() or {}
        ratings_data = data.get("ratings", {})
        items.append(
            AdminMessageFeedbackItem(
                id=doc.id,
                userId=data.get("userId", ""),
                userEmail=data.get("userEmail", ""),
                conversationId=data.get("conversationId", ""),
                messageId=data.get("messageId", ""),
                ratings=MessageFeedbackRatings(
                    pertinence=ratings_data.get("pertinence", 0),
                    accuracy=ratings_data.get("accuracy", 0),
                ),
                expectedAnswer=data.get("expectedAnswer"),
                createdAt=_ts_to_iso(data.get("createdAt")),
            )
        )

    return AdminMessageFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminUsersResponse:
    """Lista todos los usuarios registrados con su rol y fecha de registro."""
    db = get_db()

    try:
        docs = [
            doc
            async for doc in db.collection("users")
            .order_by("createdAt", direction="DESCENDING")
            .stream()
        ]
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


@router.post(
    "/users",
    response_model=AdminUserItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: CreateUserRequest,
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> AdminUserItem:
    """Crea una cuenta de Firebase Auth y su documento en Firestore.

    El nuevo usuario nace con rol 'user'. No se envía email de verificación.
    """
    try:
        user_record = await create_user_async(
            email=payload.email,
            password=payload.password,
            display_name=payload.displayName,
        )
    except firebase_auth.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese email ya está registrado.",
        ) from exc
    except (
        ValueError,
        firebase_auth.InvalidIdTokenError,
    ) as exc:
        # firebase_auth lanza ValueError para email/password mal formados
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Datos inválidos: {exc}",
        ) from exc

    db = get_db()
    user_doc = {
        "email": payload.email,
        "displayName": payload.displayName,
        "role": "user",
        "createdAt": SERVER_TIMESTAMP,
    }
    await db.collection("users").document(user_record.uid).set(user_doc)

    # Releer para obtener el timestamp resuelto por el servidor
    snap = await db.collection("users").document(user_record.uid).get()
    data = snap.to_dict() or {}

    return AdminUserItem(
        uid=user_record.uid,
        email=data.get("email", payload.email),
        displayName=data.get("displayName"),
        role=data.get("role", "user"),
        createdAt=_ts_to_iso(data.get("createdAt")),
    )


@router.patch(
    "/users/{uid}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_user_password(
    uid: str,
    payload: UpdatePasswordRequest,
    _admin: dict = Depends(require_admin),  # noqa: B008
) -> None:
    """Cambia la contraseña de un usuario existente. Sin verificación."""
    try:
        await update_user_password_async(uid, payload.password)
    except firebase_auth.UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Contraseña inválida: {exc}",
        ) from exc
