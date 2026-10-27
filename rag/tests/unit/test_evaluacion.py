"""Evaluación del ejercicio de validación (``rag/api/ejercicio.py`` y
``routes/evaluacion.py``), contra el documento del profe y la planilla:

- F1-F3 de 1 a 3, Cv dentro del rango de Ct (S 3-6, I 7-9, A 10-12).
- Dos calificaciones por pregunta, una por sede; diferencias al comité.
- Premios: mayor Cv por nivel sin desempate automático; constancia por días,
  luego preguntas válidas, luego puntaje.
- Excel con las columnas de la hoja "Evaluación" e ID de pregunta numérico.
"""

from __future__ import annotations

import asyncio
import io
import re
import zipfile
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from rag.api import ejercicio as ej
from rag.api.auth import create_access_token
from rag.api.database import get_session
from rag.api.models import (
    Base,
    Conversation,
    ExerciseProfile,
    Message,
    User,
    ValidatorProfile,
)
from rag.api.routes.evaluacion import router as evaluacion_router
from rag.api.routes.validacion import router as validacion_router

# ── Reglas puras ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("f", "ct", "cv", "ok"),
    [
        ((1, 2, 3), "S", 3, True),
        ((3, 3, 3), "S", 6, True),
        ((1, 1, 1), "S", 7, False),
        ((1, 1, 1), "I", 7, True),
        ((1, 1, 1), "I", 10, False),
        ((1, 1, 1), "A", 12, True),
        ((1, 1, 1), "A", 9, False),
        ((0, 1, 1), "S", 3, False),
        ((1, 4, 1), "S", 3, False),
    ],
)
def test_validar_calificacion(f: tuple, ct: str, cv: int, ok: bool) -> None:
    assert (ej.validar_calificacion(*f, ct, cv) is None) is ok


def _cal(
    evaluador: str,
    sede: str,
    ct: str,
    cv: int,
    f: int = 2,
    final: bool = False,
    valida: bool = True,
):
    return ej.Calificacion(
        evaluador_id=evaluador,
        evaluador=evaluador,
        sede=sede,
        f1=f,
        f2=f,
        f3=f,
        ct=ct,
        cv=cv,
        total=3 * f + cv,
        valida=valida,
        observaciones=None,
        es_final=final,
    )


def test_calificacion_oficial() -> None:
    assert ej.calificacion_oficial([]).estado == "sin_evaluar"
    assert ej.calificacion_oficial([_cal("a", "Santa Marta", "S", 4)]).estado == "una_evaluacion"
    concord = ej.calificacion_oficial(
        [_cal("a", "Santa Marta", "I", 7), _cal("b", "Barranquilla", "I", 8)]
    )
    assert concord.estado == "concordante" and concord.cv == 8 and concord.total == 14
    assert concord.evaluo == "a, b"
    distinto_nivel = [_cal("a", "Santa Marta", "S", 6), _cal("b", "Barranquilla", "I", 7)]
    assert ej.calificacion_oficial(distinto_nivel).estado == "con_diferencias"
    lejos = [_cal("a", "Santa Marta", "I", 7, f=1), _cal("b", "Barranquilla", "I", 9, f=3)]
    assert ej.calificacion_oficial(lejos).estado == "con_diferencias"
    final = ej.calificacion_oficial(distinto_nivel + [_cal("c", "", "I", 9, final=True)])
    assert final.estado == "final" and final.cv == 9 and final.reviso == "c"
    # PQ-59: dos "no válida" concordantes siguen siendo no válidas.
    no_validas = [
        _cal("a", "Santa Marta", "S", 4, valida=False),
        _cal("b", "Barranquilla", "S", 4, valida=False),
    ]
    of = ej.calificacion_oficial(no_validas)
    assert of.estado == "concordante" and of.valida is False


def _of(
    mid: str, codigo: str, ct: str, cv: int, dia: int, valida: bool = True, total: int | None = None
):
    return ej.PreguntaOficial(
        mid,
        codigo,
        datetime(2026, 10, dia, 10, tzinfo=UTC),
        f"pregunta {mid}",
        ej.Oficial("final", 2, 2, 2, ct, cv, total if total is not None else 6 + cv, valida),
    )


