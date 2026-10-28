"""Endpoints del panel (``routes/panel.py``): permisos, cifras, CSV y lectura.

Se siembra una base SQLite en memoria con casos conocidos y se comparan las
cifras con lo esperado a mano. También se prueba que los endpoints son de
solo lectura (mismos conteos antes y después) y que sin sesión o sin rol
admin responden 401/403 desde el servidor.
"""

from __future__ import annotations

import asyncio
import csv
import io
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from rag.api import panel_metricas as pm
from rag.api.auth import create_access_token
from rag.api.database import get_session
from rag.api.models import Base, Conversation, Feedback, Message, MessageFeedback, User
from rag.api.routes.panel import DEMO_EMAIL
from rag.api.routes.panel import router as panel_router
from rag.core import agent

_AHORA = datetime.now(UTC)
_FUENTE = [
    {
        "source": "normativa/d2324.md",
        "title": "Decreto 2324 de 1984",
        "doc_type": "normativa",
        "fragments": [{"index": 1, "content": "x", "metadata": {}}],
    }
]
_SENTENCIA = [
    {
        "source": "jurisprudencia/gieseken.md",
        "title": "Gieseken Cuello vs. DIMAR",
        "doc_type": "jurisprudencia",
        "fragments": [{"index": 1, "content": "x", "metadata": {}}],
    }
]


def _hace(dias: float) -> datetime:
    return _AHORA - timedelta(days=dias)


# (usuario, hace_dias, pregunta, respuesta, sources, ratings, esperaba)
_CASOS = [
    (
        "u1",
        1,
        pm.TEMAS_POR_ID["entrar"].preguntas[1],
        "Según la norma [doc1].",
        _FUENTE,
        (5, 5),
        None,
    ),
    (
        "u1",
        2,
        pm.TEMAS_POR_ID["entrar"].preguntas[1],
        "Según la norma [doc1].",
        _FUENTE + _SENTENCIA,
        None,
        None,
    ),
    (
        "u2",
        3,
        "¿Puedo arreglar el techo de mi kiosco? Es en Taganga, en Santa Marta.",
        agent._NO_EVIDENCE_RESPONSE,
        [],
        (1, 1),
        "si la DIMAR da permiso",
    ),
    (
        "u2",
        4,
        "¿Puedo arreglar el techo de mi kiosco? Es en Taganga, en Santa Marta.",
        agent._NO_EVIDENCE_RESPONSE,
        [],
        None,
        None,
    ),
    ("u3", 5, "¿Qué horario tiene el museo?", agent._OUT_OF_SCOPE_RESPONSE, [], None, None),
    ("u3", 6, "hola", agent._CONVERSATION_RESPONSE, [], None, None),
    (
        "u1",
        7,
        pm.TEMAS_POR_ID["hoteles"].preguntas[0],
        "No pueden [doc1].",
        _FUENTE,
        (1, 2),
        "=HYPERLINK(malo)",
    ),
    # Periodo anterior (entre 31 y 60 días): solo cuenta para la comparación.
    ("u4", 40, pm.TEMAS_POR_ID["pescar"].preguntas[0], "Sí [doc1].", _FUENTE, (5, 5), None),
    ("u1", 45, pm.TEMAS_POR_ID["entrar"].preguntas[0], "Sí [doc1].", _FUENTE, None, None),
]


