# src/ingest/sections_normativa.py
"""
Seccionado de NORMATIVA (decretos, reglamentos) por artículos.

Reconoce rótulos de artículos en texto plano y formato ATX/negrita acotado,
con identificadores simples, punteados y sufijos de una letra ASCII. Los
marcadores ``## Página N`` se retiran sin limpiar el resto del contenido.

``split_by_articles`` segmenta el documento en una unidad (``Document``) por
encabezado admitido, arrastrando como metadata el ``TÍTULO``/``CAPÍTULO`` vigente.
Una zona de considerandos anterior al primer candidato y con un único marcador
de disposición puede reintegrarse al preámbulo; los extractos y marcadores
ambiguos conservan el fallback por encabezados. Las remisiones léxicas
explícitas dentro del articulado permanecen en su contenedor.

Los epígrafes son una heurística estructural, no una identidad jurídica
certificada. No distingue la atribución de anexos ni disposiciones insertadas;
esos textos se conservan sin inferir una norma o artículo padre.
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

# Rótulo de artículo al inicio de línea: ATX de 1–6 niveles y negrita
# opcionales, componentes numéricos con un sufijo ASCII y ordinales º/°.
# El punto seguido de otro componente no puede aceptarse como separador
# retrocediendo a un prefijo del identificador.
_ARTICULO_RE = re.compile(
    r"""
    ^[ \t]*(?:\#{1,6}[ \t]+)?
    (?P<bold>\*\*)?
    art[ií]culo
    [ \t]+
    (?P<num>
        \d+(?-i:[A-Za-z])?
        (?:[ \t]*\.[ \t]*\d+(?-i:[A-Za-z])?)*
    )
    (?![ \t]*\.[ \t]*\d)
    [ \t]*(?P<ordinal>[º°])?
    [ \t]*
    (?P<sep>[.:](?:[ \t]*-)?|-)?
    (?(bold)[ \t]*\*\*)
    (?:(?<=[º°.:*\-])|(?=[ \t]|\n|$))
    [ \t]*
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# Jerarquía: líneas tipo "TITULO I", "TÍTULO 1 A", "CAPITULO II ...".
# La admisión exige después palabra clave en mayúsculas y numeral.
_TITULO_RE = re.compile(
    r"^[ \t]*(?P<kw>t[ií]tulo)\b[ \t]*(?P<rest>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_CAPITULO_RE = re.compile(
    r"^[ \t]*(?P<kw>cap[ií]tulo)\b[ \t]*(?P<rest>.*)$",
    re.IGNORECASE | re.MULTILINE,
)

_DISPOSICION_RE = re.compile(r"(?:DECRETA|RESUELVE)[ \t]*[:.]?", re.IGNORECASE)
_CONSIDERANDO_RE = re.compile(r"CONSIDERANDOS?[ \t]*:?", re.IGNORECASE)
# Remisiones sin puntuación divisoria: tipo normativo explícito, no «de/del»
# aislado. No identifica una norma concreta ni elimina números repetidos.
_REMISION_RE = re.compile(
    r"(?:del[ \t]+c[óo]digo[ \t]+de\b|"
    r"del[ \t]+decreto[ \t]+\d+\b|"
    r"de[ \t]+la[ \t]+ley[ \t]+\d+\b|"
    r"del[ \t]+presente[ \t]+\w)",
    re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-+*][ \t]+|\d+[.)][ \t]+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unformat_heading(line: str) -> str:
    """Interpretar ATX/negrita iniciales sin limpiar el texto almacenado."""
    plain = re.sub(r"^#{1,6}[ \t]+", "", line.strip())
    if plain.startswith("**"):
        label, closing, rest = plain[2:].partition("**")
        if closing:
            plain = label + rest
    return plain


