"""Clasificaciones del panel de administración, en código y sin IA.

Todo lo que el panel "deduce" de una pregunta o de una respuesta sale de aquí:

- el **tema** de una pregunta: primero por coincidencia exacta con las
  preguntas fijas del flujo guiado (copiadas de
  ``rag/frontend/lib/guia/temas.ts``; ``tests/unit/test_panel_metricas.py``
  verifica que sigan iguales), después por palabras clave y si no, "otros";
- la **playa**: el sufijo "Es en <playa>, en Santa Marta." que agrega el flujo
  guiado (``preguntaConPlaya``) o el nombre de la playa en el texto;
- el **resultado** de una respuesta: con fuente, o alguna de las respuestas
  fijas del agente (``rag/core/agent.py``), reconocidas por su texto inicial;
- las **normas citadas**: los títulos de ``messages.sources``.

No hay costo por uso: son reglas sobre texto ya guardado.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

# Colombia no tiene horario de verano: UTC−5 fijo, sin depender de tzdata.
HORA_COLOMBIA = timezone(timedelta(hours=-5), "COT")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos y con espacios simples."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-z0-9ñ ]+", " ", sin_tildes.lower())
    return re.sub(r"\s+", " ", limpio).strip()


def a_utc(dt: datetime) -> datetime:
    """SQLite devuelve fechas sin zona aunque la columna sea ``timezone=True``:
    se asumen UTC, que es como se guardan (``models._now``)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


# ── Temas ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tema:
    id: str
    titulo: str
    corto: str
    preguntas: tuple[str, ...]
    palabras: tuple[str, ...]


# Las `preguntas` son copia literal de `temas.ts` (campo `pregunta`). Las
# `palabras` se comparan contra el texto normalizado (sin tildes), como
# palabras o frases completas.
TEMAS: tuple[Tema, ...] = (
    Tema(
        id="entrar",
        titulo="Entrar o caminar por la playa",
        corto="Entrar",
        preguntas=(
            "Un hotel o un negocio no me deja pasar a la playa. ¿Puede impedirme el paso a la playa?",
            "Me quieren cobrar por entrar a la playa. ¿Pueden cobrar por el acceso a la playa?",
            "Me piden que me vaya de la playa. ¿En qué casos me pueden pedir que salga de una playa?",
        ),
        palabras=(
            "acceso",
            "entrar",
            "entrada",
            "pasar",
            "paso",
            "caminar",
            "cobrar por entrar",
            "cobran la entrada",
            "salir de la playa",
            "me sacan",
            "me echan",
            "servidumbre",
            "libre acceso",
            "uso publico",
            "bien de uso publico",
        ),
    ),
    Tema(
        id="pescar",
        titulo="Pescar",
        corto="Pescar",
        preguntas=(
            "¿Puedo pescar en la playa o en el mar frente a un hotel?",
            "¿Qué permiso necesito para pescar en el mar o en la playa?",
        ),
        palabras=(
            "pescar",
            "pesca",
            "pescador",
            "pescadores",
            "red",
            "redes",
            "chinchorro",
            "aunap",
        ),
    ),
    Tema(
        id="vender",
        titulo="Vender en la playa",
        corto="Vender",
        preguntas=(
            "¿Qué permiso necesito para vender en la playa?",
            "¿En qué parte de la playa se puede vender?",
        ),
        palabras=(
            "vender",
            "venta",
            "vendedor",
            "vendedores",
            "ambulante",
            "ambulantes",
            "carne",
            "kiosco",
            "kioscos",
            "puesto",
            "comida",
            "artesanias",
            "masajes",
        ),
    ),
    Tema(
        id="hoteles",
        titulo="Hoteles y negocios frente al mar",
        corto="Hoteles",
        preguntas=(
            "¿Un hotel puede poner sillas y carpas en la arena de la playa?",
            "¿Un hotel puede cerrar o encerrar una parte de la playa?",
        ),
        palabras=(
            "hotel",
            "hoteles",
            "restaurante",
            "negocio",
            "negocios",
            "sillas",
            "carpas",
            "parasoles",
            "concesion",
            "concesiones",
            "encerrar",
            "cerrar la playa",
            "club de playa",
        ),
    ),
    Tema(
        id="lanchas",
        titulo="Lanchas, motos de agua y bañistas",
        corto="Lanchas",
        preguntas=(
            "¿Por dónde pueden andar las lanchas y las motos de agua cerca de la playa?",
            "¿Hasta dónde se pueden bañar las personas en la playa? ¿Cómo se separa la zona de bañistas?",
        ),
        palabras=(
            "lancha",
            "lanchas",
            "moto de agua",
            "motos de agua",
            "jet ski",
            "embarcacion",
            "embarcaciones",
            "bote",
            "botes",
            "banistas",
            "banarse",
            "banar",
            "nadar",
            "boya",
            "boyas",
            "salvavidas",
            "canal de acceso",
        ),
    ),
    Tema(
        id="obras",
        titulo="Construcciones cerca del mar",
        corto="Construcciones",
        preguntas=("¿Se puede construir sobre la arena de la playa?",),
        palabras=(
            "construir",
            "construccion",
            "construcciones",
            "obra",
            "obras",
            "edificar",
            "edificio",
            "muro",
            "espolon",
            "relleno",
            "casa",
            "techo",
            "reparar",
            "arreglar",
            "remodelar",
            "licencia",
            "bajamar",
            "terrenos de bajamar",
        ),
    ),
)
TEMA_OTROS = "otros"
TITULO_OTROS = "Otros temas"
TEMAS_POR_ID: dict[str, Tema] = {t.id: t for t in TEMAS}