async def _sembrar(factory: async_sessionmaker, demo: bool) -> None:
    async with factory() as s:
        for uid, creado in [("u1", 100), ("u2", 10), ("u3", 100), ("u4", 100)]:
            s.add(
                User(
                    id=uid,
                    email=f"{uid}persona@correo.co",
                    password_hash="x",
                    display_name=uid.upper(),
                    role="user",
                    created_at=_hace(creado),
                )
            )
        s.add(User(id="adm", email="admin@atlas.co", password_hash="x", role="admin"))
        # Encuestas del final de la conversación: una buena con comentario, una mala sin él
        # y una vieja (fuera de 30 días).
        for fid, uid, dias_atras, general, comentario in [
            ("e1", "u1", 1, 5, "Muy clara"),
            ("e2", "u2", 3, 1, None),
            ("e3", "u4", 40, 3, "Regular"),
        ]:
            s.add(
                Feedback(
                    id=fid,
                    user_id=uid,
                    user_email=f"{uid}persona@correo.co",
                    ratings={
                        "tone": general,
                        "length": general,
                        "usability": general,
                        "overall": general,
                    },
                    comment=comentario,
                    conversation_id="c0",
                    conversation_title="Título",
                    created_at=_hace(dias_atras),
                )
            )
        if demo:
            s.add(User(id="demo", email=DEMO_EMAIL, password_hash="x", role="user"))
        for i, (uid, dias, preg, resp, sources, ratings, esperaba) in enumerate(_CASOS):
            cid = f"c{i}"
            s.add(
                Conversation(
                    id=cid, user_id=uid, thread_id=cid, title=preg[:30], created_at=_hace(dias)
                )
            )
            s.add(
                Message(
                    id=f"q{i}", conversation_id=cid, role="user", text=preg, created_at=_hace(dias)
                )
            )
            s.add(
                Message(
                    id=f"a{i}",
                    conversation_id=cid,
                    role="assistant",
                    text=resp,
                    sources=sources,
                    created_at=_hace(dias) + timedelta(seconds=5),
                )
            )
            if ratings:
                s.add(
                    MessageFeedback(
                        id=f"f{i}",
                        user_id=uid,
                        conversation_id=cid,
                        message_id=f"a{i}",
                        ratings={"pertinence": ratings[0], "accuracy": ratings[1]},
                        expected_answer=esperaba,
                    )
                )
        await s.commit()


@pytest.fixture
def cliente(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[tuple[TestClient, async_sessionmaker]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "prueba-panel-secreto-largo-1234567890")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _sembrar(factory, demo=getattr(request, "param", False))

    asyncio.run(_preparar())

    async def _sesion() -> AsyncGenerator:
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(panel_router)
    app.dependency_overrides[get_session] = _sesion
    with TestClient(app) as c:
        yield c, factory
    asyncio.run(engine.dispose())


def _auth(uid: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uid, f'{uid}@x.co', role)}"}


_ADMIN = {"uid": "adm", "role": "admin"}


@pytest.mark.parametrize(
    "ruta",
    [
        "/resumen",
        "/preguntas",
        "/preguntas.csv",
        "/conversaciones/c0",
        "/encuestas",
        "/encuestas.csv",
    ],
)
def test_permisos_en_el_servidor(cliente, ruta: str) -> None:
    c, _ = cliente
    url = "/api/admin/panel" + ruta
    assert c.get(url).status_code == 401
    assert c.get(url, headers={"Authorization": "Bearer basura"}).status_code == 401
    assert c.get(url, headers=_auth("u1", "user")).status_code == 403
    # El rol se lee de la base: un token que dice "admin" de un usuario que no lo es no pasa.
    assert c.get(url, headers=_auth("u1", "admin")).status_code == 403
    assert c.get(url, headers=_auth(**_ADMIN)).status_code == 200