def _reference_continues_prose(
    text: str, previous: re.Match[str] | None, candidate: re.Match[str]
) -> bool:
    """Excluir solo una remisión plana con continuidad local acreditada."""
    if (
        previous is None
        or candidate.group("sep")
        or candidate.group("bold")
        or candidate.group().lstrip().startswith("#")
        or not _REMISION_RE.match(text, candidate.end())
    ):
        return False

    # Conservar offsets locales para distinguir el epígrafe de su cuerpo.
    lines = []
    offset = previous.start()
    for index, raw in enumerate(
        text[previous.start() : candidate.start()].splitlines(keepends=True)
    ):
        if index:
            lines.append((offset, offset + len(raw), raw))
        offset += len(raw)
    inline = text[previous.end() : candidate.start()].partition("\n")[0]
    epigraphe_end = inline.find(".")
    if epigraphe_end >= 0 and _extract_epigraphe(text[previous.start() : candidate.start()]):
        lines.insert(
            0,
            (
                previous.end() + epigraphe_end + 1,
                previous.end() + len(inline),
                inline[epigraphe_end + 1 :],
            ),
        )
    while lines and not lines[-1][2].strip():
        lines.pop()
    if not lines:
        return False
    page_gap = lines[-1][2].strip().isdecimal()
    if page_gap:
        lines.pop()
    labels = []
    while lines:
        line_start, line_end, line = lines.pop()
        line = line.strip()
        if not line:
            continue
        # Los rótulos gráficos conservan su tratamiento previo. Para el
        # cuerpo, consultar C4 solo hasta esta línea, sin mobiliario posterior.
        if not (page_gap and line.isupper()):
            prefix = text[previous.start() : line_end]
            if _extract_epigraphe(prefix):
                title_end = text.find(".", previous.end(), line_end)
                if title_end < 0:
                    return False
                if title_end >= line_start:
                    line = text[title_end + 1 : line_end].strip()
        plain = _unformat_heading(line)
        if (
            plain != line
            or _looks_like_heading(line)
            or _ARTICULO_RE.match(line)
            or _DISPOSICION_RE.fullmatch(plain)
            or _CONSIDERANDO_RE.fullmatch(plain)
        ):
            return False
        if page_gap and line.isupper():
            # Rótulos planos: sin listas, comillas, HTML ni Markdown.
            if not re.fullmatch(r"[^\W_]+(?:[ \t]+[^\W_]+)*", line):
                return False
            labels.append(line)
            continue
        if page_gap and len(labels) == len(set(labels)):
            return False
        return bool(re.search(r"\b(?:en[ \t]+el|del)[ \t]*$", line, re.IGNORECASE))
    return False


def _article_matches(text: str) -> list[re.Match[str]]:
    """Conservar encabezados; reintegrar solo referencias explícitas."""
    matches = list(_ARTICULO_RE.finditer(text))
    markers = []
    introductions = []
    for line in re.finditer(r"^.*$", text, re.MULTILINE):
        label = _unformat_heading(line.group())
        if _DISPOSICION_RE.fullmatch(label):
            markers.append(line.start())
        elif _CONSIDERANDO_RE.fullmatch(label):
            introductions.append(line.start())

    # Una consideración anterior al primer candidato respalda la zona
    # introductoria. Sin ella, con varios marcadores o articulado inicial,
    # conservar el fallback; no escoger una frontera global arbitraria.
    if (
        len(markers) == 1
        and matches
        and any(pos < matches[0].start() and pos < markers[0] for pos in introductions)
    ):
        matches = [match for match in matches if match.start() > markers[0]]

    own_articles: list[re.Match[str]] = []
    for match in matches:
        previous = own_articles[-1] if own_articles else None
        if _reference_continues_prose(text, previous, match):
            continue
        own_articles.append(match)
    return own_articles


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

    Interpreta ATX/negrita iniciales y exige palabra clave en mayúsculas y
    numeral, sin inferir jerarquía de prosa o encabezados sin número.
    """
    line = _unformat_heading(line)
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


def _extract_epigraphe(body: str) -> str:
    """Título hasta el primer punto, con límite de 80 caracteres.

    Permite continuidad OCR dentro de un párrafo, pero no un rótulo sin título,
    un candidato que cruza párrafos/listas o una introducción con dos puntos.
    No modifica el cuerpo ni certifica que una frase corta sea un título.
    """
    # Compartir la frontera del encabezado, sin reinterpretar su número.
    m = _ARTICULO_RE.match(body)
    if m is None:
        return ""
    after = body[m.end() :]
    end = after.find(".")
    if end < 0:
        end = len(after)
    head = after[:end]
    first_line = head.partition("\n")[0].strip()
    if not first_line or first_line.endswith(":") or re.search(r"\n[ \t]*\n", head):
        return ""
    # Buscar sobre el texto sin truncar: el primer punto puede ser el de «1.».
    list_item = _LIST_ITEM_RE.search(after)
    if list_item and list_item.start() < end:
        return ""
    head = re.sub(r"\s+", " ", head).strip()
    return head if len(head) <= 80 else ""


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


def split_by_articles(doc: Document) -> list[Document]:
    """Parte un ``Document`` de normativa en una unidad por artículo.

    Algoritmo
    ---------
    1. Elimina los headings ``## Página N`` del texto.
    2. Localiza encabezados completos y reintegra referencias explícitas.
    3. Rastrea ``TÍTULO``/``CAPÍTULO`` numerados y extrae epígrafes conservadores.
    4. El texto previo al primer encabezado admitido va a una unidad ``"Preámbulo"``.
    5. Cada ``Document`` hereda la metadata base y añade: ``doc_type``,
       ``articulo``, ``articulo_titulo``, ``titulo``, ``capitulo``,
       ``section_index`` (1-based), ``section_name``.
    """
    base_meta: dict[str, Any] = dict(doc.metadata)

    # 1) Pre-limpieza: quitar marcadores "## Página N".
    text = _PAGINA_RE.sub("", doc.page_content)

    # 2) Localizar los inicios admitidos, sin retirar referencias del texto.
    matches = _article_matches(text)

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

    # Preámbulo: texto antes del primer encabezado admitido.
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

    # Una unidad por encabezado admitido, sin deduplicar su identificador.
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        num = _clean_number(m.group("num"))
        epigraphe = _extract_epigraphe(body)
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
