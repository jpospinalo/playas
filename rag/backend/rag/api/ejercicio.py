"""Reglas del ejercicio de validación del agente (documento del profe y
"Planilla de evaluación-agente jurídico"). Sin IA: puro cálculo.

- Participantes: número de participante y un tipo de usuario de playa (1-5).
- Puntaje de una pregunta = Forma (F1+F2+F3, cada uno de 1 a 3) + Cv.
- Cv depende de la complejidad Ct: S (sencillo) 3-6, I (intermedio) 7-9,
  A (avanzado) 10-12.
- Cada pregunta la califican dos evaluadores (uno por sede). Si difieren en
  Ct o en más de ``UMBRAL_DIFERENCIA`` puntos de total, pasa al comité, que
  fija la calificación final ("Revisó").
- Premios: mejor pregunta por nivel (mayor Cv) y participación más constante
  (días distintos con preguntas válidas; desempate: cantidad, luego puntaje).
"""

from __future__ import annotations

import io
import os
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from xml.sax.saxutils import escape

# ── Catálogos ────────────────────────────────────────────────────────────────

TIPOS_PLAYA: dict[int, str] = {
    1: "Residentes",
    2: "Pescadores",
    3: "Comerciantes",
    4: "Empresarios",
    5: "Turistas",
}
# Nombre largo, como en el listado de tipos de usuario de playa.
TIPOS_PLAYA_LARGO: dict[int, str] = {
    1: "Residentes, habitantes y propietarios de predios o viviendas costeras",
    2: "Pescadores",
    3: "Comerciantes y trabajadores de playa",
    4: "Hoteleros, restauranteros y empresas de servicios vinculados a la playa",
    5: "Turistas y visitantes",
}

ROLES = ("user", "evaluador", "comite", "admin")
ROLES_EVALUACION = frozenset({"evaluador", "comite", "admin", "super-admin"})
ROLES_COMITE = frozenset({"comite", "admin", "super-admin"})
SEDES = ("Santa Marta", "Barranquilla")

RANGOS_CV: dict[str, tuple[int, int]] = {"S": (3, 6), "I": (7, 9), "A": (10, 12)}
NIVELES = {"S": "Sencillo", "I": "Intermedio", "A": "Avanzado"}
# Valor de la columna Ct en la planilla de Excel.
CT_PLANILLA = {"S": "S - Sencillo", "I": "I - Intermedio", "A": "A - Avanzado"}

# Diferencia de puntaje total a partir de la cual dos evaluaciones del mismo
# nivel se consideran distintas (configurable sin tocar código).
UMBRAL_DIFERENCIA = int(os.getenv("EVAL_UMBRAL_DIFERENCIA", "2"))

# El documento dice que el comité valida todas las evaluaciones. Con dos
# calificaciones concordantes, la planilla ya tiene un valor (el promedio),
# pero queda "pendiente de revisión del comité". Si esta variable es "true",
# solo cuentan para resumen y premios las que el comité revisó (decisión de
# Juan, PQ-55); por defecto cuentan también las concordantes.
PREMIOS_SOLO_REVISADAS = os.getenv("EVAL_PREMIOS_SOLO_REVISADAS", "false").lower() == "true"