def test_resumen_cifras(cliente) -> None:
    c, _ = cliente
    r = c.get("/api/admin/panel/resumen?dias=30", headers=_auth(**_ADMIN)).json()
    cif = r["cifras"]
    assert r["demo"] is False
    assert cif["preguntas"] == 7
    assert cif["personas"] == 3
    assert cif["personas_nuevas"] == 2  # u2 y u3 preguntan por primera vez en el periodo
    assert cif["respuestas"] == 6  # el saludo no cuenta
    assert cif["con_fuente"] == 3
    assert cif["sin_respuesta_segura"] == 2
    assert cif["fuera_de_tema"] == 1
    assert cif["pide_aclarar"] == 0 and cif["saludos"] == 1 and cif["sin_respuesta_guardada"] == 0
    # Las partes suman el total (PQ-04).
    assert (
        cif["con_fuente"] + cif["sin_respuesta_segura"] + cif["fuera_de_tema"] + cif["pide_aclarar"]
        == cif["respuestas"]
    )
    assert cif["respuestas"] + cif["saludos"] + cif["sin_respuesta_guardada"] == cif["preguntas"]
    assert cif["calificaciones"] == 3
    assert cif["le_sirvio"] == 1
    assert cif["no_le_sirvio"] == 2
    ant = r["anterior"]
    assert ant["preguntas"] == 2 and ant["con_fuente"] == 2 and ant["personas"] == 2

    assert sum(p["preguntas"] for p in r["serie"]) == 7
    assert sum(p["sin_respuesta_segura"] for p in r["serie"]) == 2
    assert r["periodo"]["agrupacion"] == "semana"
    # Semanas de lunes a domingo, recortadas al periodo (PQ-02/03).
    from datetime import date as _date

    for p in r["serie"]:
        assert _date.fromisoformat(p["fecha"]).weekday() == 0
        assert p["fecha"] <= p["desde"] <= p["hasta"]
    assert r["serie"][0]["parcial"] or r["serie"][0]["desde"] == r["serie"][0]["fecha"]
    assert r["serie"][-1]["hasta"] == pm.clave_dia(_AHORA)

    temas = {t["id"]: t for t in r["temas"]}
    assert sum(t["preguntas"] for t in r["temas"]) == 7
    assert temas["entrar"]["preguntas"] == 2 and temas["entrar"]["le_sirvio"] == 1
    assert temas["obras"]["preguntas"] == 2 and temas["obras"]["brechas"] == 2
    assert r["temas"][-1]["id"] == pm.TEMA_OTROS

    assert r["normas"][0] == {
        "nombre": "Decreto 2324 de 1984",
        "doc_type": "normativa",
        "respuestas": 3,
    }
    assert r["normas"][1]["nombre"] == "Gieseken Cuello vs. DIMAR"
    assert r["playas"] == [{"nombre": "Taganga", "preguntas": 2}]
    assert r["sin_playa"] == 5

    assert r["personas"] == {
        "activas": 3,
        "nuevas": 2,
        "recurrentes": 1,
        "preguntas_por_persona": 2.3,
        "mediana_por_persona": 2.0,
    }

    # Brechas: 2 sin respuesta (misma pregunta, agrupadas) + 1 mal calificada.
    assert r["brechas_total"] == 3
    primera = r["brechas"][0]
    assert primera["veces"] == 2 and primera["tema"] == "obras"
    assert primera["esperaba"] == "si la DIMAR da permiso"
    assert primera["conversation_id"] == "c2"  # la más reciente
    assert r["brechas"][1]["motivo"] == "no_le_sirvio"


def test_resumen_sin_hash_ni_correos(cliente) -> None:
    c, _ = cliente
    texto = c.get("/api/admin/panel/resumen?dias=0", headers=_auth(**_ADMIN)).text
    assert "correo.co" not in texto and "@" not in texto
    assert "password" not in texto


def test_resumen_todo_y_filtro_de_tema(cliente) -> None:
    c, _ = cliente
    h = _auth(**_ADMIN)
    todo = c.get("/api/admin/panel/resumen?dias=0", headers=h).json()
    assert todo["cifras"]["preguntas"] == 9 and todo["anterior"] is None
    assert todo["periodo"]["desde"] is None
    tema = c.get("/api/admin/panel/resumen?dias=30&tema=obras", headers=h).json()
    assert tema["cifras"]["preguntas"] == 2 and [t["id"] for t in tema["temas"]] == ["obras"]
    assert c.get("/api/admin/panel/resumen?tema=nada", headers=h).status_code == 422
    for dias in ("-1", "abc", "99999", "1.5"):
        assert c.get(f"/api/admin/panel/resumen?dias={dias}", headers=h).status_code == 422


