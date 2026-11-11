"""Extracción determinista con evidencia, antes de limpiar el texto jurídico."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

SCHEMA_VERSION = "legal-metadata-4"
FIELDS = (
    "tipo_documento",
    "corporacion",
    "sala",
    "clase",
    "numero",
    "anio",
    "radicado",
    "fecha_iso",
    "magistrado_ponente",
    "ambito",
    "municipio",
    "normas_citadas",
    "entidad_emisora",
)
TIPOS_NORMA = ("Ley", "Decreto", "Decreto Ley", "Resolución", "Acuerdo", "Circular")
# Campos que identifican cada tipo de documento (puerta de identidad).
IDENTIDAD_REQUERIDA = {
    "jurisprudencia": ("corporacion",),
    "normativa": ("tipo_documento", "numero", "anio"),
}
IDENTIDAD_RECOMENDADA = {
    "jurisprudencia": ("magistrado_ponente",),
    "normativa": ("entidad_emisora", "fecha_iso"),
}
_TIPO = r"(DECRETO(?:[ \t]*-?[ \t]*LEY)?|LEY|RESOLUCI[ÓO]N|ACUERDO|CIRCULAR)"
# Los superíndices son \w, pero no \d: una llamada puede seguir a una cifra
# sin formar parte de ella ni impedir el reconocimiento del año/fecha.
_SUPERINDICES = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_NOTA = rf"[{_SUPERINDICES}]*"
_FIN_NUMERO = rf"(?=\b|[{_SUPERINDICES}])"
_NUMERO = r"(?:N[ÚU]MERO|No\.?|N[°º*]|Nro\.?)?[ \t]*[:.]?[ \t]*(\d{1,5}(?:\.\d{3})?)" + _NOTA
# Encabezado propio de la norma: una línea que solo contiene tipo, número y año.
_ENCABEZADO = re.compile(
    r"(?im)^[ \t]*"
    + _TIPO
    + r"[ \t]+"
    + _NUMERO
    + r"(?:[ \t]+DEL?[ \t]+(\d{4}))?"
    + _NOTA
    + r"[ \t]*\.?[ \t]*$"
)
# Impresiones de SUIN-Juriscol: «DECRETO 1436 DE 1984 - Colombia | SUIN Juriscol».
_SUIN = re.compile(
    r"(?im)^[ \t]*"
    + _TIPO
    + r"[ \t]+(\d{1,5})"
    + _NOTA
    + r"[ \t]+DE[ \t]+(\d{4})"
    + _NOTA
    + r"[ \t]*-[ \t]*Colombia[ \t]*\|[ \t]*SUIN"
)
# Pie del Gestor Normativo de Función Pública: «Decreto 1076 de 2015 Sector ... EVA - Gestor Normativo».
_GESTOR = re.compile(
    r"(?im)^[ \t]*"
    + _TIPO
    + r"[ \t]+(\d{1,5})"
    + _NOTA
    + r"[ \t]+de[ \t]+(\d{4})"
    + _FIN_NUMERO
    + r"[^\n]{0,80}EVA[ \t]*-[ \t]*Gestor[ \t]+Normativo"
)
_EMISOR = re.compile(
    r"(?im)^[ \t]*(?:EL|LA)[ \t]+(PRESIDENTE[ \t]+DE[ \t]+LA[ \t]+REP[ÚU]BLICA"
    r"|ALCALDE(?:SA)?[^\n,]{0,90}|MINISTR[OA][ \t]+DE[^\n,]{3,70}"
    r"|CONGRESO[ \t]+DE[ \t]+(?:LA[ \t]+REP[ÚU]BLICA|COLOMBIA)"
    r"|DIRECTOR[ \t]+GENERAL[ \t]+MAR[ÍI]TIMO[^\n,]{0,40}|GOBERNADOR(?:A)?[^\n,]{0,70}"
    r"|CONCEJO[^\n,]{0,70}|SUPERINTENDENTE[^\n,]{0,60})"
)


def _tipo_norma(texto):
    tipo = " ".join(texto.replace("-", " ").split()).casefold()
    return {
        "ley": "Ley",
        "decreto": "Decreto",
        "decreto ley": "Decreto Ley",
        "resolución": "Resolución",
        "resolucion": "Resolución",
        "acuerdo": "Acuerdo",
        "circular": "Circular",
    }[tipo]


def identidad_normativa(text):
    """Tipo, número y año de la PROPIA norma, solo desde formas de encabezado.

    Nunca toma una norma citada dentro de una frase. Devuelve None si el texto
    (p. ej. un fragmento de compilación) no contiene la identidad de la norma.
    """
    head = text[:6000]
    for patron, origen in ((_ENCABEZADO, "encabezado"), (_SUIN, "suin"), (_GESTOR, "gestor")):
        match = patron.search(head if patron is not _GESTOR else text)
        if match:
            anio = match.group(3)
            fecha = None
            if origen == "encabezado":
                # La fecha de expedición suele ir en las líneas siguientes; una
                # fecha de otro año es de una norma citada y no se usa. Una fecha
                # corta «(agosto 2)» justo tras el encabezado toma su año.
                corta = _FECHA_CORTA.match(text, match.end()) if anio else None
                if corta:
                    mes = corta.group(1) or corta.group(4)
                    dia = corta.group(2) or corta.group(3)
                    fecha = (int(anio), MONTHS[mes.casefold()], int(dia), corta.group().strip())
                for candidata in [] if fecha else _fechas(text, match.end(), match.end() + 600):
                    if not anio or candidata[0] == int(anio):
                        fecha = candidata
                        break
                if not anio and fecha:
                    anio = fecha[0]
            return {
                "tipo": _tipo_norma(match.group(1)),
                "numero": match.group(2).replace(".", ""),
                "anio": int(anio) if anio else None,
                "evidencia": match.group(),
                "fecha": fecha,
                "origen": origen,
            }
    return None


MONTHS = {
    name: i
    for i, name in enumerate(
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
        1,
    )
}


_FECHA = re.compile(
    r"\b(\d{1,2})(?:\s*\(\d{1,2}\))?\s+de\s+("
    + "|".join(MONTHS)
    + r")\s+de(?:l)?\s+(\d{4})"
    + _FIN_NUMERO,
    re.I,
)


_FECHA_MES_PRIMERO = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\s+de(?:l)?\s+(\d{4})" + _FIN_NUMERO,
    re.I,
)


_FECHA_CORTA = re.compile(
    r"\s*\(\s*(?:("
    + "|".join(MONTHS)
    + r")\s+(\d{1,2})|(\d{1,2})\s+de\s+("
    + "|".join(MONTHS)
    + r"))\s*\)",
    re.I,
)


def _fechas(text, inicio, fin):
    """Fechas «15 de octubre de 2024» u «octubre 15 de 2024» en orden de aparición."""
    encontradas = [
        (m.start(), int(m.group(3)), MONTHS[m.group(2).casefold()], int(m.group(1)), m.group())
        for m in _FECHA.finditer(text, inicio, fin)
    ] + [
        (m.start(), int(m.group(3)), MONTHS[m.group(1).casefold()], int(m.group(2)), m.group())
        for m in _FECHA_MES_PRIMERO.finditer(text, inicio, fin)
    ]
    return [f[1:] for f in sorted(encontradas)]


def empty(reason="sin_evidencia"):
    return {"valor": None, "evidencia": None, "confianza": 0.0, "razon": reason}


def identity_gate(metadata, doc_type):
    """Puerta de identidad por tipo: campos requeridos con evidencia y faltantes."""
    tipo = doc_type if doc_type in IDENTIDAD_REQUERIDA else "jurisprudencia"
    campos = metadata["campos"]
    faltan = [c for c in IDENTIDAD_REQUERIDA[tipo] if campos.get(c, {}).get("valor") is None]
    if tipo == "normativa" and campos["tipo_documento"]["valor"] not in TIPOS_NORMA:
        faltan = list(dict.fromkeys(["tipo_documento", *faltan]))
    recomendados = [
        c for c in IDENTIDAD_RECOMENDADA[tipo] if campos.get(c, {}).get("valor") is None
    ]
    return {"pasa": not faltan, "faltan": faltan, "recomendados_ausentes": recomendados}


def extract_legal_metadata(original, doc_type=None):
    """Cada evidencia es subcadena NFC del original; ausencias explícitas.

    Con ``doc_type="normativa"`` la identidad (tipo, número, año, fecha y
    entidad emisora) sale solo del encabezado de la propia norma; si el texto
    no la contiene, esos campos quedan vacíos en lugar de tomar una cita.
    """
    text = unicodedata.normalize("NFC", original)
    head = text[:10000]
    fields = {name: empty() for name in FIELDS}
    conflicts = []

    def assign(name, value, evidence, confidence=0.9):
        if not evidence or evidence not in text:
            fields[name] = empty()
            return
        fields[name] = {
            "valor": value,
            "evidencia": evidence,
            "confianza": confidence,
            "razon": None,
        }

    corp = re.search(
        r"CONSEJO\s+DE\s+ESTADO|CORTE\s+CONSTITUCIONAL|CORTE\s+SUPREMA\s+DE\s+JUSTICIA|TRIBUNAL\s+ADMINISTRATIVO(?:\s+DEL?\s+[A-ZÁÉÍÓÚÑ ]{3,45})?|JUZGADO[^\n]{0,80}ADMINISTRATIVO[^\n]{0,45}|DIRECCI[ÓO]N\s+GENERAL\s+MAR[ÍI]TIMA|ALCALD[ÍI]A[^\n]{0,70}",
        head,
        re.I,
    )
    if corp:
        assign("corporacion", " ".join(corp.group().split()), corp.group(), 0.85)
    patterns = {
        "sala": r"(?:SALA\s+(?:DE\s+LO\s+)?[A-ZÁÉÍÓÚÑ ]{4,70}|SECCI[ÓO]N\s+(?:PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA))",
        "radicado": r"(?:Radicaci[oó]n|Radicado|Expediente)\s*(?:n[úu]mero|no\.?|n[º°])?\s*[:.\-]?\s*([0-9][0-9 .\-()]{8,70})",
        "magistrado_ponente": r"(?<!\w)(?:Magistrad[oa](?:\s+sustanciador[ae]?)?\s+ponente\b|Consejer[oa]\s+ponente\b|M\.?[ \t]*P\.?(?!\w))\s*[:\-]?\s*([^\n\f:]{5,100})",
    }
    for name, pattern in patterns.items():
        matches = list(re.finditer(pattern, head, re.I))
        if matches:
            match = matches[0]
            value = (match.group(1) if match.lastindex else match.group()).strip()
            assign(name, value, match.group())
            distinct = list(
                dict.fromkeys((m.group(1) if m.lastindex else m.group()).strip() for m in matches)
            )
            if len(distinct) > 1:
                conflicts.append({"campo": name, "valores": distinct})
    norm = re.search(
        r"\b(Decreto|Resoluci[oó]n|Ley|Acuerdo)\s*(?:No\.?|N[°º])?\s*(\d{1,6})"
        + _NOTA
        + r"(?:\s+de\s+(\d{4}))?",
        head,
        re.I,
    )
    judgment = re.search(
        r"\bSentencia(?:\s+(?:de\s+)?[A-Z]{1,3}[- ]?\d{1,6}(?:[/\-]\d{2,4})?)?", head, re.I
    )
    is_court = corp and re.search(r"CORTE|CONSEJO|TRIBUNAL|JUZGADO", corp.group(), re.I)
    if is_court:
        assign("tipo_documento", "Sentencia", judgment.group() if judgment else corp.group(), 0.7)
    elif norm:
        assign("tipo_documento", norm.group(1).title(), norm.group())
    if norm and not is_court:
        assign("numero", norm.group(2), norm.group())
        if norm.group(3):
            assign("anio", int(norm.group(3)), norm.group())
    elif judgment:
        number = re.search(r"[A-Z]{1,3}[- ]?\d{1,6}(?:[/\-]\d{2,4})?", judgment.group(), re.I)
        if number:
            assign("numero", number.group(), judgment.group())
    date = re.search(
        r"\b(\d{1,2})(?:\s*\(\d{1,2}\))?\s+de\s+("
        + "|".join(MONTHS)
        + r")\s+de(?:l)?\s+(\d{4})"
        + _FIN_NUMERO,
        head,
        re.I,
    )
    if date:
        try:
            value = dt.date(
                int(date.group(3)), MONTHS[date.group(2).casefold()], int(date.group(1))
            ).isoformat()
            assign("fecha_iso", value, date.group(), 0.85)
            if fields["anio"]["valor"] is None:
                assign("anio", int(date.group(3)), date.group(), 0.8)
        except ValueError:
            fields["fecha_iso"] = empty("fecha_invalida")
    clase = re.search(
        r"acci[oó]n\s+popular|acci[oó]n\s+de\s+tutela|nulidad\s+y\s+restablecimiento|simple\s+nulidad|reparaci[oó]n\s+directa",
        head,
        re.I,
    )
    if clase:
        assign("clase", clase.group(), clase.group())
    city = re.search(
        r"Santa\s+Marta|Cartagena(?:\s+de\s+Indias)?|Turbo|Barranquilla|Buenaventura|Riohacha",
        head,
        re.I,
    )
    if city:
        assign("municipio", city.group(), city.group(), 0.65)
    if corp:
        scope = (
            "nacional"
            if re.search(r"CONSEJO|CORTE|GENERAL MAR", corp.group(), re.I)
            else "departamental"
            if "TRIBUNAL" in corp.group().upper()
            else "municipal"
        )
        assign("ambito", scope, corp.group(), 0.6)
    citations = list(
        dict.fromkeys(
            m.group()
            for m in re.finditer(
                rf"\b(?:Ley|Decreto|Resoluci[oó]n|Sentencia|Art[íi]culo)\s+[A-Z]{{0,3}}[- ]?\d(?:(?![{_SUPERINDICES}])[\w.\-/])*(?:{_NOTA}\s+de\s+\d{{4}})?",
                text,
                re.I,
            )
        )
    )
    if citations:
        fields["normas_citadas"] = {
            "valor": citations,
            "evidencia": citations,
            "confianza": 0.8,
            "razon": None,
        }
    if doc_type == "normativa":
        identidad = identidad_normativa(text)
        for name in ("tipo_documento", "numero", "anio", "fecha_iso"):
            fields[name] = empty("sin_identidad_en_texto")
        if identidad:
            confianza = {"encabezado": 0.9, "suin": 0.85, "gestor": 0.75}[identidad["origen"]]
            assign("tipo_documento", identidad["tipo"], identidad["evidencia"], confianza)
            assign("numero", identidad["numero"], identidad["evidencia"], confianza)
            if identidad["anio"]:
                assign("anio", identidad["anio"], identidad["evidencia"], confianza)
            fecha = identidad["fecha"]
            if fecha:
                anio, mes, dia, evidencia = fecha
                try:
                    assign("fecha_iso", dt.date(anio, mes, dia).isoformat(), evidencia, 0.85)
                    if fields["anio"]["valor"] is None:
                        assign("anio", anio, evidencia, 0.8)
                except ValueError:
                    fields["fecha_iso"] = empty("fecha_invalida")
        emisor = _EMISOR.search(head)
        if emisor:
            valor = " ".join(emisor.group(1).split())
            valor = re.sub(r"\s+DE$", "", valor, flags=re.I)
            assign("entidad_emisora", valor[:1].upper() + valor[1:].lower(), emisor.group(), 0.8)
    return {"schema_version": SCHEMA_VERSION, "campos": fields, "conflictos": conflicts}


def apply_overrides(metadata, rows, doc_id, original):
    """Manual gana; evidencia inválida queda pendiente, nunca inventada."""
    text = unicodedata.normalize("NFC", original)
    for row in rows:
        if row.get("doc_id") != doc_id:
            continue
        field = row.get("campo")
        if field not in FIELDS:
            raise ValueError("Campo de override desconocido")
        quote = unicodedata.normalize("NFC", row.get("evidencia") or "")
        value = unicodedata.normalize("NFC", row.get("valor") or "")
        value = "".join(
            " " if c in "\n\r\t" else c
            for c in value
            if unicodedata.category(c) not in {"Cc", "Cf"} or c in "\n\r\t"
        )
        value = value.strip()
        if value and quote and quote in text:
            metadata["campos"][field] = {
                "valor": value,
                "evidencia": quote,
                "confianza": 1.0,
                "razon": None,
                "origen": "manual",
            }
            resolved = [c for c in metadata["conflictos"] if c["campo"] == field]
            if resolved:
                metadata.setdefault("conflictos_resueltos_manual", []).extend(resolved)
                metadata["conflictos"] = [c for c in metadata["conflictos"] if c["campo"] != field]
        else:
            metadata["campos"][field] = empty(
                "override_sin_evidencia" if value else "correccion_manual"
            )
    return metadata