PLAYAS: tuple[str, ...] = (
    "Taganga",
    "Bahía de Santa Marta",
    "Playa Blanca",
    "El Rodadero",
    "Bello Horizonte",
    "Pozos Colorados",
)
SIN_PLAYA = "Sin playa"

_RE_SUFIJO_PLAYA = re.compile(r"\s*Es en (.+?), en Santa Marta\.\s*$")
_EXACTAS: dict[str, str] = {normalizar(p): t.id for t in TEMAS for p in t.preguntas}
_PATRONES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (t.id, re.compile(r"\b(?:" + "|".join(re.escape(p) for p in t.palabras) + r")\b"))
    for t in TEMAS
)
# "Bahía de Santa Marta" antes que cualquier mención suelta de "Santa Marta".
_PLAYAS_NORM = tuple((p, normalizar(p)) for p in PLAYAS)


def separar_playa(texto: str) -> tuple[str, str | None]:
    """Quita el sufijo del flujo guiado y devuelve ``(pregunta, playa)``."""
    m = _RE_SUFIJO_PLAYA.search(texto)
    if not m:
        return texto, None
    return texto[: m.start()], m.group(1)


def clasificar_tema(texto: str) -> str:
    """Id del tema (``entrar``, ``pescar``…) o ``otros``.

    Exacta primero (preguntas de los botones); si no, el tema con más
    palabras clave encontradas; en empate gana el orden de ``TEMAS``.
    """
    base, _ = separar_playa(texto)
    norm = normalizar(base)
    if norm in _EXACTAS:
        return _EXACTAS[norm]
    mejor, mejor_n = TEMA_OTROS, 0
    for tema_id, patron in _PATRONES:
        n = len(patron.findall(norm))
        if n > mejor_n:
            mejor, mejor_n = tema_id, n
    return mejor


def detectar_playa(texto: str) -> str:
    _, playa = separar_playa(texto)
    if playa:
        return playa if playa in PLAYAS else SIN_PLAYA
    norm = normalizar(texto)
    for nombre, nombre_norm in _PLAYAS_NORM:
        if re.search(r"\b" + re.escape(nombre_norm) + r"\b", norm):
            return nombre
    return SIN_PLAYA


def titulo_tema(tema_id: str) -> str:
    tema = TEMAS_POR_ID.get(tema_id)
    return tema.titulo if tema else TITULO_OTROS


def corto_tema(tema_id: str) -> str:
    tema = TEMAS_POR_ID.get(tema_id)
    return tema.corto if tema else TITULO_OTROS


# ── Resultado de cada respuesta ──────────────────────────────────────────────

CON_FUENTE = "con_fuente"
SIN_EVIDENCIA = "sin_evidencia"
SIN_CITA_VALIDA = "sin_cita_valida"
SIN_FUENTE_OTRO = "sin_fuente_otro"
FUERA_DE_TEMA = "fuera_de_tema"
PIDE_ACLARAR = "pide_aclarar"
SALUDO = "saludo"
SIN_RESPUESTA = "sin_respuesta"  # la pregunta no tiene respuesta guardada

# Resultados que cuentan como "sin respuesta segura" (brecha de contenido).
BRECHAS = frozenset({SIN_EVIDENCIA, SIN_CITA_VALIDA, SIN_FUENTE_OTRO})