def test_resumen_periodo_vacio(cliente) -> None:
    c, factory = cliente

    async def _vaciar() -> None:
        async with factory() as s:
            for modelo in (MessageFeedback, Message, Conversation):
                for fila in (await s.execute(select(modelo))).scalars():
                    await s.delete(fila)
            await s.commit()

    asyncio.run(_vaciar())
    r = c.get("/api/admin/panel/resumen?dias=7", headers=_auth(**_ADMIN)).json()
    assert r["cifras"]["preguntas"] == 0 and r["cifras"]["respuestas"] == 0
    assert len(r["serie"]) == 7 and all(p["preguntas"] == 0 for p in r["serie"])
    assert r["periodo"]["agrupacion"] == "dia"
    assert r["temas"] == [] and r["brechas"] == []


@pytest.mark.parametrize("cliente", [True], indirect=True)
def test_aviso_demo(cliente) -> None:
    c, _ = cliente
    assert c.get("/api/admin/panel/resumen", headers=_auth(**_ADMIN)).json()["demo"] is True
    # PQ-133: el aviso también sale para todo /admin y en la primera fila del CSV.
    assert c.get("/api/admin/panel/demo", headers=_auth(**_ADMIN)).json() == {"demo": True}
    csv_txt = c.get("/api/admin/panel/preguntas.csv", headers=_auth(**_ADMIN)).text
    assert csv_txt.lstrip('\ufeff"').startswith("Datos de demostración")


def test_preguntas_filtros_y_paginas(cliente) -> None:
    c, _ = cliente
    h = _auth(**_ADMIN)
    r = c.get("/api/admin/panel/preguntas?dias=30&page_size=5", headers=h).json()
    assert r["total"] == 7 and len(r["items"]) == 5
    fechas = [i["fecha"] for i in r["items"]]
    assert fechas == sorted(fechas, reverse=True)
    assert r["items"][0]["persona"] == "U1"
    assert r["items"][0]["calificacion"] == "util"
    p2 = c.get("/api/admin/panel/preguntas?dias=30&page_size=5&page=2", headers=h).json()
    assert len(p2["items"]) == 2

    def total(q: str) -> int:
        return c.get(f"/api/admin/panel/preguntas?dias=30&{q}", headers=h).json()["total"]

    assert total("resultado=con_fuente") == 3
    assert total("resultado=sin_respuesta_segura") == 2
    assert total("resultado=no_le_sirvio") == 2
    assert total("resultado=fuera_de_tema") == 1
    assert total("tema=entrar&resultado=con_fuente") == 2
    assert c.get("/api/admin/panel/preguntas?resultado=otra", headers=h).status_code == 422


def test_csv_bom_y_formulas_escapadas(cliente) -> None:
    c, _ = cliente
    r = c.get("/api/admin/panel/preguntas.csv?dias=30", headers=_auth(**_ADMIN))
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    filas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(filas) == 1 + 7
    assert filas[0][:3] == ["Fecha (hora de Colombia)", "Participante", "Tipo de usuario de playa"]
    assert "Fuentes citadas" in filas[0] and "Normas citadas" not in filas[0]  # PQ-49
    assert not any("norma citada" in ",".join(f) for f in filas)
    col = filas[0].index("Lo que esperaba")
    esperaba = [f[col] for f in filas[1:] if f[col]]
    assert "'=HYPERLINK(malo)" in esperaba
    assert all("correo.co" not in ",".join(f) for f in filas)