def test_mejor_pregunta_sin_desempate_automatico() -> None:
    ps = [
        _of("q1", "P001", "S", 6, 1),
        _of("q2", "P002", "S", 6, 2, total=21),  # mayor total: no desempata
        _of("q3", "P003", "S", 5, 3),
        _of("q4", "P004", "I", 9, 3),
        _of("q5", "P005", "A", 12, 4, valida=False),  # no válida: no cuenta
    ]
    r = ej.mejores_por_nivel(ps)
    assert r["S"]["ganadora"] is None and r["S"]["decide_comite"]
    assert [f["message_id"] for f in r["S"]["empatadas"]] == ["q1", "q2"]
    assert r["I"]["ganadora"]["message_id"] == "q4"
    assert r["A"]["ganadora"] is None and not r["A"]["decide_comite"]
    elegida = ej.mejores_por_nivel(ps, {"S": "q2"})
    assert elegida["S"]["ganadora"]["message_id"] == "q2"


def test_constancia_dias_luego_preguntas_luego_puntaje() -> None:
    ps = [
        # P001: 3 días
        _of("a1", "P001", "S", 3, 1),
        _of("a2", "P001", "S", 3, 2),
        _of("a3", "P001", "S", 3, 3),
        # P002: 2 días, 3 preguntas
        _of("b1", "P002", "S", 3, 1),
        _of("b2", "P002", "S", 3, 1),
        _of("b3", "P002", "S", 3, 2),
        # P003: 2 días, 3 preguntas, más puntaje
        _of("c1", "P003", "A", 12, 1),
        _of("c2", "P003", "A", 12, 2),
        _of("c3", "P003", "A", 12, 2),
        # P004: 30 preguntas en un día no gana
        *[_of(f"d{i}", "P004", "S", 3, 5) for i in range(30)],
    ]
    orden = [f["codigo"] for f in ej.ranking_participantes(ps)]
    assert orden[:3] == ["P001", "P003", "P002"]


def test_xlsx_minimo_se_abre_como_zip() -> None:
    datos = ej.libro_xlsx([("Hoja", [["A", "B"], [1, "=1+1"]], [10, 10])])
    z = zipfile.ZipFile(io.BytesIO(datos))
    assert "xl/worksheets/sheet1.xml" in z.namelist()
    assert ej.celda_segura("=1+1") == "'=1+1" and ej.celda_segura("hola") == "hola"


# ── Endpoints ────────────────────────────────────────────────────────────────

_AHORA = datetime.now(UTC)
PREGUNTAS = [
    ("q1", "u1", "Trabajo vendiendo bebidas en la playa. ¿Qué requisitos debo cumplir?", 3),
    ("q2", "u1", "Un hotel instaló carpas que impiden el paso. ¿Ante qué autoridad me quejo?", 2),
    ("q3", "u2", "La playa frente a mi apartamento se erosiona. ¿Qué regulación aplica?", 1),
]


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", "prueba-evaluacion-secreto-largo-1234567")
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
            for uid, rol, nombre in [
                ("u1", "user", "Ana Secreta"),
                ("u2", "user", "Beto Secreto"),
                ("sm", "evaluador", "Semillerista SM"),
                ("sm2", "evaluador", "Otro SM"),
                ("bq", "evaluador", "Semillerista BQ"),
                ("sin", "evaluador", "Sin sede"),
                ("com", "comite", "Comité"),
                ("ana", "comite", "Ana María Muelle"),
                ("san", "comite", "Sandra Otero"),
                ("cam", "comite", "Camilo Botero"),
            ]:
                s.add(
                    User(
                        id=uid,
                        email=f"{uid}@x.co",
                        password_hash="x",
                        display_name=nombre,
                        role=rol,
                    )
                )
            await s.flush()
            s.add(ExerciseProfile(user_id="u1", codigo="P001", tipo_playa=3))
            s.add(ExerciseProfile(user_id="u2", codigo="P002", tipo_playa=1))
            s.add(ExerciseProfile(user_id="sm", sede="Santa Marta"))
            s.add(ExerciseProfile(user_id="sm2", sede="Santa Marta"))
            s.add(ExerciseProfile(user_id="bq", sede="Barranquilla"))
            # Reunión del 20-oct: validación jurídica por sede y gestión costera.
            s.add(ExerciseProfile(user_id="ana", sede="Santa Marta"))
            s.add(ExerciseProfile(user_id="san", sede="Barranquilla"))
            s.add(ValidatorProfile(user_id="ana", tipo="juridico"))
            s.add(ValidatorProfile(user_id="san", tipo="juridico"))
            s.add(ValidatorProfile(user_id="cam", tipo="costero"))
            for i, (mid, uid, texto, dias) in enumerate(PREGUNTAS):
                cid = f"c{i}"
                cuando = _AHORA - timedelta(days=dias)
                s.add(Conversation(id=cid, user_id=uid, thread_id=cid, created_at=cuando))
                s.add(
                    Message(id=mid, conversation_id=cid, role="user", text=texto, created_at=cuando)
                )
                s.add(
                    Message(
                        id=f"a{i}",
                        conversation_id=cid,
                        role="assistant",
                        text=f"Respuesta {i}",
                        created_at=cuando + timedelta(seconds=5),
                    )
                )
            await s.commit()

    asyncio.run(_preparar())

    async def _sesion() -> AsyncGenerator:
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(evaluacion_router)
    app.include_router(validacion_router)
    app.dependency_overrides[get_session] = _sesion
    with TestClient(app) as c:
        yield c
    asyncio.run(engine.dispose())


