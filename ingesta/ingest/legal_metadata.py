"""Extracción determinista con evidencia, antes de limpiar el texto jurídico."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

SCHEMA_VERSION = "legal-metadata-1"
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
)
MONTHS = {
    name: i
    for i, name in enumerate(
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
        1,
    )
}


def empty(reason="sin_evidencia"):
    return {"valor": None, "evidencia": None, "confianza": 0.0, "razon": reason}


def extract_legal_metadata(original):
    """Cada evidencia es subcadena NFC del original; ausencias explícitas."""
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
        "magistrado_ponente": r"(?:Magistrad[oa](?:\s+sustanciador[ae]?)?\s+ponente|Consejer[oa]\s+ponente|M\.?\s*P\.?)\s*[:\-]?\s*([^\n\f:]{5,100})",
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
        r"\b(Decreto|Resoluci[oó]n|Ley|Acuerdo)\s*(?:No\.?|N[°º])?\s*(\d{1,6})(?:\s+de\s+(\d{4}))?",
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
        r"\b(\d{1,2})(?:\s*\(\d{1,2}\))?\s+de\s+(" + "|".join(MONTHS) + r")\s+de(?:l)?\s+(\d{4})\b",
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
                r"\b(?:Ley|Decreto|Resoluci[oó]n|Sentencia|Art[íi]culo)\s+[A-Z]{0,3}[- ]?\d[\w.\-/]*(?:\s+de\s+\d{4})?",
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
        quote = unicodedata.normalize("NFC", row.get("evidencia", ""))
        value = row.get("valor", "")
        if value and quote and quote in text:
            metadata["campos"][field] = {
                "valor": value,
                "evidencia": quote,
                "confianza": 1.0,
                "razon": None,
                "origen": "manual",
            }
        else:
            metadata["campos"][field] = empty(
                "override_sin_evidencia" if value else "correccion_manual"
            )
    return metadata