def test_conversacion_detalle(cliente) -> None:
    c, _ = cliente
    h = _auth(**_ADMIN)
    r = c.get("/api/admin/panel/conversaciones/c1", headers=h).json()
    assert r["persona"] == "U1"
    assert [m["role"] for m in r["mensajes"]] == ["user", "assistant"]
    assert r["mensajes"][1]["resultado"] == "con_fuente"
    assert r["mensajes"][1]["fuentes"] == [
        {"nombre": "Decreto 2324 de 1984", "doc_type": "normativa"},
        {"nombre": "Gieseken Cuello vs. DIMAR", "doc_type": "jurisprudencia"},
    ]
    malo = c.get("/api/admin/panel/conversaciones/c2", headers=h).json()["mensajes"][1]
    assert malo["calificacion"] == "no_util" and malo["esperaba"] == "si la DIMAR da permiso"
    assert c.get("/api/admin/panel/conversaciones/nada", headers=h).status_code == 404


def test_solo_lectura(cliente) -> None:
    c, factory = cliente

    async def _conteos() -> tuple[int, ...]:
        async with factory() as s:
            return tuple(
                [
                    (await s.execute(select(func.count()).select_from(m))).scalar_one()
                    for m in (User, Conversation, Message, MessageFeedback)
                ]
            )

    antes = asyncio.run(_conteos())
    h = _auth(**_ADMIN)
    for ruta in (
        "/resumen?dias=0",
        "/preguntas",
        "/preguntas.csv",
        "/conversaciones/c0",
        "/encuestas",
    ):
        assert c.get("/api/admin/panel" + ruta, headers=h).status_code == 200
    assert asyncio.run(_conteos()) == antes


def test_filtros_de_opiniones_y_fuentes_por_tipo(cliente) -> None:
    c, _ = cliente
    h = _auth(**_ADMIN)

    def total(q: str) -> int:
        return c.get(f"/api/admin/panel/preguntas?dias=30&{q}", headers=h).json()["total"]

    assert total("resultado=calificadas") == 3
    assert total("resultado=le_sirvio") == 1
    assert total("resultado=con_esperaba") == 2
    items = c.get("/api/admin/panel/preguntas?dias=30", headers=h).json()["items"]
    dos_fuentes = next(i for i in items if i["fuentes"] == 2)
    assert dos_fuentes["fuentes_sentencias"] == 1


def test_encuestas(cliente) -> None:
    c, _ = cliente
    h = _auth(**_ADMIN)
    r = c.get("/api/admin/panel/encuestas?dias=30", headers=h).json()
    assert r["total"] == 2
    assert r["promedios"] == {
        "general": 3.0,
        "claridad": 0.0,
        "tono": 3.0,
        "largo": 3.0,
        "facilidad": 3.0,
    }
    assert r["items"][0]["claridad"] is None  # encuesta vieja, sin claridad
    primera = r["items"][0]
    assert (
        primera["persona"] == "U1"
        and primera["general"] == 5
        and primera["comentario"] == "Muy clara"
    )
    assert "@" not in str(r)
    assert c.get("/api/admin/panel/encuestas?dias=0", headers=h).json()["total"] == 3
    assert c.get("/api/admin/panel/encuestas?dias=30&filtro=malas", headers=h).json()["total"] == 1
    assert (
        c.get("/api/admin/panel/encuestas?dias=0&filtro=con_comentario", headers=h).json()["total"]
        == 2
    )
    assert c.get("/api/admin/panel/encuestas?filtro=otra", headers=h).status_code == 422


def test_encuestas_csv_con_comentarios(cliente) -> None:
    # A9: los comentarios de la encuesta son evidencia del informe (PDF p. 9).
    c, _ = cliente
    r = c.get("/api/admin/panel/encuestas.csv?dias=0", headers=_auth(**_ADMIN))
    assert r.headers["content-type"].startswith("text/csv")
    filas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(filas) == 1 + 3
    assert filas[0][4:7] == [
        "Claridad de las respuestas",
        "Facilidad de uso",
        "Calificación general",
    ]
    assert "Muy clara" in [f[-1] for f in filas[1:]]
    assert "@" not in r.content.decode("utf-8-sig")