# Rúbrica de la hoja "Instructivo", para mostrarla en la ficha de evaluación.
RUBRICA_FORMA = {
    "f1": {
        "nombre": "F1 - Contextualización",
        "pregunta": "¿Se entiende desde qué realidad o perfil se formula la consulta?",
        "niveles": {
            1: "No permite identificar quién consulta, qué actividad realiza ni su situación.",
            2: "Incluye parte del contexto, pero faltan datos relevantes sobre la persona, actividad o situación.",
            3: "Identifica claramente quién consulta, qué actividad realiza y cuál es su situación particular.",
        },
    },
    "f2": {
        "nombre": "F2 - Problema concreto",
        "pregunta": "¿Existe una situación concreta que el agente deba resolver?",
        "niveles": {
            1: "No plantea un problema o duda concreta.",
            2: "Hay un problema identificable, pero está incompleto, es general o poco delimitado.",
            3: "Plantea con claridad un problema, conflicto, necesidad o duda concreta relacionada con la playa.",
        },
    },
    "f3": {
        "nombre": "F3 - Redacción",
        "pregunta": "¿El agente puede comprender la consulta sin tener que adivinar qué se pregunta?",
        "niveles": {
            1: "La pregunta es confusa o difícil de comprender.",
            2: "La pregunta se comprende, aunque presenta ambigüedades o falta de precisión.",
            3: "La pregunta es clara, coherente y suficientemente precisa para ser respondida.",
        },
    },
}
RUBRICA_FONDO = {
    "S": {
        "nivel": "Sencillo",
        "como": "La respuesta puede darse mediante aplicación directa de la normativa sobre uso, acceso u ocupación de playas. No presenta un conflicto jurídico complejo ni exige analizar múltiples actores o entidades.",
        "guia": {
            3: "Caso sencillo básico.",
            4: "Sencillo con contexto suficiente.",
            5: "Sencillo bien desarrollado y pertinente.",
            6: "Sencillo especialmente claro, completo y útil para la validación.",
        },
    },
    "I": {
        "nivel": "Intermedio",
        "como": "Existe un conflicto real entre dos o más actores sobre acceso, uso, ocupación o aprovechamiento de la playa. Exige analizar intereses o derechos de las partes.",
        "guia": {
            7: "Conflicto identificable con desarrollo suficiente.",
            8: "Conflicto claro con varios elementos jurídicos relevantes.",
            9: "Caso intermedio muy bien desarrollado que exige analizar derechos o intereses de dos o más actores.",
        },
    },
    "A": {
        "nivel": "Avanzado",
        "como": "Plantea una problemática jurídica compleja; puede involucrar gestión del riesgo, varias entidades públicas, derechos colectivos, acciones de grupo o articulación de varias normas y competencias.",
        "guia": {
            10: "Problemática compleja claramente identificada.",
            11: "Exige articular varios actores, normas o competencias.",
            12: "Caso avanzado especialmente completo y útil para poner a prueba al agente.",
        },
    },
}


# ── Puntajes ─────────────────────────────────────────────────────────────────


def validar_calificacion(f1: int, f2: int, f3: int, ct: str, cv: int) -> str | None:
    """Mensaje de error si la calificación no cumple la planilla, o ``None``."""
    for nombre, valor in (("F1", f1), ("F2", f2), ("F3", f3)):
        if valor not in (1, 2, 3):
            return f"{nombre} debe ser 1, 2 o 3."
    if ct not in RANGOS_CV:
        return "Ct debe ser S, I o A."
    minimo, maximo = RANGOS_CV[ct]
    if not minimo <= cv <= maximo:
        return f"Para un caso {NIVELES[ct].lower()}, Cv va de {minimo} a {maximo}."
    return None


def puntaje_forma(f1: int, f2: int, f3: int) -> int:
    return f1 + f2 + f3


def puntaje_total(f1: int, f2: int, f3: int, cv: int) -> int:
    return puntaje_forma(f1, f2, f3) + cv


@dataclass(frozen=True)
class Calificacion:
    evaluador_id: str
    evaluador: str
    sede: str | None
    f1: int
    f2: int
    f3: int
    ct: str
    cv: int
    total: int
    valida: bool
    observaciones: str | None
    es_final: bool


def hay_diferencia(a: Calificacion, b: Calificacion, umbral: int = UMBRAL_DIFERENCIA) -> bool:
    """Distinto nivel, distinta validez o total separado por ``umbral`` o más."""
    return a.ct != b.ct or a.valida != b.valida or abs(a.total - b.total) >= umbral


ESTADOS = ("sin_evaluar", "una_evaluacion", "concordante", "con_diferencias", "final")


@dataclass(frozen=True)
class Oficial:
    """Calificación que cuenta para el resumen, los premios y el Excel."""

    estado: str
    f1: int | None = None
    f2: int | None = None
    f3: int | None = None
    ct: str | None = None
    cv: int | None = None
    total: int | None = None
    valida: bool | None = None
    evaluo: str = ""
    reviso: str = ""
    observaciones: str = ""


def _media(a: int, b: int) -> int:
    # Redondeo "hacia arriba" en .5, como lo haría una persona con la planilla.
    return (a + b + 1) // 2


def calificacion_oficial(cals: list[Calificacion]) -> Oficial:
    """Final del comité si existe; si no, el promedio de dos concordantes."""
    finales = [c for c in cals if c.es_final]
    evals = [c for c in cals if not c.es_final]
    evaluo = ", ".join(c.evaluador for c in evals)
    obs = " | ".join(c.observaciones for c in cals if c.observaciones)
    if finales:
        f = finales[-1]
        return Oficial(
            "final", f.f1, f.f2, f.f3, f.ct, f.cv, f.total, f.valida, evaluo, f.evaluador, obs
        )
    if len(evals) < 2:
        return Oficial(
            "una_evaluacion" if evals else "sin_evaluar", evaluo=evaluo, observaciones=obs
        )
    a, b = evals[0], evals[1]
    if hay_diferencia(a, b):
        return Oficial("con_diferencias", evaluo=evaluo, observaciones=obs)
    f1, f2, f3 = _media(a.f1, b.f1), _media(a.f2, b.f2), _media(a.f3, b.f3)
    lo, hi = RANGOS_CV[a.ct]
    cv = min(hi, max(lo, _media(a.cv, b.cv)))
    return Oficial(
        # Concordantes: misma validez por definición (si no, habría diferencia).
        "concordante",
        f1,
        f2,
        f3,
        a.ct,
        cv,
        puntaje_total(f1, f2, f3, cv),
        a.valida,
        evaluo,
        "",
        obs,
    )