def _h(uid: str, rol: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uid, f'{uid}@x.co', rol)}"}


def _hs() -> tuple[dict[str, str], ...]:
    """Encabezados de cada cuenta (se crean dentro de la prueba, con la clave JWT ya puesta)."""
    return (
        _h("sm", "evaluador"),
        _h("sm2", "evaluador"),
        _h("bq", "evaluador"),
        _h("sin", "evaluador"),
        _h("com", "comite"),
        _h("u1", "user"),
    )


def _sm(c: TestClient, mid: str) -> tuple[dict[str, str], dict[str, str]]:
    """(semillerista de Santa Marta asignado a la pregunta, el otro de Santa Marta)."""
    SM, SM2, *_ = _hs()  # noqa: N806
    if c.get(f"/api/evaluacion/preguntas/{mid}", headers=SM).status_code == 200:
        return SM, SM2
    return SM2, SM


def _validar_todas(c: TestClient, h: dict[str, str]) -> int:
    """La validadora marca "de acuerdo" en lote todo lo de su sede."""
    b = c.get("/api/evaluacion/validacion/bandeja?estado=por_validar&page_size=100", headers=h)
    ids = [e["id"] for i in b.json()["items"] for e in i["evaluaciones"]]
    if not ids:
        return 0
    r = c.post(
        "/api/evaluacion/validacion/lote", headers=h, json={"evaluaciones": ids, "confirmar": True}
    )
    assert r.status_code == 200, r.text
    return r.json()["validadas"]


def _cal_json(ct: str, cv: int, f: int = 2, valida: bool = True, obs: str | None = None) -> dict:
    return {"f1": f, "f2": f, "f3": f, "ct": ct, "cv": cv, "valida": valida, "observaciones": obs}