# Inicio de las respuestas fijas de `rag/core/agent.py` (normalizado). Si
# cambian allá, `test_panel_metricas.py` lo detecta.
_FIJAS: tuple[tuple[str, str], ...] = (
    (SIN_EVIDENCIA, normalizar("**Situación:** evidencia insuficiente.")),
    (
        SIN_CITA_VALIDA,
        normalizar("**Situación:** no fue posible producir una respuesta verificable."),
    ),
    (FUERA_DE_TEMA, normalizar("La consulta está fuera del ámbito jurídico y normativo")),
    (PIDE_ACLARAR, normalizar("La consulta podría estar dentro del ámbito, pero necesito que")),
    (SALUDO, normalizar("Puedo responder consultas sobre jurisprudencia y normatividad")),
)


def clasificar_respuesta(texto: str | None, sources: list | None) -> str:
    if texto is None:
        return SIN_RESPUESTA
    norm = normalizar(texto[:400])
    for resultado, inicio in _FIJAS:
        if norm.startswith(inicio):
            return resultado
    return CON_FUENTE if sources else SIN_FUENTE_OTRO


# ── Normas citadas ───────────────────────────────────────────────────────────

_RE_EXTENSION = re.compile(r"\.(md|pdf|txt|json|jsonl)$", re.IGNORECASE)


_RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


def _legible(nombre: str) -> str:
    """``decreto-2324-de-1984`` → ``Decreto 2324 de 1984`` (títulos que quedaron
    como nombre de archivo en el corpus). Los demás se dejan igual."""
    if _RE_SLUG.match(nombre):
        texto = nombre.replace("-", " ")
        return texto[:1].upper() + texto[1:]
    return nombre


def normas_citadas(sources: list | None) -> list[tuple[str, str | None]]:
    """``[(nombre, doc_type)]`` sin repetidos, en el orden en que se citan."""
    vistas: dict[str, str | None] = {}
    for grupo in sources or []:
        if not isinstance(grupo, dict):
            continue
        nombre = _legible((grupo.get("title") or "").strip())
        if not nombre:
            # Sin título: nombre del archivo, sin carpeta ni extensión.
            archivo = (grupo.get("source") or "").strip().rsplit("/", 1)[-1]
            nombre = _legible(_RE_EXTENSION.sub("", archivo))
        if nombre and nombre not in vistas:
            vistas[nombre] = grupo.get("doc_type")
    return list(vistas.items())


# ── Calificaciones ──────────────────────────────────────────────

UTIL = "util"
NO_UTIL = "no_util"
NEUTRA = "neutra"


def calificacion(ratings: dict | None) -> str | None:
    """Promedio de pertinencia y precisión: ≥ 4 le sirvió, ≤ 2 no le sirvió.

    El flujo guiado guarda "Sí" como 5/5 y "No" como 1/1; en el chat del
    equipo son estrellas de 1 a 5 (3 queda como neutra).
    """
    if not ratings:
        return None
    valores = [
        v for v in (ratings.get("pertinence"), ratings.get("accuracy")) if isinstance(v, int)
    ]
    if not valores:
        return None
    promedio = sum(valores) / len(valores)
    if promedio >= 4:
        return UTIL
    if promedio <= 2:
        return NO_UTIL
    return NEUTRA


# ── Periodo ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Periodo:
    inicio: datetime | None  # UTC; None = desde el principio
    fin: datetime  # UTC (ahora)
    anterior_inicio: datetime | None
    dias: int  # 0 = todo


def calcular_periodo(dias: int, ahora: datetime | None = None) -> Periodo:
    """Últimos ``dias`` días en hora de Colombia, **incluyendo hoy**: desde las
    00:00 de hace ``dias − 1`` días hasta ahora. El periodo anterior es el
    bloque de la misma duración justo antes. ``dias = 0`` es todo."""
    ahora = a_utc(ahora or datetime.now(UTC))
    if dias <= 0:
        return Periodo(None, ahora, None, 0)
    hoy_col = ahora.astimezone(HORA_COLOMBIA).replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = (hoy_col - timedelta(days=dias - 1)).astimezone(UTC)
    return Periodo(inicio, ahora, inicio - timedelta(days=dias), dias)


def clave_dia(dt: datetime) -> str:
    return a_utc(dt).astimezone(HORA_COLOMBIA).date().isoformat()


def clave_semana(dt: datetime) -> str:
    """Lunes (hora de Colombia) de la semana de ``dt``."""
    d = a_utc(dt).astimezone(HORA_COLOMBIA).date()
    return (d - timedelta(days=d.weekday())).isoformat()