# ── Premios ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreguntaOficial:
    message_id: str
    codigo: str
    fecha: datetime  # hora de Colombia
    texto: str
    oficial: Oficial


def mejores_por_nivel(
    preguntas: list[PreguntaOficial], elegidas: dict[str, str] | None = None, top: int = 3
) -> dict[str, dict]:
    """Mejor pregunta de cada nivel = mayor Cv (puntaje de Fondo) entre las
    válidas. Si varias comparten el Cv más alto, hay **empate** y decide el
    comité (``elegidas``: nivel → message_id); la app no desempata por fecha
    ni por puntaje total. Devuelve, por nivel, la ganadora (o ``None`` si hay
    empate sin decidir), las empatadas y las siguientes."""
    elegidas = elegidas or {}
    salida: dict[str, dict] = {}
    for ct in RANGOS_CV:
        candidatas = [
            p for p in preguntas if p.oficial.valida and p.oficial.ct == ct and p.oficial.cv
        ]
        # Solo para mostrarlas en orden estable: Cv y luego orden de llegada.
        candidatas.sort(key=lambda p: (-(p.oficial.cv or 0), p.fecha))
        if not candidatas:
            salida[ct] = {
                "ganadora": None,
                "empatadas": [],
                "siguientes": [],
                "decide_comite": False,
            }
            continue
        mejor_cv = candidatas[0].oficial.cv
        empatadas = [p for p in candidatas if p.oficial.cv == mejor_cv]

        def fila(p: PreguntaOficial) -> dict:
            return {
                "message_id": p.message_id,
                "codigo": p.codigo,
                "texto": p.texto,
                "cv": p.oficial.cv,
                "total": p.oficial.total,
            }

        ganadora = None
        if len(empatadas) == 1:
            ganadora = fila(empatadas[0])
        elif elegidas.get(ct) in {p.message_id for p in empatadas}:
            ganadora = fila(next(p for p in empatadas if p.message_id == elegidas[ct]))
        salida[ct] = {
            "ganadora": ganadora,
            "empatadas": [fila(p) for p in empatadas] if len(empatadas) > 1 else [],
            "decide_comite": len(empatadas) > 1,
            "siguientes": [fila(p) for p in candidatas[len(empatadas) : len(empatadas) + top]],
        }
    return salida


def ranking_participantes(preguntas: list[PreguntaOficial]) -> list[dict]:
    """Participación más constante: días distintos con preguntas válidas;
    desempate por número de preguntas válidas y luego puntaje acumulado
    (criterios numéricos del documento). Trae el puntaje acumulado, que sirve
    para la gratificación (no es un premio aparte)."""
    por_codigo: dict[str, list[PreguntaOficial]] = defaultdict(list)
    for p in preguntas:
        if p.oficial.valida and p.oficial.total is not None:
            por_codigo[p.codigo].append(p)
    filas = [
        {
            "codigo": codigo,
            "dias": len({p.fecha.date() for p in ps}),
            "preguntas_validas": len(ps),
            "puntaje": sum(p.oficial.total or 0 for p in ps),
        }
        for codigo, ps in por_codigo.items()
    ]
    filas.sort(key=lambda f: (-f["dias"], -f["preguntas_validas"], -f["puntaje"], f["codigo"]))
    # Si los primeros empatan en los tres criterios, decide el comité (PQ-57).
    if filas:
        clave = (filas[0]["dias"], filas[0]["preguntas_validas"], filas[0]["puntaje"])
        empatados = [f for f in filas if (f["dias"], f["preguntas_validas"], f["puntaje"]) == clave]
        for f in filas:
            f["empate"] = len(empatados) > 1 and f in empatados
    return filas


# ── Excel (.xlsx) sin dependencias ───────────────────────────────────────────


