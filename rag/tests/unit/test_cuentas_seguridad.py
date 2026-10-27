"""CHECKLIST-FINAL del revisor: desactivar cuentas (c2), sesión más corta
para el personal (c5), auditoría de acciones de administración (c7) y aviso
de privacidad con autorización guardada (c8, Ley 1581 / Decreto 1377)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from rag.api.auditoria import router as auditoria_router
from rag.api.auth import create_access_token
from rag.api.database import get_session
from rag.api.models import Base, ExerciseProfile, User
from rag.api.passwords import hash_password
from rag.api.routes.auth import router as auth_router
from rag.api.routes.participantes import router as participantes_router
from rag.api.routes.privacidad import router as privacidad_router

_SECRETO = "prueba-seguridad-cuentas-secreto-largo-1234"


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", _SECRETO)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    clave = hash_password("clave-de-prueba-1")

    async def _preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(User(id="adm", email="admin@x.co", password_hash=clave, role="admin"))
            s.add(
                User(id="u1", email="u1@x.co", password_hash=clave, display_name="Ana", role="user")
            )
            await s.flush()
            s.add(ExerciseProfile(user_id="u1", codigo="P001", tipo_playa=2))
            await s.commit()

    asyncio.run(_preparar())

    async def _sesion() -> AsyncGenerator:
        async with factory() as s:
            yield s

    app = FastAPI()
    for r in (participantes_router, auth_router, auditoria_router, privacidad_router):
        app.include_router(r)
    app.dependency_overrides[get_session] = _sesion
    with TestClient(app) as c:
        yield c
    asyncio.run(engine.dispose())


def _h(uid: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uid, f'{uid}@x.co', role)}"}


def _entrar(c: TestClient, correo: str):
    return c.post("/api/auth/login", json={"email": correo, "password": "clave-de-prueba-1"})


def test_desactivar_conserva_historial_y_bloquea_el_ingreso(cliente) -> None:
    c = cliente
    adm, ana = _h("adm", "admin"), _h("u1", "user")
    assert _entrar(c, "u1@x.co").status_code == 200
    r = c.patch("/api/admin/participantes/u1", headers=adm, json={"activa": False})
    assert r.status_code == 200 and r.json()["activa"] is False
    assert _entrar(c, "u1@x.co").status_code == 403
    # Un token que ya tenía deja de servir.
    assert c.get("/api/privacidad", headers=ana).status_code == 403
    lista = c.get("/api/admin/participantes", headers=adm).json()["items"]
    assert {x["uid"]: x["activa"] for x in lista}["u1"] is False
    # Reactivar.
    assert c.patch("/api/admin/participantes/u1", headers=adm, json={"activa": True}).json()[
        "activa"
    ]
    assert _entrar(c, "u1@x.co").status_code == 200
    # Nadie se desactiva a sí mismo.
    assert (
        c.patch("/api/admin/participantes/adm", headers=adm, json={"activa": False}).status_code
        == 422
    )


def test_sesion_mas_corta_para_el_personal(cliente) -> None:
    def horas(role: str) -> float:
        t = jwt.decode(create_access_token("x", "x@x.co", role), _SECRETO, algorithms=["HS256"])
        return (t["exp"] - t["iat"]) / 3600

    assert horas("admin") == horas("comite") == horas("evaluador") == 8
    assert horas("user") == 7 * 24


def test_auditoria_de_acciones_de_admin(cliente) -> None:
    c = cliente
    adm = _h("adm", "admin")
    c.post(
        "/api/admin/participantes/lote",
        headers=adm,
        json={"personas": [{"nombre": "Luis", "rol": "user", "tipo_playa": 3}]},
    )
    c.patch("/api/admin/participantes/u1", headers=adm, json={"tipo_playa": 5})
    clave = c.post("/api/admin/participantes/u1/clave", headers=adm).json()["clave"]
    c.patch("/api/admin/participantes/u1", headers=adm, json={"activa": False})
    assert c.get("/api/admin/auditoria", headers=_h("u1", "user")).status_code == 403
    r = c.get("/api/admin/auditoria", headers=adm).json()
    acciones = [x["accion"] for x in r["items"]]
    assert acciones == ["desactivar_cuenta", "nueva_clave", "cambiar_cuenta", "crear_cuentas"]
    cambio = r["items"][2]
    assert cambio["objetivo"] == "P001 · Ana" and cambio["detalle"]["cambios"]["tipo_playa"] == [
        2,
        5,
    ]
    assert r["items"][3]["detalle"]["cantidad"] == 1
    assert clave not in str(r)  # la clave nunca queda en la auditoría


def test_aviso_de_privacidad_y_autorizacion_guardada(cliente) -> None:
    c = cliente
    ana = _h("u1", "user")
    assert c.get("/api/privacidad").status_code == 401
    r = c.get("/api/privacidad", headers=ana).json()
    assert r["aceptada"] is False and r["fecha"] is None
    assert any("Ley 1581" in p for p in r["parrafos"])
    assert c.post("/api/privacidad", headers=ana, json={"acepto": False}).status_code == 422
    ok = c.post("/api/privacidad", headers=ana, json={"acepto": True}).json()
    assert ok["aceptada"] is True and ok["fecha"]
    assert c.get("/api/privacidad", headers=ana).json()["aceptada"] is True
