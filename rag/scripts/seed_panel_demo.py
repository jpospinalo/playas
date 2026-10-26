"""Semilla de DEMOSTRACIÓN para el panel de administración (solo SQLite local).

Crea una base SQLite con ~480 preguntas de varios meses, personas variadas,
respuestas con y sin norma citada, respuestas fijas del agente (fuera de tema,
pide aclarar, saludos, sin evidencia) y calificaciones buenas y malas con
"lo que esperaba". Es reproducible: la misma ``--semilla`` da los mismos datos.

Los nombres de normas y sentencias son los títulos reales del corpus
(``data/documents/gold``), pero **las preguntas, personas y calificaciones son
inventadas**. Por eso crea la cuenta marcador ``demo-seed@atlas.local``: con
ella el panel muestra el aviso "Datos de demostración".

Nunca toca PostgreSQL ni AWS: solo acepta una ruta de archivo SQLite.

Uso (desde ``rag/``):
    uv run python scripts/seed_panel_demo.py --db data/panel-demo.db --reset
    DATABASE_URL=sqlite+aiosqlite:///./data/panel-demo.db make app

Cuenta de administrador de la demo (solo local): admin@atlas.demo / panel-demo-2026
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from rag.api import panel_metricas as pm  # noqa: E402
from rag.api.models import (  # noqa: E402
    Base,
    Conversation,
    Feedback,
    Message,
    MessageFeedback,
    User,
)
from rag.api.passwords import hash_password  # noqa: E402
from rag.api.routes.panel import DEMO_EMAIL  # noqa: E402
from rag.core import agent  # noqa: E402

ADMIN_EMAIL = "admin@atlas.demo"
ADMIN_PASSWORD = "panel-demo-2026"  # cuenta local de demostración, no es un secreto
USUARIO_EMAIL = "persona@atlas.demo"  # usuario sin rol admin, para probar el 403

# ── Normas y sentencias (títulos reales del corpus) ──────────────────────────
N_DIMAR = "decreto-2324-de-1984"
N_PLAYAS_SM = (
    "Por medio del cual se reglamenta el uso, zonificación y horario de las playas con vocación "
    "turística del Distrito Turístico, Cultural e Histórico de Santa Marta, aptas para la "
    "realización de activiades de aprovech"
)
N_RODADERO = (
    "Por medio de la cual se reglamenta el área de playa en el Balneario Turístico El Rodadero"
)
N_COMITES = "Por el cual se reglamenta el funcionamiento de los comités locales para la organización de las playas"
N_REMAC = "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)"
N_ESPACIO = "Por el cual se reglamenta el manejo del espacio público en los planes de ordenamiento territorial"
N_LICENCIAS = (
    "Por el cual se reglamentan las disposiciones sobre licencias urbanísticas, reconocimiento de "
    "edificaciones y legalización de asentamientos humanos"
)
N_RECURSOS = "Por el cual se dicta el Código Nacional de Recursos Naturales Renovables y de Protección al Medio Ambiente"
N_TRANSPORTE = "Por el cual se reglamenta el servicio público de transporte marítimo"
N_UAC = (
    "Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- y las comisiones "
    "conjuntas, se establecen las reglas de procedimiento y criterios para reglamentar la "
    "restricción de ciertas actividades en"
)
N_TURISMO = "Por medio del cual se expide el Decreto Único Reglamentario del Sector Comercio, Industria y Turismo"
S_GIESEKEN = "AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros"
S_PROCURADURIA = "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS"
S_COVENAS = "CE 2da AP 2016 328 Ricardo Cabrales VS Mun Coveñas Playa Uso Publico"
S_FEPEP = "CE 2da NYR 2009 164 FEPEP VS DIMAR Playa Uso Urbanistico"
S_MERCEDES = "CE 2da NYR 1999 503 Inversiones Mercedes VS Dimar Concesiones Uso Playa"
S_CONSULTA = "CE Consulta 2005 168 MinDefensa Bienes De Uso Publico"
S_RADLEY = "CE 2da AP 2010 028 Radley Bent VS Dimar Daños Ambientales Embarcaciones"
S_CARRERO = "CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera"

JURIS = {
    S_GIESEKEN,
    S_PROCURADURIA,
    S_COVENAS,
    S_FEPEP,
    S_MERCEDES,
    S_CONSULTA,
    S_RADLEY,
    S_CARRERO,
}

FUENTES_POR_TEMA = {
    "entrar": [N_DIMAR, N_PLAYAS_SM, S_COVENAS, S_CONSULTA, N_ESPACIO, S_GIESEKEN],
    "pescar": [N_RECURSOS, N_DIMAR, N_UAC, N_PLAYAS_SM],
    "vender": [N_PLAYAS_SM, N_RODADERO, N_COMITES, N_ESPACIO],
    "hoteles": [N_DIMAR, S_MERCEDES, N_PLAYAS_SM, S_GIESEKEN, N_TURISMO],
    "lanchas": [N_REMAC, N_TRANSPORTE, S_RADLEY, N_DIMAR],
    "obras": [N_DIMAR, N_LICENCIAS, S_FEPEP, S_CARRERO, S_PROCURADURIA],
    "otros": [N_DIMAR, S_CONSULTA],
}

# ── Preguntas escritas a mano (inventadas, realistas) ────────────────────────
LIBRES = {
    "entrar": [
        "¿Me pueden cobrar la entrada a la playa del hotel?",
        "El conjunto residencial puso una reja y no deja pasar al mar, ¿es legal?",
        "¿La policía me puede sacar de la playa por la noche?",
        "¿Es obligatorio dejar un camino libre de acceso a la playa?",
        "¿Las playas son de uso público o pueden ser privadas?",
    ],
    "pescar": [
        "¿Necesito carné para pescar con chinchorro?",
        "¿Se puede pescar con red cerca de donde se bañan los turistas?",
        "¿Qué entidad da el permiso de pesca artesanal?",
        "Soy pescador, ¿me pueden prohibir sacar la lancha en la playa?",
    ],
    "vender": [
        "¿Qué carné necesita un vendedor ambulante en la playa?",
        "¿Me pueden decomisar la nevera si vendo sin permiso?",
        "¿Se pueden vender masajes en la playa?",
        "¿Cuántos kioscos se permiten en la playa?",
        "¿Dónde se pide el permiso para vender comida en la arena?",
    ],
    "hoteles": [
        "¿El hotel puede reservar sillas en la arena solo para sus huéspedes?",
        "¿Cuánto cuesta la concesión de un parqueadero frente a la playa?",
        "¿Un restaurante puede poner mesas sobre la arena?",
        "¿Un club de playa puede cobrar por usar los parasoles?",
    ],
    "lanchas": [
        "¿A qué distancia de la orilla pueden andar las motos de agua?",
        "¿Quién marca la zona de bañistas con boyas?",
        "¿Las lanchas pueden desembarcar turistas en cualquier parte de la playa?",
        "¿Es obligatorio que haya salvavidas en la playa?",
    ],
    "obras": [
        "¿Puedo arreglar el techo de mi kiosco sin permiso?",
        "¿Se puede construir un muro para frenar la erosión?",
        "¿Qué licencia necesito para remodelar una casa frente al mar?",
        "¿Qué son los terrenos de bajamar y quién los administra?",
        "¿Pueden tumbar una construcción que está sobre la playa?",
    ],
    "otros": [
        "¿Qué horario tiene el acuario?",
        "¿Cuál es la mejor playa para ir con niños?",
        "¿ATLAS sirve para poner una denuncia?",
    ],
}
# Preguntas que ATLAS no sabe responder bien y se repiten (brechas).
DIFICILES = [
    ("obras", "¿Puedo arreglar el techo de mi kiosco sin permiso?"),
    ("hoteles", "¿Cuánto cuesta la concesión de un parqueadero frente a la playa?"),
    ("vender", "¿Me pueden decomisar la nevera si vendo sin permiso?"),
    ("obras", "¿Se puede construir un muro para frenar la erosión?"),
    ("lanchas", "¿Es obligatorio que haya salvavidas en la playa?"),
    ("pescar", "¿Necesito carné para pescar con chinchorro?"),
]
FUERA = [
    "¿Qué horario tiene el museo del oro?",
    "¿Cuánto cuesta un tiquete a Bogotá?",
    "Recomiéndeme un restaurante en el centro",
    "¿Va a llover mañana en Santa Marta?",
]
ACLARAR = ["¿Y los permisos?", "¿Qué pasa con eso?", "Necesito saber de un permiso"]
SALUDOS = ["hola", "buenos días", "¿qué puede hacer usted?", "gracias"]
# "Lo que esperaba" según el tema de la pregunta (PQ-17): tiene que leerse
# como algo que esa persona pudo escribir.
ESPERABA_POR_TEMA = {
    "entrar": [
        "Si el hotel puede cerrarme el paso y a quién me quejo",
        "Que me dijera si es legal cobrar la entrada",
        "A qué entidad acudir para que abran el acceso",
    ],
    "pescar": [
        "Dónde se saca el permiso de pesca y cuánto cuesta",
        "Si puedo pescar con red cerca de los bañistas",
    ],
    "vender": [
        "Qué papeles necesito para vender sin que me quiten la mercancía",
        "En qué oficina de Santa Marta se pide el permiso",
        "Si la Policía puede decomisarme la nevera",
    ],
    "hoteles": [
        "El valor de la concesión o cómo se calcula",
        "Si el hotel puede reservar la arena solo para huéspedes",
        "Qué norma dice hasta dónde puede poner sillas el hotel",
    ],
    "lanchas": [
        "A qué distancia de la orilla pueden pasar las motos de agua",
        "Quién está obligado a poner salvavidas",
    ],
    "obras": [
        "Saber si la DIMAR me tiene que dar permiso para reparar",
        "Qué licencia necesito y quién la da",
        "Si pueden tumbar la construcción y qué puedo hacer",
    ],
}
ESPERABA_GENERAL = [
    "Una respuesta más corta, con el paso a paso",
    "El número de la norma exacta",
    "Que me dijera si es legal o no",
]


def _esperaba(rng: random.Random, tema: str) -> str:
    opciones = ESPERABA_POR_TEMA.get(tema, [])
    return rng.choice(opciones if opciones and rng.random() < 0.8 else ESPERABA_GENERAL)


COMENTARIOS_BUENOS = [
    "Clara y con la norma, gracias.",
    "Me sirvió para hablar con el hotel.",
    "Muy fácil de usar desde el celular.",
    "Me gustó que dijera a quién acudir.",
]
COMENTARIOS_MALOS = [
    "No entendí la respuesta, muy técnica.",
    "No me dijo qué hacer en mi caso.",
    "Esperaba algo sobre Taganga.",
    "La respuesta fue muy larga.",
]

NOMBRES = (
    "Laura Pérez, Pedro Ramírez, Ana Gómez, Carlos Rodríguez, María Fernanda Ruiz, Jorge Díaz, "
    "Sandra Ortiz, Luis Herrera, Diana Castro, Andrés Molina, Paola Vargas, Camilo Rojas, "
    "Natalia Suárez, Julián Mendoza, Carolina Ríos, Felipe Torres, Valentina Cruz, Óscar Navarro, "
    "Juliana Peña, Ricardo Salazar, Alejandra Ramos, Fernando Guerrero, Mónica Arias, Héctor Mejía, "
    "Lucía Cárdenas, Esteban Pardo, Gloria Romero, Iván Correa, Patricia León, Sergio Acosta, "
    "Marcela Campo, Daniel Vega, Rosa Barrios, Manuel Fuentes, Adriana Silva, Tomás Zúñiga, "
    "Elena Pacheco, Raúl Medina, Claudia Osorio, Mauricio Quintero"
).split(", ")


def _fuentes(rng: random.Random, tema: str) -> list[dict]:
    titulos = rng.sample(
        FUENTES_POR_TEMA[tema], k=min(len(FUENTES_POR_TEMA[tema]), rng.choice((1, 2, 2, 3)))
    )
    return [
        {
            "source": f"{'jurisprudencia' if t in JURIS else 'normativa'}/{t[:60]}.md",
            "title": t,
            "doc_type": "jurisprudencia" if t in JURIS else "normativa",
            "metadata": {},
            "fragments": [
                {"index": i + 1, "content": "Fragmento de demostración.", "metadata": {}}
            ],
        }
        for i, t in enumerate(titulos)
    ]


def _respuesta_con_fuente(fuentes: list[dict]) -> str:
    citas = " ".join(f"[doc{i + 1}]" for i in range(len(fuentes)))
    return (
        "**Situación:** respuesta de demostración.\n\n"
        f"Según las normas citadas {citas}, esta es una respuesta inventada para probar el panel."
    )


def _fecha(rng: random.Random, ahora: datetime, dias: int) -> datetime:
    # Más uso reciente (la demo "crece") y más de lunes a viernes, de 7 a 21 h Colombia.
    while True:
        atras = int(dias * (1 - rng.random() ** 0.75))
        dia = (ahora.astimezone(pm.HORA_COLOMBIA) - timedelta(days=atras)).date()
        if dia.weekday() >= 5 and rng.random() < 0.45:
            continue
        hora = datetime(
            dia.year,
            dia.month,
            dia.day,
            rng.randint(7, 20),
            rng.randint(0, 59),
            rng.randint(0, 59),
            tzinfo=pm.HORA_COLOMBIA,
        )
        if hora.astimezone(UTC) < ahora:
            return hora.astimezone(UTC)


def _pregunta(rng: random.Random) -> tuple[str, str]:
    """``(tipo, texto)``: tipo es el tema, o fuera/aclarar/saludo."""
    r = rng.random()
    if r < 0.06:
        return "fuera", rng.choice(FUERA)
    if r < 0.08:
        return "aclarar", rng.choice(ACLARAR)
    if r < 0.12:
        return "saludo", rng.choice(SALUDOS)
    if r < 0.20:
        return rng.choice(DIFICILES)
    tema = rng.choices(
        ["entrar", "vender", "hoteles", "obras", "pescar", "lanchas", "otros"],
        weights=[28, 20, 17, 12, 9, 7, 3],
    )[0]
    if tema != "otros" and rng.random() < 0.55:
        base = rng.choice(pm.TEMAS_POR_ID[tema].preguntas)  # botón del flujo guiado
        if rng.random() < 0.5:
            base = f"{base} Es en {rng.choice(pm.PLAYAS)}, en Santa Marta."
        return tema, base
    texto = rng.choice(LIBRES[tema])
    if rng.random() < 0.25:
        texto = texto.rstrip("?") + f" en {rng.choice(pm.PLAYAS)}?"
    return tema, texto


async def sembrar(
    db: Path, n: int, semilla: int, reset: bool, dias: int, casos_limite: bool = False
) -> dict[str, int]:
    if db.exists():
        if not reset:
            raise SystemExit(f"{db} ya existe. Use --reset para borrarlo y crearlo de nuevo.")
        db.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(semilla)
    ahora = datetime.now(UTC).replace(microsecond=0)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def uid() -> str:
        return str(uuid.UUID(int=rng.getrandbits(128)))

    conteo = {"usuarios": 0, "preguntas": 0, "calificaciones": 0, "conversaciones": 0}
    correos: dict[str, str] = {}
    async with factory() as s:
        hash_demo = hash_password(ADMIN_PASSWORD)
        s.add(
            User(
                id=uid(),
                email=ADMIN_EMAIL,
                password_hash=hash_demo,
                display_name="Administración ATLAS",
                role="admin",
                created_at=ahora - timedelta(days=dias + 30),
            )
        )
        s.add(
            User(
                id=uid(),
                email=USUARIO_EMAIL,
                password_hash=hash_demo,
                display_name="Persona de prueba",
                role="user",
                created_at=ahora - timedelta(days=dias + 30),
            )
        )
        s.add(
            User(
                id=uid(),
                email=DEMO_EMAIL,
                password_hash="!",
                display_name="Semilla de demostración",
                role="user",
                created_at=ahora,
            )
        )
        personas: list[tuple[str, float]] = []
        # 80 nombres distintos: los 40 de la lista y 40 cruzando nombre y apellido.
        cruzados = [
            f"{n.rsplit(' ', 1)[0]} {NOMBRES[(i + 7) % len(NOMBRES)].rsplit(' ', 1)[1]}"
            for i, n in enumerate(NOMBRES)
        ]
        for i, nombre in enumerate(NOMBRES + cruzados):
            correo = pm.normalizar(nombre).replace(" ", ".") + f"{i}@correo.example"
            creado = ahora - timedelta(days=rng.randint(0, dias + 20))
            usuario = User(
                id=uid(),
                email=correo,
                password_hash="!",
                display_name=nombre if rng.random() < 0.9 else None,
                role="user",
                created_at=creado,
            )
            s.add(usuario)
            # Peso de actividad: pocos preguntan mucho, la mayoría poco.
            personas.append((usuario.id, rng.paretovariate(1.6)))
            correos[usuario.id] = correo
        conteo["usuarios"] = len(personas)
        ids, pesos = zip(*personas, strict=True)

        for _ in range(n):
            tipo, texto = _pregunta(rng)
            usuario = rng.choices(ids, weights=pesos)[0]
            cuando = _fecha(rng, ahora, dias)
            conv = Conversation(
                id=uid(),
                user_id=usuario,
                thread_id=uid(),
                title=texto[:60],
                created_at=cuando,
                updated_at=cuando,
                message_count=2,
            )
            s.add(conv)
            s.add(
                Message(
                    id=uid(), conversation_id=conv.id, role="user", text=texto, created_at=cuando
                )
            )
            sources: list[dict] = []
            if tipo == "fuera":
                respuesta = agent._OUT_OF_SCOPE_RESPONSE
            elif tipo == "aclarar":
                respuesta = agent._CLARIFICATION_RESPONSE
            elif tipo == "saludo":
                respuesta = agent._CONVERSATION_RESPONSE
            else:
                dificil = (tipo, texto) in DIFICILES
                p_brecha = 0.7 if dificil else {"obras": 0.14, "otros": 0.3}.get(tipo, 0.05)
                if rng.random() < p_brecha:
                    respuesta = (
                        agent._NO_EVIDENCE_RESPONSE
                        if rng.random() < 0.8
                        else agent._INVALID_CITATIONS_RESPONSE
                    )
                else:
                    sources = _fuentes(rng, tipo)
                    respuesta = _respuesta_con_fuente(sources)
            respuesta_id = uid()
            s.add(
                Message(
                    id=respuesta_id,
                    conversation_id=conv.id,
                    role="assistant",
                    text=respuesta,
                    sources=sources or None,
                    created_at=cuando + timedelta(seconds=rng.randint(6, 40)),
                )
            )
            conteo["preguntas"] += 1

            if tipo in ("saludo",) or rng.random() > 0.38:
                continue
            p_util = 0.82 if sources else 0.0  # sin norma nunca "le sirvió"
            if tipo in ("obras", "otros") and sources:
                p_util = 0.6
            util = rng.random() < p_util
            if rng.random() < 0.8:  # "¿Le sirvió?" del flujo guiado
                ratings = (
                    {"pertinence": 5, "accuracy": 5} if util else {"pertinence": 1, "accuracy": 1}
                )
            else:  # estrellas del chat del equipo
                a, b = (
                    (rng.randint(4, 5), rng.randint(3, 5))
                    if util
                    else (rng.randint(1, 3), rng.randint(1, 2))
                )
                ratings = {"pertinence": a, "accuracy": b}
            esperaba = None if util or rng.random() < 0.35 else _esperaba(rng, tipo)
            s.add(
                MessageFeedback(
                    id=uid(),
                    user_id=usuario,
                    user_email=correos.get(usuario, ""),
                    conversation_id=conv.id,
                    message_id=respuesta_id,
                    ratings=ratings,
                    expected_answer=esperaba,
                    created_at=cuando + timedelta(minutes=2),
                )
            )
            conteo["calificaciones"] += 1
            # Encuesta de la conversación (tono, largo, facilidad, general).
            if rng.random() < 0.4:
                base = rng.randint(4, 5) if util else rng.randint(1, 3)
                notas = {
                    k: max(1, min(5, base + rng.choice((-1, 0, 0, 1))))
                    for k in ("tone", "length", "usability")
                }
                s.add(
                    Feedback(
                        id=uid(),
                        user_id=usuario,
                        user_email=correos.get(usuario, ""),
                        ratings={**notas, "overall": base},
                        comment=rng.choice(COMENTARIOS_BUENOS if util else COMENTARIOS_MALOS)
                        if rng.random() < 0.6
                        else None,
                        conversation_id=conv.id,
                        conversation_title=conv.title,
                        created_at=cuando + timedelta(minutes=3),
                    )
                )
                conteo["conversaciones"] += 1
        # Casos límite para QA (PQ-14), solo con --casos-limite (PQ-16): texto
        # muy largo, pregunta sin respuesta guardada, HTML y fórmulas que deben
        # verse como texto plano y salir escapados en el CSV. Van fechados al
        # principio de los datos para que la vista por defecto arranque limpia.
        largo = (
            "Tengo un kiosco en la playa desde hace muchos años y quiero saber qué tengo que hacer. "
            * 24
        ).strip()
        especiales = [
            (largo, _respuesta_con_fuente(_fuentes(rng, "obras")), True),
            ("¿Qué pasa si me ponen un comparendo en la playa?", None, False),
            (
                "<b>x</b><script>alert(1)</script> ¿Se puede vender en la playa?",
                agent._NO_EVIDENCE_RESPONSE,
                False,
            ),
            ("@SUM(1+1) ¿Un hotel puede cerrar la playa?", agent._NO_EVIDENCE_RESPONSE, False),
        ]
        if not casos_limite:
            especiales = []
        inicio_casos = ahora - timedelta(days=dias - 5)
        for i, (texto, respuesta, con_fuente) in enumerate(especiales):
            cuando = inicio_casos + timedelta(hours=3 + i)
            conv = Conversation(
                id=uid(),
                user_id=ids[i],
                thread_id=uid(),
                title=texto[:60],
                created_at=cuando,
                updated_at=cuando,
                message_count=2 if respuesta else 1,
            )
            s.add(conv)
            s.add(
                Message(
                    id=uid(), conversation_id=conv.id, role="user", text=texto, created_at=cuando
                )
            )
            if respuesta:
                fuentes = _fuentes(rng, "obras") if con_fuente else None
                id_respuesta = uid()
                s.add(
                    Message(
                        id=id_respuesta,
                        conversation_id=conv.id,
                        role="assistant",
                        text=respuesta,
                        sources=fuentes,
                        created_at=cuando + timedelta(seconds=20),
                    )
                )
                if texto.startswith("@SUM"):
                    # "Lo que esperaba" con HTML y fórmula (PQ-06).
                    s.add(
                        MessageFeedback(
                            id=uid(),
                            user_id=ids[i],
                            user_email=correos.get(ids[i], ""),
                            conversation_id=conv.id,
                            message_id=id_respuesta,
                            ratings={"pertinence": 1, "accuracy": 1},
                            expected_answer='<img src=x onerror=alert(1)> =HYPERLINK("x","clic")',
                            created_at=cuando + timedelta(minutes=2),
                        )
                    )
            conteo["preguntas"] += 1
        await s.commit()
    await engine.dispose()
    return conteo


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--db", type=Path, default=Path("data/panel-demo.db"), help="Archivo SQLite a crear"
    )
    p.add_argument("--preguntas", type=int, default=480)
    p.add_argument("--dias", type=int, default=120, help="Días hacia atrás que cubren los datos")
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--reset", action="store_true", help="Borra el archivo si ya existe")
    p.add_argument(
        "--casos-limite",
        action="store_true",
        help="Agrega preguntas de prueba para QA (HTML, fórmulas, texto largo)",
    )
    a = p.parse_args()
    if a.db.suffix not in (".db", ".sqlite", ".sqlite3"):
        raise SystemExit("--db debe ser un archivo SQLite (.db, .sqlite o .sqlite3)")
    conteo = asyncio.run(sembrar(a.db, a.preguntas, a.semilla, a.reset, a.dias, a.casos_limite))
    print(
        f"Semilla lista en {a.db}: {conteo['usuarios']} personas, {conteo['preguntas']} preguntas, {conteo['calificaciones']} calificaciones por respuesta, {conteo['conversaciones']} de conversación."
    )
    print(
        f"Administrador de la demo: {ADMIN_EMAIL} / {ADMIN_PASSWORD}  (sin rol admin: {USUARIO_EMAIL}, misma clave)"
    )
    print(f"Backend: DATABASE_URL=sqlite+aiosqlite:///./{a.db} make app")


if __name__ == "__main__":
    main()