def test_permisos(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    assert c.get("/api/evaluacion/bandeja").status_code == 401
    assert c.get("/api/evaluacion/bandeja", headers=USER).status_code == 403
    assert c.get("/api/evaluacion/bandeja", headers=SM).status_code == 200
    for ruta in ("/api/evaluacion/premios", "/api/evaluacion/exportar.xlsx"):
        assert c.get(ruta, headers=SM).status_code == 403
        assert c.get(ruta, headers=COM).status_code == 200
    assert (
        c.put("/api/evaluacion/preguntas/q1/final", headers=SM, json=_cal_json("S", 4)).status_code
        == 403
    )


def test_bandeja_anonima_y_ficha_con_rubrica(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    A, _ = _sm(c, "q1")  # noqa: N806
    r = c.get("/api/evaluacion/bandeja?estado=pendientes", headers=A).json()
    numeros = [i["numero"] for i in r["items"]]
    assert numeros == sorted(numeros) and numeros[0] == 1  # las más antiguas primero
    assert (
        r["items"][0]["codigo"] == "P001" and r["items"][0]["tipo_playa_nombre"] == "Comerciantes"
    )
    texto = str(r)
    assert "Ana" not in texto and "@" not in texto
    ficha = c.get("/api/evaluacion/preguntas/q1", headers=A).json()
    assert ficha["respuesta"] == "Respuesta 0" and ficha["puede_evaluar"] and ficha["otras"] is None
    cat = c.get("/api/evaluacion/catalogo", headers=SM).json()
    assert cat["rangos"] == {"S": [3, 6], "I": [7, 9], "A": [10, 12]}
    assert cat["forma"]["f1"]["niveles"]["3"].startswith("Identifica claramente")


def test_rango_de_cv_y_una_por_sede(cliente) -> None:
    c = cliente
    _, _, BQ, SIN, COM, USER = _hs()  # noqa: N806
    SM, SM2 = _sm(c, "q1")  # noqa: N806  (asignado y el otro de Santa Marta)
    assert (
        c.put("/api/evaluacion/preguntas/q1/mia", headers=SM, json=_cal_json("S", 8)).status_code
        == 422
    )
    assert (
        c.put("/api/evaluacion/preguntas/q1/mia", headers=SIN, json=_cal_json("S", 4)).status_code
        == 409
    )
    r = c.put("/api/evaluacion/preguntas/q1/mia", headers=SM, json=_cal_json("S", 4))
    assert r.status_code == 200 and r.json()["mia"]["total"] == 10 and r.json()["mia"]["forma"] == 6
    # Otro evaluador de la misma sede ya no puede; el de la otra sede sí.
    segundo = c.put("/api/evaluacion/preguntas/q1/mia", headers=SM2, json=_cal_json("S", 4))
    assert segundo.status_code == 409 and "otro semillerista" in segundo.json()["detail"]
    # Corregir la propia sí se puede.
    assert (
        c.put("/api/evaluacion/preguntas/q1/mia", headers=SM, json=_cal_json("S", 5)).status_code
        == 200
    )
    r2 = c.put("/api/evaluacion/preguntas/q1/mia", headers=BQ, json=_cal_json("S", 5))
    assert r2.json()["estado"] == "concordante"
    pend = c.get("/api/evaluacion/bandeja?estado=pendientes", headers=SM).json()
    assert 1 not in [i["numero"] for i in pend["items"]]
    assert c.get("/api/evaluacion/bandeja?estado=mias", headers=SM).json()["total"] == 1


def test_diferencias_y_final_del_comite(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    SM, _ = _sm(c, "q2")  # noqa: N806
    c.put("/api/evaluacion/preguntas/q2/mia", headers=SM, json=_cal_json("S", 6))
    r = c.put(
        "/api/evaluacion/preguntas/q2/mia", headers=BQ, json=_cal_json("I", 8, obs="Hay conflicto")
    )
    assert r.json()["estado"] == "con_diferencias"
    assert c.get("/api/evaluacion/bandeja?estado=pendientes", headers=COM).json()["total"] == 1
    ficha = c.get("/api/evaluacion/preguntas/q2", headers=COM).json()
    assert len(ficha["otras"]) == 2 and ficha["es_comite"]
    f = c.put("/api/evaluacion/preguntas/q2/final", headers=COM, json=_cal_json("I", 9, f=3))
    assert f.json()["estado"] == "final" and f.json()["oficial"]["total"] == 18
    # Con final, los evaluadores ya no la cambian.
    assert (
        c.put("/api/evaluacion/preguntas/q2/mia", headers=SM, json=_cal_json("S", 3)).status_code
        == 409
    )


def test_resumen_premios_y_excel(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    for q, ct, cv in [("q1", "S", 6), ("q3", "S", 6)]:
        c.put(f"/api/evaluacion/preguntas/{q}/mia", headers=_sm(c, q)[0], json=_cal_json(ct, cv))
        c.put(f"/api/evaluacion/preguntas/{q}/mia", headers=BQ, json=_cal_json(ct, cv))
    # Reunión del 20-oct (T2): nada cuenta hasta que la validación jurídica
    # esté de acuerdo con las evaluaciones (4 = 2 preguntas x 2 sedes).
    antes = c.get("/api/evaluacion/premios", headers=COM).json()
    assert antes["por_validar"] == 4 and antes["solo_revisadas"]
    assert antes["mejor_pregunta"]["S"]["ganadora"] is None
    assert not antes["mejor_pregunta"]["S"]["empatadas"]
    assert c.get("/api/evaluacion/resumen", headers=SM).json()["evaluadas"] == 0
    for v in ("ana", "san"):
        _validar_todas(c, _h(v, "comite"))
    assert c.get("/api/evaluacion/premios", headers=COM).json()["por_validar"] == 0
    res = c.get("/api/evaluacion/resumen", headers=SM).json()
    assert res["preguntas_registradas"] == 3 and res["evaluadas"] == 2
    assert res["por_nivel"] == {"S": 2, "I": 0, "A": 0} and res["promedio_total"] == 12
    avance = {a["evaluador"] for a in res["avance_evaluadores"]}
    assert "Semillerista BQ" in avance and avance <= {
        "Semillerista SM",
        "Otro SM",
        "Semillerista BQ",
    }

    p = c.get("/api/evaluacion/premios", headers=COM).json()
    assert (
        p["mejor_pregunta"]["S"]["decide_comite"] and p["mejor_pregunta"]["S"]["ganadora"] is None
    )
    assert "gratificacion" in p and "acumulado" not in p
    assert {f["codigo"] for f in p["participacion_por_dia"]} == {"P001", "P002"}
    assert (
        c.put(
            "/api/evaluacion/premios/I/ganadora", headers=COM, json={"message_id": "q1"}
        ).status_code
        == 409
    )
    assert (
        c.put(
            "/api/evaluacion/premios/S/ganadora", headers=COM, json={"message_id": "q2"}
        ).status_code
        == 422
    )
    elegido = c.put(
        "/api/evaluacion/premios/S/ganadora", headers=COM, json={"message_id": "q3"}
    ).json()
    assert elegido["mejor_pregunta"]["S"]["ganadora"]["message_id"] == "q3"

    x = c.get("/api/evaluacion/exportar.xlsx", headers=COM)
    assert x.headers["content-type"].startswith("application/vnd.openxmlformats")
    z = zipfile.ZipFile(io.BytesIO(x.content))
    libro = z.read("xl/workbook.xml").decode()
    assert re.findall(r'name="([^"]+)"', libro) == [
        "Evaluación",
        "Calificaciones",
        "Resumen",
        "Premios y participación",
        "Puntaje por interacción",
    ]
    # PDF p. 5: número, pregunta, categoría, puntos y acumulado por interacción.
    inter = z.read("xl/worksheets/sheet5.xml").decode()
    for col in ("ID Usuario", "Categoría (Ct)", "Puntos (Puntaje Total)", "Puntaje acumulado"):
        assert col in inter
    assert "Secreta" not in inter
    hoja = z.read("xl/worksheets/sheet1.xml").decode()
    for col in ("ID pregunta", "ID Usuario", "Fecha", "Hora", "Tipo de Usuario de Playa", "Revisó"):
        assert col in hoja
    assert '<c r="A2"><v>1</v></c>' in hoja  # ID de pregunta numérico
    # B22: mismas validaciones que la planilla (listas, Cv 3-12, Cv en rojo fuera de rango).
    assert '<formula1>"1,2,3"</formula1>' in hoja
    assert "S - Sencillo,I - Intermedio,A - Avanzado" in hoja and "Tipo 5. Turistas" in hoja
    assert "<formula1>3</formula1><formula2>12</formula2>" in hoja
    assert 'conditionalFormatting sqref="L2:L' in hoja
    assert "<dxfs" in z.read("xl/styles.xml").decode()
    assert "Tipo 3. Comerciantes" in hoja and "S - Sencillo" in hoja
    assert "Secreta" not in hoja
    # Revisó: la validadora jurídica de cada sede y la fecha.
    assert re.search(
        r"Ana María Muelle \(\d{4}-\d{2}-\d{2}\), Sandra Otero \(\d{4}", hoja
    ) or re.search(r"Sandra Otero \(\d{4}-\d{2}-\d{2}\), Ana María Muelle \(\d{4}", hoja)


def test_constancia_empate_total_lo_decide_el_comite() -> None:
    ps = [
        _of("a1", "P002", "S", 3, 1),
        _of("b1", "P001", "S", 3, 1),
        _of("c1", "P003", "S", 3, 2, total=1),
    ]
    filas = ej.ranking_participantes(ps)
    assert [f["empate"] for f in filas] == [True, True, False]
    assert not any(f["empate"] for f in ej.ranking_participantes(ps[:1]))


def test_concordantes_por_validar_del_comite(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    c.put("/api/evaluacion/preguntas/q1/mia", headers=_sm(c, "q1")[0], json=_cal_json("S", 4))
    r = c.put("/api/evaluacion/preguntas/q1/mia", headers=BQ, json=_cal_json("S", 5))
    assert r.json()["estado"] == "concordante"
    b = c.get("/api/evaluacion/bandeja?estado=por_validar", headers=COM).json()
    assert [i["message_id"] for i in b["items"]] == ["q1"] and b["conteos"]["por_validar"] == 1
    # El comité la valida guardando la final: sale de "por validar".
    c.put("/api/evaluacion/preguntas/q1/final", headers=COM, json=_cal_json("S", 5))
    assert c.get("/api/evaluacion/bandeja?estado=por_validar", headers=COM).json()["total"] == 0


def test_id_de_pregunta_persistente(cliente) -> None:
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806
    antes = {
        i["message_id"]: i["numero"]
        for i in c.get("/api/evaluacion/bandeja?estado=todas", headers=COM).json()["items"]
    }
    assert sorted(antes.values()) == list(range(1, len(antes) + 1))
    otra = c.get("/api/evaluacion/bandeja?estado=todas", headers=COM).json()["items"]
    assert {i["message_id"]: i["numero"] for i in otra} == antes


def test_asignacion_automatica_balanceada(cliente) -> None:
    """T1 (reunión del 20-oct): cada pregunta queda asignada a 1 semillerista de
    cada sede, repartiendo por igual; cada uno ve solo las suyas."""
    c = cliente
    SM, SM2, BQ, SIN, COM, USER = _hs()  # noqa: N806

    def numeros(h: dict[str, str]) -> set[int]:
        r = c.get("/api/evaluacion/bandeja?estado=todas", headers=h).json()
        return {i["numero"] for i in r["items"]}

    sm1, sm2, bq = numeros(SM), numeros(SM2), numeros(BQ)
    assert sm1 | sm2 == {1, 2, 3} and not sm1 & sm2  # Santa Marta: cada pregunta a uno solo
    assert abs(len(sm1) - len(sm2)) <= 1  # repartido por igual
    assert bq == {1, 2, 3}  # Barranquilla tiene un solo semillerista
    assert numeros(SIN) == set()  # sin sede no recibe preguntas
    # La que no le tocó no la puede abrir ni calificar.
    ajena = "q1" if 1 in sm2 else ("q2" if 2 in sm2 else "q3")
    assert c.get(f"/api/evaluacion/preguntas/{ajena}", headers=SM).status_code == 403
    # La asignación es estable: otra lectura da lo mismo.
    assert numeros(SM) == sm1


def test_asignacion_simultanea_no_duplica(tmp_path) -> None:
    """Revisor (plan v2, punto 2): dos lecturas a la vez no asignan dos veces
    la misma pregunta (clave única pregunta+sede y reintento)."""
    from sqlalchemy import func, select

    from rag.api.models import QuestionAssignment
    from rag.api.routes.evaluacion import _cargar

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _correr() -> tuple[int, int]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(User(id="u1", email="u1@x.co", password_hash="x", role="user"))
            for uid, sede in [("e1", "Santa Marta"), ("e2", "Santa Marta"), ("e3", "Barranquilla")]:
                s.add(User(id=uid, email=f"{uid}@x.co", password_hash="x", role="evaluador"))
                s.add(ExerciseProfile(user_id=uid, sede=sede))
            s.add(ExerciseProfile(user_id="u1", codigo="P001", tipo_playa=1))
            for i in range(30):
                s.add(Conversation(id=f"c{i}", user_id="u1", thread_id=f"c{i}", created_at=_AHORA))
                s.add(
                    Message(
                        id=f"m{i}",
                        conversation_id=f"c{i}",
                        role="user",
                        text=f"Pregunta {i}",
                        created_at=_AHORA + timedelta(seconds=i),
                    )
                )
            await s.commit()

        async def leer() -> None:
            async with factory() as s:
                await _cargar(s)

        await asyncio.gather(leer(), leer(), leer())
        async with factory() as s:
            filas = (
                await s.execute(select(func.count()).select_from(QuestionAssignment))
            ).scalar_one()
            distintas = (
                await s.execute(
                    select(func.count()).select_from(
                        select(QuestionAssignment.message_id, QuestionAssignment.sede)
                        .distinct()
                        .subquery()
                    )
                )
            ).scalar_one()
        await engine.dispose()
        return filas, distintas

    filas, distintas = asyncio.run(_correr())
    assert filas == distintas == 60  # 30 preguntas x 2 sedes, sin duplicados


def test_validacion_juridica_conversacion_y_pertinencia(cliente) -> None:
    """Reunión del 20-oct (T2-T4, E7): cada evaluación va a la validadora de
    su sede; "No de acuerdo" abre la conversación; el semillerista corrige y
    vuelve a validarse; Camilo marca pertinencia; "no pertinente" sale de
    premios. Los participantes siguen anónimos."""
    c = cliente
    _, _, BQ, SIN, COM, USER = _hs()  # noqa: N806
    SM, _ = _sm(c, "q1")  # noqa: N806
    ANA, SAN, CAM = _h("ana", "comite"), _h("san", "comite"), _h("cam", "comite")  # noqa: N806
    c.put("/api/evaluacion/preguntas/q1/mia", headers=SM, json=_cal_json("S", 4))
    url_b = "/api/evaluacion/validacion/bandeja?estado=por_validar"
    b = c.get(url_b, headers=ANA).json()
    assert b["tipo"] == "juridico" and b["sede"] == "Santa Marta" and b["total"] == 1
    assert "Secreta" not in str(b) and "@" not in str(b)
    assert c.get(url_b, headers=SAN).json()["total"] == 0  # Barranquilla aún no evaluó
    eid = b["items"][0]["evaluaciones"][0]["id"]
    url = f"/api/evaluacion/validacion/evaluaciones/{eid}"
    # Desacuerdo sin explicar: no.
    assert c.put(url, headers=ANA, json={"de_acuerdo": False}).status_code == 422
    # Otra sede, gestión costera, semillerista: no validan esta.
    for h in (SAN, CAM, SM):
        assert c.put(url, headers=h, json={"de_acuerdo": True}).status_code == 403
    r = c.put(
        url, headers=ANA, json={"de_acuerdo": False, "comentario": "Es intermedia: hay conflicto"}
    )
    assert r.json()["evaluacion"]["estado"] == "en_conversacion"
    # El autor ve su conversación; el semillerista de la otra sede, no.
    assert c.get(url, headers=SM).status_code == 200
    assert c.get(url, headers=BQ).status_code == 403
    c.post(f"{url}/comentarios", headers=SM, json={"texto": "Tiene razón, la corrijo"})
    assert c.post(f"{url}/comentarios", headers=BQ, json={"texto": "x"}).status_code == 403
    c.put("/api/evaluacion/preguntas/q1/mia", headers=SM, json=_cal_json("I", 8))
    d = c.get(url, headers=SM).json()
    assert [e["tipo"] for e in d["hilo"]] == ["desacuerdo", "comentario", "correccion"]
    assert "Ct S → I" in d["hilo"][-1]["texto"] and "Cv 4 → 8" in d["hilo"][-1]["texto"]
    assert d["evaluacion"]["estado"] == "por_validar"  # tras corregir, vuelve a validarse
    assert (
        c.put(url, headers=ANA, json={"de_acuerdo": True}).json()["evaluacion"]["estado"]
        == "validada"
    )
    # Barranquilla evalúa igual y Sandra valida: la oficial queda "validada".
    c.put("/api/evaluacion/preguntas/q1/mia", headers=BQ, json=_cal_json("I", 8))
    _validar_todas(c, SAN)
    ficha = c.get("/api/evaluacion/preguntas/q1", headers=COM).json()
    assert ficha["oficial"]["estado"] == "validada" and ficha["oficial"]["total"] == 14
    # Gestión costera: solo Camilo marca pertinencia; "no" la saca de premios.
    url_p = "/api/evaluacion/validacion/preguntas/q1/pertinencia"
    assert c.put(url_p, headers=ANA, json={"pertinente": False}).status_code == 403
    assert c.get("/api/evaluacion/premios", headers=COM).json()["mejor_pregunta"]["I"]["ganadora"]
    assert (
        c.put(
            url_p, headers=CAM, json={"pertinente": False, "comentario": "No es de playas"}
        ).status_code
        == 200
    )
    premios = c.get("/api/evaluacion/premios", headers=COM).json()
    assert premios["mejor_pregunta"]["I"]["ganadora"] is None
    costera = c.get("/api/evaluacion/validacion/bandeja?estado=todas", headers=CAM).json()
    assert costera["tipo"] == "costero" and costera["items"][0]["pertinente"] is False
