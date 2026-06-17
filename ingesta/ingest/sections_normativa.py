# src/ingest/sections_normativa.py
"""
Seccionado de NORMATIVA (decretos, reglamentos) por artículos.

A diferencia de la jurisprudencia (ver ``ingest/sections.py``), la estructura
real de la normativa colombiana (``TÍTULO``, ``CAPÍTULO``, ``Artículo N``) vive
en TEXTO PLANO, no en headings Markdown. Los ``.md`` producidos por el OCR sólo
traen headings ``## Página N`` que parten los artículos por la mitad.

``split_by_articles`` segmenta el documento en una unidad (``Document``) por
artículo, arrastrando como metadata el ``TÍTULO``/``CAPÍTULO`` vigente. El texto
previo al primer artículo (encabezado del decreto, ``DECRETA:``) va a una unidad
inicial con ``section_name == "Preámbulo"``.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document

from .sections import _strip_accents  # reutilizamos el helper (no lo duplicamos)

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Marcadores de página del OCR: líneas tipo "## Página 12".
_PAGINA_RE = re.compile(r"^##\s*P[aá]gina\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)

# Inicio de artículo, anclado a comienzo de línea y tolerante al ruido OCR.
# Acepta "Artículo", "ARTÍCULO", "Articulo", numeración simple o punteada
# (1, 2, 5.1.1, 5.2.5 .12 — con espacios espurios entre dígitos/puntos),
# seguida de un separador ":", "°", ".", "-" o espacio.
_ARTICULO_RE = re.compile(
    r"""
    ^[ \t]*                          # posibles espacios iniciales
    art[ií]culo                      # "Artículo" / "Articulo" / "ARTICULO"
    [ \t]+
    (?P<num>                         # número: simple o punteado (5.1.1, 5.2.5 .12)
        \d+                          #   primer grupo de dígitos
        (?:[ \t]*\.[ \t]*\d+)*       #   grupos punteados sucesivos (espacios OCR ok)
    )
    [ \t]*
    (?P<sep>[:°.\-]|(?=[ \t]))        # separador explícito o espacio (lookahead)
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# Jerarquía: líneas tipo "TITULO I", "TÍTULO 1 A", "CAPITULO II ...".
# Se exige que la línea EMPIECE por la palabra clave (en mayúsculas o no).
_TITULO_RE = re.compile(
    r"^[ \t]*(?P<kw>t[ií]tulo)\b[ \t]*(?P<rest>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_CAPITULO_RE = re.compile(
    r"^[ \t]*(?P<kw>cap[ií]tulo)\b[ \t]*(?P<rest>.*)$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_number(raw: str) -> str:
    """Normaliza el identificador del artículo: quita espacios espurios.

    "5.2.5 .12" -> "5.2.5.12"; "1 " -> "1".
    """
    cleaned = re.sub(r"\s+", "", raw)
    cleaned = cleaned.strip(".-")
    return cleaned


def _looks_like_heading(line: str) -> str | None:
    """Devuelve la jerarquía ('TITULO ...'/'CAPITULO ...') normalizada si la
    línea es un encabezado de TÍTULO o CAPÍTULO; si no, None.

    Aceptamos la línea como heading sólo si su parte de "texto" (sin la palabra
    clave) es corta o está en mayúsculas, evitando capturar prosa que mencione
    "título" o "capítulo" en mitad de un párrafo.
    """
    for regex in (_TITULO_RE, _CAPITULO_RE):
        m = regex.match(line)
        if not m:
            continue
        rest = m.group("rest").strip()
        kw = m.group("kw").strip()
        # Heurística anti-falsos-positivos. Un encabezado real es de la forma
        # "TITULO I" / "TÍTULO 1 A" / "CAPITULO II ...": la palabra clave va en
        # mayúsculas y va seguida de un numeral (romano o arábigo). Exigir el
        # numeral evita capturar prosa tipo "Título 10 a la Parte 3 del REMAC".
        is_upper_kw = kw.upper() == kw
        starts_with_numeral = bool(
            re.match(r"^(?:[ivxlcdm]+|\d+)\b", _strip_accents(rest), re.IGNORECASE)
        )
        if is_upper_kw and starts_with_numeral:
            label = f"{kw} {rest}".strip()
            return re.sub(r"\s+", " ", label)
    return None


def _extract_epigraphe(body: str, num: str, sep: str) -> str:
    """Extrae el epígrafe del artículo: el texto que sigue a "Artículo N:" hasta
    el primer punto, si parece un epígrafe corto (titulillo).

    Ej: "Artículo 1: Nombre y naturaleza. La Dirección..." -> "Nombre y naturaleza".
    Devuelve "" si no se detecta un epígrafe razonable.
    """
    # body empieza en "Artículo". Saltamos hasta después del separador.
    m = re.match(
        r"^[ \t]*art[ií]culo[ \t]+\d+(?:[ \t]*\.[ \t]*\d+)*[ \t]*[:°.\-]?[ \t]*",
        body,
        re.IGNORECASE,
    )
    after = body[m.end() :] if m else body
    # Primera "oración" hasta el primer punto.
    head = after.split(".", 1)[0].strip()
    head = re.sub(r"\s+", " ", head)
    # Un epígrafe es corto y no termina en dos puntos ni es prosa larga.
    if head and len(head) <= 80 and "\n" not in head:
        return head
    return ""


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


def split_by_articles(doc: Document) -> list[Document]:
    """Parte un ``Document`` de normativa en una unidad por artículo.

    Algoritmo
    ---------
    1. Elimina los headings ``## Página N`` del texto.
    2. Segmenta por inicio de artículo (regex tolerante a OCR).
    3. Rastrea el ``TÍTULO``/``CAPÍTULO`` vigente y lo arrastra como metadata.
    4. El texto previo al primer artículo va a una unidad ``"Preámbulo"``.
    5. Cada ``Document`` hereda la metadata base y añade: ``doc_type``,
       ``articulo``, ``articulo_titulo``, ``titulo``, ``capitulo``,
       ``section_index`` (1-based), ``section_name``.
    """
    base_meta: dict[str, Any] = dict(doc.metadata)

    # 1) Pre-limpieza: quitar marcadores "## Página N".
    text = _PAGINA_RE.sub("", doc.page_content)

    # 2) Localizar los inicios de artículo.
    matches = list(_ARTICULO_RE.finditer(text))

    result: list[Document] = []
    section_index = 1

    def _make_meta(
        *,
        articulo: str | None,
        articulo_titulo: str,
        titulo: str,
        capitulo: str,
        section_name: str,
        idx: int,
    ) -> dict[str, Any]:
        return {
            **base_meta,
            "doc_type": "normativa",
            "articulo": articulo,
            "articulo_titulo": articulo_titulo,
            "titulo": titulo,
            "capitulo": capitulo,
            "section_index": idx,
            "section_name": section_name,
        }

    # Jerarquía vigente al recorrer el texto.
    def _hierarchy_at(pos: int) -> tuple[str, str]:
        """TÍTULO/CAPÍTULO vigentes justo antes de la posición *pos*."""
        titulo = ""
        capitulo = ""
        for line_match in re.finditer(r"^.*$", text[:pos], re.MULTILINE):
            label = _looks_like_heading(line_match.group(0))
            if label is None:
                continue
            if label.lower().startswith(("titulo", "título")) or _strip_accents(
                label
            ).lower().startswith("titulo"):
                titulo = label
                capitulo = ""  # un nuevo título reinicia el capítulo
            else:
                capitulo = label
        return titulo, capitulo

    # 4) Preámbulo: texto antes del primer artículo.
    preamble_end = matches[0].start() if matches else len(text)
    preamble = text[:preamble_end].strip()
    if preamble:
        result.append(
            Document(
                page_content=preamble,
                metadata=_make_meta(
                    articulo=None,
                    articulo_titulo="",
                    titulo="",
                    capitulo="",
                    section_name="Preámbulo",
                    idx=section_index,
                ),
            )
        )
        section_index += 1

    # 3) Una unidad por artículo.
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        num = _clean_number(m.group("num"))
        sep = m.group("sep")
        epigraphe = _extract_epigraphe(body, num, sep)
        titulo, capitulo = _hierarchy_at(start)

        section_name = epigraphe if epigraphe else f"Artículo {num}"

        result.append(
            Document(
                page_content=body,
                metadata=_make_meta(
                    articulo=num,
                    articulo_titulo=epigraphe,
                    titulo=titulo,
                    capitulo=capitulo,
                    section_name=section_name,
                    idx=section_index,
                ),
            )
        )
        section_index += 1

    return result