def _col(n: int) -> str:
    letras = ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def _hoja(filas: list[list[object]], anchos: list[float], controles: str = "") -> str:
    cols = "".join(
        f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(anchos, 1)
    )
    xml_filas = []
    for r, fila in enumerate(filas, 1):
        celdas = []
        for c, valor in enumerate(fila, 1):
            ref = f"{_col(c)}{r}"
            estilo = ' s="1"' if r == 1 else ""
            if valor is None or valor == "":
                continue
            if isinstance(valor, bool):
                valor = "Sí" if valor else "No"
            if isinstance(valor, (int, float)):
                celdas.append(f'<c r="{ref}"{estilo}><v>{valor}</v></c>')
            else:
                texto = escape(str(valor))
                celdas.append(
                    f'<c r="{ref}" t="inlineStr"{estilo}><is><t xml:space="preserve">{texto}</t></is></c>'
                )
        xml_filas.append(f'<row r="{r}">{"".join(celdas)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{cols}</cols><sheetData>{''.join(xml_filas)}</sheetData>{controles}</worksheet>"
    )


def controles_planilla(filas: int) -> str:
    """Las mismas validaciones de la hoja "Evaluación" de la planilla del
    equipo jurídico, para que una corrección a mano en el Excel exportado no
    se salga de las reglas (B22): listas de F1-F3, Ct y tipo de usuario, Cv de
    3 a 12, y Cv en rojo si no cae en el rango de su Ct (Instructivo A17)."""
    ultima = max(501, filas + 100)
    tipos = ",".join(f"Tipo {n}. {t}" for n, t in TIPOS_PLAYA.items())
    niveles = ",".join(CT_PLANILLA[c] for c in ("S", "I", "A"))
    fuera = (
        'AND($L2<>"",OR(AND(LEFT($K2,1)="S",OR($L2<3,$L2>6)),'
        'AND(LEFT($K2,1)="I",OR($L2<7,$L2>9)),AND(LEFT($K2,1)="A",OR($L2<10,$L2>12))))'
    )

    def lista(rango: str, valores: str, titulo: str) -> str:
        return (
            f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
            f'errorTitle="{escape(titulo)}" error="Elija un valor de la lista." sqref="{rango}">'
            f'<formula1>"{escape(valores)}"</formula1></dataValidation>'
        )

    return (
        f'<conditionalFormatting sqref="L2:L{ultima}"><cfRule type="expression" dxfId="0" '
        f'priority="1"><formula>{escape(fuera)}</formula></cfRule></conditionalFormatting>'
        '<dataValidations count="4">'
        + lista(f"E2:E{ultima}", tipos, "Tipo de usuario de playa")
        + lista(f"G2:I{ultima}", "1,2,3", "F1, F2 y F3")
        + lista(f"K2:K{ultima}", niveles, "Complejidad tipo (Ct)")
        + f'<dataValidation type="whole" operator="between" allowBlank="1" showErrorMessage="1" '
        f'errorTitle="Cv" error="Cv va de 3 a 12 (S 3-6, I 7-9, A 10-12)." sqref="L2:L{ultima}">'
        "<formula1>3</formula1><formula2>12</formula2></dataValidation>"
        "</dataValidations>"
    )


def libro_xlsx(hojas: list[tuple]) -> bytes:
    """Arma un .xlsx mínimo (texto y números, encabezado en negrita). Cada hoja
    es (nombre, filas, anchos) o (nombre, filas, anchos, controles XML)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(hojas) + 1)
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(nombre)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, (nombre, *_) in enumerate(hojas, 1)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(hojas) + 1)
            )
            + f'<Relationship Id="rId{len(hojas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="2"><xf/><xf fontId="1" applyFont="1"><alignment wrapText="1"/></xf></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            # Formato de "Cv fuera de rango" (rojo, como la planilla).
            '<dxfs count="1"><dxf><font><color rgb="FF9C0006"/></font>'
            '<fill><patternFill><bgColor rgb="FFFFC7CE"/></patternFill></fill></dxf></dxfs>'
            "</styleSheet>",
        )
        for i, (_, filas, anchos, *controles) in enumerate(hojas, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _hoja(filas, anchos, *controles))
    return buf.getvalue()


# Columnas de la hoja "Evaluación" de la planilla, en el mismo orden.
COLUMNAS_PLANILLA = [
    "ID pregunta",
    "ID Usuario",
    "Fecha",
    "Hora",
    "Tipo de Usuario de Playa",
    "Pregunta formulada",
    "F1\nContextualización",
    "F2\nProblema concreto",
    "F3\nRedacción",
    "Puntaje de forma",
    "Ct\nComplejidad tipo",
    "Cv\nValor de fondo",
    "Puntaje Total",
    "Observaciones",
    "Evaluó",
    "Revisó",
]
ANCHOS_PLANILLA = [12, 14, 12, 10, 24, 46.9, 20, 20.3, 14, 16, 20, 16, 14, 36, 18, 18]


def celda_segura(valor: object) -> object:
    """Evita que Excel ejecute texto como fórmula (=, +, -, @)."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor
