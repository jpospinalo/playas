"""Cuentas del ejercicio de validación (``routes/participantes.py``) y los
filtros por participante y tipo de usuario de playa del panel.

Se prueba que solo un admin entra, que la creación por lote asigna números
P001… y devuelve claves que sí sirven para entrar, que valida tipo/sede y
duplicados, y que el registro público (cuando se activa) guarda el tipo.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from rag.api.auth import create_access_token
from rag.api.database import get_session
from rag.api.models import Base, Conversation, ExerciseProfile, Message, User
from rag.api.routes.auth import router as auth_router
from rag.api.routes.panel import router as panel_router
from rag.api.routes.participantes import clave_nueva
from rag.api.routes.participantes import router as participantes_router

_AHORA = datetime.now(UTC)


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, async_sessionmaker]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "prueba-participantes-secreto-largo-123456")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(User(id="adm", email="admin@atlas.co", password_hash="x", role="admin"))
            s.add(
                User(id="u1", email="u1@x.co", password_hash="x", display_name="Ana", role="user")
            )
            s.add(
                User(id="u2", email="u2@x.co", password_hash="x", display_name="Beto", role="user")
            )
            s.add(ExerciseProfile(user_id="u1", codigo="P007", tipo_playa=2))
            s.add(ExerciseProfile(user_id="u2", codigo="P008", tipo_playa=5))
            for i, uid in enumerate(["u1", "u1", "u2"]):
                cid = f"c{i}"
                s.add(Conversation(id=cid, user_id=uid, thread_id=cid, created_at=_AHORA))
                s.add(
                    Message(
                        id=f"q{i}",
                        conversation_id=cid,
                        role="user",
                        text=f"¿Pregunta {i} sobre pesca?",
                        created_at=_AHORA - timedelta(hours=i + 1),
                    )
                )
            await s.commit()

    asyncio.run(_preparar())

    async def _sesion() -> AsyncGenerator:
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(participantes_router)
    app.include_router(panel_router)
    app.include_router(auth_router)
    app.dependency_overrides[get_session] = _sesion
    with TestClient(app) as c:
        yield c, factory
    asyncio.run(engine.dispose())


def _h(uid: str = "adm", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uid, f'{uid}@x.co', role)}"}


def test_clave_nueva_legible() -> None:
    c = clave_nueva()
    assert len(c) >= 8 and c.count("-") == 2


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/api/admin/participantes"),
        ("get", "/api/admin/participantes/catalogo"),
        ("post", "/api/admin/participantes/lote"),
        ("patch", "/api/admin/participantes/u1"),
        ("post", "/api/admin/participantes/u1/clave"),
    ],
)
def test_solo_admin(cliente, metodo: str, ruta: str) -> None:
    c, _ = cliente
    assert getattr(c, metodo)(ruta).status_code == 401
    assert getattr(c, metodo)(ruta, headers=_h("u1", "user")).status_code == 403


def test_listar_y_catalogo(cliente) -> None:
    c, _ = cliente
    r = c.get("/api/admin/participantes", headers=_h()).json()
    primeros = [(i["codigo"], i["tipo_playa_nombre"], i["preguntas"]) for i in r["items"][:2]]
    assert primeros == [("P007", "Pescadores", 2), ("P008", "Turistas", 1)]
    assert c.get("/api/admin/participantes?tipo_playa=5", headers=_h()).json()["total"] == 1
    cat = c.get("/api/admin/participantes/catalogo", headers=_h()).json()
    assert [t["id"] for t in cat["tipos_playa"]] == [1, 2, 3, 4, 5]
    assert cat["roles"] == ["user", "evaluador", "comite", "admin"]


def test_lote_crea_cuentas_con_clave_que_sirve(cliente) -> None:
    c, factory = cliente
    r = c.post(
        "/api/admin/participantes/lote",
        headers=_h(),
        json={
            "personas": [
                {"nombre": "Carla Ruiz", "tipo_playa": 3},
                {"nombre": "Dario Paz", "tipo_playa": 1},
                {"nombre": "Eva Semillero", "rol": "evaluador", "sede": "Barranquilla"},
            ]
        },
    )
    assert r.status_code == 201
    creadas = r.json()["creadas"]
    assert [x["codigo"] for x in creadas] == ["P009", "P010", None]
    assert creadas[0]["correo"] == "p009@ejercicio.atlas"
    login = c.post(
        "/api/auth/login", json={"email": creadas[0]["correo"], "password": creadas[0]["clave"]}
    )
    assert login.status_code == 200

    async def _rol() -> str:
        async with factory() as s:
            u = (
                await s.execute(select(User).where(User.email == creadas[2]["correo"]))
            ).scalar_one()
            return u.role

    assert asyncio.run(_rol()) == "evaluador"


@pytest.mark.parametrize(
    ("personas", "codigo"),
    [
        ([{"nombre": "Sin tipo"}], 422),
        ([{"nombre": "Eval", "rol": "evaluador"}], 422),
        ([{"nombre": "A", "tipo_playa": 1, "codigo": "P007"}], 409),
        (
            [
                {"nombre": "A", "tipo_playa": 1, "codigo": "X1"},
                {"nombre": "B", "tipo_playa": 1, "codigo": "X1"},
            ],
            422,
        ),
        ([{"nombre": "A", "tipo_playa": 9}], 422),
    ],
)
def test_lote_valida(cliente, personas: list, codigo: int) -> None:
    c, _ = cliente
    r = c.post("/api/admin/participantes/lote", headers=_h(), json={"personas": personas})
    assert r.status_code == codigo


def test_cambiar_y_restablecer_clave(cliente) -> None:
    c, _ = cliente
    r = c.patch(
        "/api/admin/participantes/u1", headers=_h(), json={"tipo_playa": 4, "rol": "comite"}
    )
    assert r.status_code == 200 and r.json()["tipo_playa"] == 4 and r.json()["rol"] == "comite"
    nueva = c.post("/api/admin/participantes/u1/clave", headers=_h()).json()
    assert (
        c.post("/api/auth/login", json={"email": "u1@x.co", "password": nueva["clave"]}).status_code
        == 200
    )
    assert c.patch("/api/admin/participantes/nadie", headers=_h(), json={}).status_code == 404


def test_filtros_del_panel_por_participante_y_tipo(cliente) -> None:
    c, _ = cliente
    h = _h()
    assert (
        c.get("/api/admin/panel/preguntas?dias=7&participante=p007", headers=h).json()["total"] == 2
    )
    item = c.get("/api/admin/panel/preguntas?dias=7&tipo_playa=5", headers=h).json()["items"][0]
    assert item["participante"] == "P008" and item["tipo_playa"] == 5
    r = c.get("/api/admin/panel/resumen?dias=7&tipo_playa=2", headers=h).json()
    assert r["cifras"]["preguntas"] == 2
    assert c.get("/api/admin/panel/resumen?tipo_playa=7", headers=h).status_code == 422


def test_registro_publico_guarda_el_tipo(cliente, monkeypatch: pytest.MonkeyPatch) -> None:
    c, factory = cliente
    assert (
        c.post(
            "/api/auth/register",
            json={"email": "z@x.co", "password": "una-clave-larga", "tipo_playa": 2},
        ).status_code
        == 403
    )  # desactivado por defecto
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)
    r = c.post(
        "/api/auth/register",
        json={"email": "z@x.co", "password": "una-clave-larga", "tipo_playa": 2},
    )
    assert r.status_code == 201

    async def _perfil() -> tuple:
        async with factory() as s:
            p = await s.get(ExerciseProfile, r.json()["user_id"])
            return p.codigo, p.tipo_playa

    assert asyncio.run(_perfil()) == ("P009", 2)
