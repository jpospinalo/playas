"""Casos sintéticos de comparación e integridad; sin acceder a U real."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2] / "benchmarks/ocr_referencia"
_spec = importlib.util.spec_from_file_location("fiabilidad_capas", BASE / "fiabilidad.py")
f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f)


def escribir_auditoria(ruta, filas):
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            [
                "sufijo",
                "veredicto_auditado",
                "causa_dominante",
                "justificacion",
                *f.HUELLAS_AUDITORIA,
            ]
        )
        escritor.writerows([*fila, *(["a" * 64] * 3)] for fila in filas)


@pytest.mark.parametrize("color", f.COLORES[:4])
def test_auditoria_aplica_color_causa_justificacion_y_fallback(tmp_path, color):
    ruta = tmp_path / "auditoria.csv"
    escribir_auditoria(ruta, [["922e", color, "U y métrica", "Texto, º/° y tablas"]])
    documentos = [
        {
            "slug": "documento_922e",
            "veredicto_automatico": "rojo",
            **dict.fromkeys(f.HUELLAS_AUDITORIA, "a" * 64),
            "gold_cobertura_silver": 1,
            "gold_cobertura_efectiva_silver": 1,
        },
        {"slug": "otro_abcd", "veredicto_automatico": "verde"},
    ]
    auditoria = f.cargar_auditoria(ruta, documentos)
    f.aplicar_auditoria(documentos, auditoria)
    assert documentos[0]["veredicto_automatico"] == "rojo"
    assert documentos[0]["veredicto_final"] == color
    assert documentos[0]["estado_auditoria"] == "aplicada"
    assert documentos[0]["veredicto_auditado"] == color
    assert documentos[0]["causa_auditada"] == "U y métrica"
    assert documentos[0]["justificacion_auditoria"] == "Texto, º/° y tablas"
    assert documentos[1]["veredicto_final"] == "verde"
    assert documentos[1]["veredicto_auditado"] == ""
    assert documentos[1]["causa_auditada"] == ""
    assert documentos[1]["justificacion_auditoria"] == ""


@pytest.mark.parametrize(
    ("filas", "slugs", "error"),
    [
        ([["ffff", "rojo", "", ""]], ["doc_922e"], "Sufijo"),
        ([["922e", "rojo", "", ""]], ["doc_922e", "otro_922e"], "ambiguo"),
        ([["922e", "ROJO", "", ""]], ["doc_922e"], "Veredicto"),
        ([["922e", "sin evaluar", "", ""]], ["doc_922e"], "Veredicto"),
        ([["922e", "", "", ""]], ["doc_922e"], "Veredicto"),
        ([["922e", "rojo", "", ""]] * 2, ["doc_922e"], "duplicado"),
    ],
)
def test_auditoria_rechaza_datos_invalidos(tmp_path, filas, slugs, error):
    ruta = tmp_path / "auditoria.csv"
    escribir_auditoria(ruta, filas)
    with pytest.raises(ValueError, match=error):
        f.cargar_auditoria(ruta, [{"slug": slug} for slug in slugs])


def test_auditoria_rechaza_columnas_incompletas(tmp_path):
    ruta = tmp_path / "auditoria.csv"
    ruta.write_text("sufijo,veredicto_auditado\n922e,rojo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Columnas"):
        f.cargar_auditoria(ruta, [{"slug": "doc_922e"}])


def test_resumen_cuenta_finales_y_conserva_automaticos_por_categoria_y_conjunto():
    documentos = [
        {
            "slug": "doc_922e",
            "categoria": "normativa",
            "conjunto": "ajuste",
            "veredicto_final": "no distinguible de U",
            "veredicto_automatico": "rojo",
        },
        {
            "slug": "otro_abcd",
            "categoria": "normativa",
            "conjunto": "validacion",
            "veredicto_final": "verde",
            "veredicto_automatico": "verde",
        },
    ]
    resumen = f.resumen_agregado(documentos, [])
    for grupo in (resumen["ajuste"], resumen["ajuste"]["categorias"]["normativa"]):
        assert grupo["colores"]["no distinguible de U"] == 1
        assert grupo["colores"]["rojo"] == 0
        assert grupo["colores_automaticos"]["rojo"] == 1
    assert resumen["validacion"]["colores"]["verde"] == 1
    assert resumen["validacion"]["colores"]["no distinguible de U"] == 0


def test_sensibilidad_filtra_en_puntos_porcentuales_y_muestra_corpus():
    datos = {
        "_corpus": {"cer": 0.01201269, "cer_grado_unificado": 0.01196287},
        "cambio_grande": {"cer": 0.02, "cer_grado_unificado": 0.0194},
        "cambio_pequeno": {"cer": 0.02, "cer_grado_unificado": 0.0196},
    }
    texto = "\n".join(f.informe_sensibilidad(datos))
    assert "1.201269 % → 1.196287 %" in texto
    assert "cambio_grande" in texto
    assert "cambio_pequeno" not in texto


def test_hashes_compara_por_ruta_incluye_cambios_y_ausentes(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    h1, h2 = "a" * 64, "b" * 64
    a.write_text(
        f"{h1}  ./pdf/capas/bronze/a.txt\n"
        f"{h1}  ./pdf/capas/silver/a.txt\n"
        f"{h1}  ./md/capas/gold/a.jsonl\n",
        encoding="utf-8",
    )
    b.write_text(
        f"{h2}  md/capas/gold/b.jsonl\n"
        f"{h2}  pdf/capas/silver/a.txt\n"
        f"{h1.upper()} *pdf\\capas\\bronze\\a.txt\n",
        encoding="utf-8",
    )
    resultado = f.comparar_hashes(a, b)
    assert (resultado["archivos"], resultado["identicos"], resultado["distintos"]) == (4, 1, 3)
    assert resultado["por_etapa"]["bronze"] == {"archivos": 1, "identicos": 1, "distintos": 0}
    assert resultado["por_etapa"]["silver"]["distintos"] == 1
    assert resultado["por_etapa"]["gold"]["distintos"] == 2
    assert resultado["por_tipo"]["pdf"]["archivos"] == 2
    assert resultado["por_tipo"]["md"]["distintos"] == 2
    assert resultado["por_tipo"]["md"]["por_etapa"]["gold"]["distintos"] == 2
    assert resultado["solo_runA"] == ["md/capas/gold/a.jsonl"]
    assert resultado["solo_runB"] == ["md/capas/gold/b.jsonl"]
    assert resultado["rutas_distintas"] == [
        "md/capas/gold/a.jsonl",
        "md/capas/gold/b.jsonl",
        "pdf/capas/silver/a.txt",
    ]


def test_hashes_identicos_con_orden_distinto(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    lineas = [f"{'a' * 64}  ./pdf/capas/{etapa}/x.txt\n" for etapa in ("bronze", "gold")]
    a.write_text("".join(lineas), encoding="utf-8")
    b.write_text("".join(reversed(lineas)), encoding="utf-8")
    resultado = f.comparar_hashes(a, b)
    assert resultado["archivos"] == resultado["identicos"] == 2
    assert resultado["distintos"] == 0
    assert resultado["rutas_distintas"] == []


@pytest.mark.parametrize(
    "contenido",
    [
        "hash inválido  ./pdf/capas/bronze/x.txt\n",
        f"{'a' * 64}  /pdf/capas/bronze/x.txt\n",
        f"{'a' * 64}  ./pdf/capas/bronze/../x.txt\n",
        f"{'a' * 64}  ./pdf/capas/otra/x.txt\n",
        f"{'a' * 64}  ./pdf/capas/bronze/x.txt\n" * 2,
    ],
)
def test_hashes_rechaza_manifiestos_invalidos(tmp_path, contenido):
    ruta = tmp_path / "hashes.txt"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ValueError):
        f.cargar_hashes(ruta)


def test_union_gold_solape_huecos_y_extremos():
    texto = "abcdefghijklmnopqrst"
    resultado = f.cobertura_gold(texto, [(6, 10), (2, 8), (14, 18), (14, 18)])
    assert resultado["gold_caracteres_cubiertos"] == 12
    assert resultado["gold_cobertura_silver"] == 0.6
    assert resultado["gold_numero_huecos"] == 3
    assert resultado["gold_huecos_mayores"][0] == {
        "inicio": 10,
        "fin": 14,
        "caracteres": 4,
        "muestra": "klmn",
    }
    assert f.union_tramos([(0, 3), (3, 20), (20, 20)], 20) == [(0, 20)]
    assert f.cobertura_gold("", [])["gold_cobertura_silver"] is None
    assert f.cobertura_gold(texto, [])["gold_caracteres_huecos"] == 20


@pytest.mark.parametrize("tramo", [(-1, 3), (3, 2), (0, 21), (0.5, 3)])
def test_offsets_invalidos_no_se_recortan_silenciosamente(tramo):
    with pytest.raises(ValueError, match="Tramo|Offsets"):
        f.union_tramos([tramo], 20)


def test_lineas_eliminadas_complemento_exacto_con_paginas_y_fragmentos():
    bronce = "CAB\ntexto\n\n\f\nPIE\nfinal"
    a, b = bronce.index("texto"), bronce.index("final")
    mapa = [{"source_start": a, "source_end": a + 5}, {"source_start": b, "source_end": b + 2}]
    eliminadas = f.lineas_eliminadas(bronce, mapa)
    assert [(x["pagina"], x["linea"], x["texto"]) for x in eliminadas] == [
        (1, 1, "CAB"),
        (2, 1, "PIE"),
        (2, 2, "nal"),
    ]
    assert all(bronce[x["inicio"] : x["fin"]].strip() == x["texto"] for x in eliminadas)
    assert f.lineas_eliminadas(bronce, [{"source_start": 0, "source_end": len(bronce)}]) == []


def test_perdida_silver_respeta_multiconjuntos_y_denominador():
    resultado = f.perdida_silver("a a b c", "a a b ruido ruido", "a b ruido")
    assert resultado["silver_palabras_u_bronce"] == 3
    assert resultado["silver_palabras_perdidas"] == 1
    assert resultado["silver_perdida"] == pytest.approx(1 / 3)
    assert resultado["bronce_ruido"] == pytest.approx(2 / 5)
    assert resultado["silver_ruido"] == pytest.approx(1 / 3)
    assert f.perdida_silver("", "algo", "")["silver_perdida"] is None
    # Un ejemplar de U no permite recuperar dos repeticiones del bronce.
    assert f.perdida_silver("a", "a a", "a")["silver_perdida"] == 0
    assert f.perdida_silver("**Árbol**", "Árbol", "árbol")["silver_perdida"] == 0


def test_separacion_mobiliario_otra_con_denominador_comun():
    cabecera = "Departamento Administrativo de la Función Pública"
    pie = "www.consejodeestado.gov.co"
    # Folio que sigue la paginación (1, 2, 3): número aislado exonerable.
    bronce = "\n\f\n".join(f"{cabecera}\nArtículo 7 protege costa\n{pie}\n{i}" for i in (1, 2, 3))
    claves = [f.clave_mobiliario(cabecera), f.clave_mobiliario(pie)]
    resultado = f.perdida_silver(
        bronce,
        bronce,
        "Artículo 7 protege\n" * 3,
        eliminadas=f.lineas_eliminadas(bronce, [], claves),
    )
    denominador = sum(f.palabras(bronce).values())
    mobiliario = 3 * sum(f.palabras(cabecera + "\n" + pie + "\n1").values())
    assert resultado["silver_palabras_perdidas_mobiliario"] == mobiliario
    assert resultado["silver_palabras_perdidas_otras"] == 3
    assert resultado["perdida_silver_mobiliario"] == pytest.approx(mobiliario / denominador)
    assert resultado["perdida_silver_otra"] == pytest.approx(3 / denominador)
    assert resultado["perdida_silver"] == resultado["silver_perdida"]
    assert resultado["silver_perdida"] == pytest.approx(
        resultado["perdida_silver_mobiliario"] + resultado["perdida_silver_otra"]
    )


def test_clave_independiente_equipara_numeros_espacios_y_mayusculas():
    linea = "  CALLE 12   No. 7-65 Bogotá  "
    clave = f.clave_mobiliario("calle 99 No. 8-32 bogotá")
    assert f.es_mobiliario(linea, [clave])
    assert f.es_folio("  234  ", 4, True, {230})
    assert not f.es_folio("  234  ", 4, True, set())
    assert not f.es_folio("  234  ", 4, False, {230})
    assert not f.es_mobiliario("Artículo 234", [])
    assert not f.es_mobiliario("12,5", [])


def test_candidato_no_es_evidencia_independiente():
    bronce = "Institución\nArtículo 7 protegido"
    claves = [f.clave_mobiliario("Institución")]
    resultado = f.perdida_silver(
        bronce,
        bronce,
        "Artículo 7 protegido",
        eliminadas=f.lineas_eliminadas(bronce, [], claves),
    )
    assert resultado["silver_palabras_perdidas_mobiliario"] == 0
    assert resultado["silver_palabras_perdidas_otras"] == 1
    eliminadas = f.lineas_eliminadas(bronce, [], claves)
    assert eliminadas[0]["candidato_rechazado"]
    assert not eliminadas[0]["mobiliario"]


def test_mobiliario_no_cuenta_palabras_conservadas_ni_ausentes_de_u():
    bronce = "cabecera ruido\ncontenido borrado"
    claves = [f.clave_mobiliario("cabecera ruido")]
    resultado = f.perdida_silver(
        "contenido borrado",
        bronce,
        "contenido",
        eliminadas=f.lineas_eliminadas(bronce, [], claves),
    )
    assert resultado["perdida_silver_mobiliario"] == 0
    assert resultado["perdida_silver_otra"] == 0.5
    sin_perdida = f.perdida_silver(bronce, bronce, bronce, eliminadas=[])
    assert sin_perdida["perdida_silver_mobiliario"] == sin_perdida["perdida_silver_otra"] == 0
    vacio = f.perdida_silver("", bronce, "", eliminadas=f.lineas_eliminadas(bronce, [], claves))
    assert vacio["perdida_silver_mobiliario"] is vacio["perdida_silver_otra"] is None


def test_separacion_no_duplica_ocurrencias_compartidas_entre_tipos_de_linea():
    bronce = "\n\f\n".join(["común común\ncomún único"] * 3)
    claves = [f.clave_mobiliario("común común")]
    resultado = f.perdida_silver(
        bronce, bronce, "común " * 3, eliminadas=f.lineas_eliminadas(bronce, [], claves)
    )
    assert resultado["silver_palabras_perdidas"] == 9
    assert resultado["silver_palabras_perdidas_mobiliario"] == 6
    assert resultado["silver_palabras_perdidas_otras"] == 3
    assert resultado["perdida_silver_mobiliario"] == 0.5
    assert resultado["perdida_silver_otra"] == 0.25


def test_fragmento_sin_primera_letra_se_clasifica_por_linea_original():
    cabecera = "Departamento Administrativo"
    bronce = "\n\f\n".join([cabecera + "\ncontenido perdido"] * 3)
    # Un separador insertado se asocia a la D fuente: el complemento empieza en e.
    mapa = [{"source_start": 0, "source_end": 1}]
    eliminadas = f.lineas_eliminadas(bronce, mapa, [f.clave_mobiliario(cabecera)])
    assert eliminadas[0]["texto"] == "epartamento Administrativo"
    assert eliminadas[0]["mobiliario"]
    assert [x["texto"] for x in eliminadas if not x["mobiliario"]] == ["contenido perdido"] * 3


@pytest.mark.parametrize("texto", ["1234", "1.234", "12,5", "1.234,56"])
def test_cortes_en_digitos_y_separadores(texto):
    resultado = f.cortes_delicados(texto, [0, *range(1, len(texto)), len(texto), 1])
    assert resultado["gold_cortes_numeros"] == len(texto) - 1
    assert resultado["gold_cortes_articulos"] == 0


@pytest.mark.parametrize("etiqueta", ["Artículo", "ARTÍCULO", "Art.", "art."])
def test_cortes_entre_articulo_y_numero(etiqueta):
    texto = etiqueta + " \n 23 texto"
    inicio, fin = len(etiqueta), texto.index("2")
    resultado = f.cortes_delicados(texto, [*range(inicio, fin + 1), inicio])
    assert resultado["gold_cortes_articulos"] == fin - inicio + 1
    assert f.cortes_delicados(texto, [1, len(texto) - 1])["gold_cortes_articulos"] == 0


def test_cuasi_duplicados_ignoran_adyacentes_y_cuerpos_sin_shingles():
    cuerpo = "uno dos tres cuatro cinco seis siete ocho nueve diez"
    assert f.cuasi_duplicados([cuerpo, cuerpo]) == 0
    assert f.cuasi_duplicados([cuerpo, cuerpo, cuerpo]) == 1
    assert f.cuasi_duplicados([cuerpo, "otro texto distinto", cuerpo.upper()]) == 1
    assert f.cuasi_duplicados(["uno dos", "otro", "uno dos"]) == 0
    assert f.cuasi_duplicados([cuerpo, "otro", "uno dos tres cuatro cinco seis diferente"]) == 0


def test_cuasi_duplicados_umbral_jaccard_inclusivo():
    cuerpo = " ".join(f"palabra{i}" for i in range(49))
    # 45 shingles comunes / 50 en la unión = exactamente 0,9.
    assert f.cuasi_duplicados([cuerpo, "intermedio", cuerpo + " a b c d e"]) == 1
    assert f.cuasi_duplicados([cuerpo, "intermedio", cuerpo + " a b c d e f"]) == 0


@pytest.mark.parametrize(
    ("cer", "color"),
    [
        (0, "verde"),
        (0.004599999, "verde"),
        (0.0046, "no distinguible de U"),
        (0.015399999, "no distinguible de U"),
        (0.0154, "amarillo"),
        (0.03, "amarillo"),
        (0.03000001, "rojo"),
        (None, "sin evaluar"),
    ],
)
def test_bordes_veredicto(cer, color):
    assert f.veredicto(cer)[0] == color


@pytest.mark.parametrize(
    ("parametros", "color", "factor"),
    [
        ({"cobertura": 0.99}, "verde", ""),
        ({"cobertura": 0.989999}, "rojo", "cobertura gold"),
        ({"perdida_otra": 0.02}, "verde", ""),
        ({"perdida_otra": 0.020001}, "amarillo", "pérdida silver otra"),
        ({"perdida_otra": 0.05}, "amarillo", "pérdida silver otra"),
        ({"perdida_otra": 0.050001}, "rojo", "pérdida silver otra"),
        ({"recall_critico": 0.90}, "verde", ""),
        ({"recall_critico": 0.89999}, "amarillo", "recall crítico"),
        ({"cobertura": 0.98, "perdida_otra": 0.06}, "rojo", "cobertura gold"),
    ],
)
def test_degradaciones_y_bordes(parametros, color, factor):
    obtenido, motivo = f.veredicto(0.001, **parametros)
    assert obtenido == color
    assert factor in motivo


def test_degradaciones_nunca_mejoran_color():
    assert f.veredicto(0.04, perdida_otra=0.03, recall_critico=0.8)[0] == "rojo"
    assert f.veredicto(0.01, perdida_otra=0.03)[0] == "amarillo"
    assert f.veredicto(0.02, perdida_otra=0.06)[0] == "rojo"


def chunk(texto, inicio, fin, *, cuerpo=None):
    return {
        "page_content": "Cabecera\n\n" + (texto[inicio:fin] if cuerpo is None else cuerpo),
        "metadata": {"header": "Cabecera", "clean_start": inicio, "clean_end": fin},
    }


def test_gold_cuerpo_real_cobertura_y_solape_independientes():
    texto = "Artículo 12. Un texto de prueba con palabras."
    resultado, unidos = f.analizar_gold(
        texto,
        [
            chunk(texto, 0, 20),
            chunk(texto, 10, len(texto)),
            chunk(texto, 10, len(texto), cuerpo="alterado"),
        ],
    )
    assert unidos == [(0, len(texto))]
    assert resultado["gold_cobertura_silver"] == 1
    assert resultado["gold_discrepancias_cuerpo"] == 1
    assert resultado["gold_numero_chunks"] == 3
    assert resultado["gold_chunks_cortos"] == 3
    assert resultado["gold_duplicados_exactos"] == 0
    assert (
        f.analizar_gold(texto, [chunk(texto, 0, 20), chunk(texto, 0, 20)])[0][
            "gold_duplicados_exactos"
        ]
        == 1
    )


def test_agregado_suma_ediciones_en_lugar_de_promediar_cer():
    paginas = [f.evaluar_pagina("x", "a"), f.evaluar_pagina("abcdefghi", "abcdefghi")]
    resumen = f.sumar_metricas(paginas)
    assert resumen["cer"] == 0.1
    assert resumen["recuperacion"] == 0.5


def test_alertas_ocr_no_inventan_cer_en_excluidas_ni_confianza():
    extraccion = {
        "ocr_pages": [1, 2, 3, 4],
        "ocr_failed_pages": [5],
        "ocr_confidence": {"1": 95, "2": 96, "3": 90, "4": None},
    }
    filas = [
        {"pagina": p, "cer": cer, "tipo_pagina": "OCR"}
        for p, cer in [(1, 0.04), (2, 0.04), (4, 0.04), (5, 0)]
    ]
    resultado = f.alertas_ocr(extraccion, filas)
    assert resultado["ocr_aciertos"] == 1
    assert resultado["ocr_fallos"] == 2
    assert resultado["ocr_precision_alertas"] == 1
    assert resultado["ocr_sensibilidad"] == pytest.approx(1 / 3)
    assert resultado["ocr_paginas_sin_confianza"] == 2
    assert resultado["ocr_alertas_sin_u_evaluable"] == 1
    assert resultado["ocr_fraccion_alertadas"] == 2 / 5


@pytest.mark.parametrize("alteracion_gold", [None, "cuerpo", "cabecera"])
@pytest.mark.parametrize("con_mobiliario", [False, True])
def test_documento_excluye_paginas_u_en_todas_las_comparaciones(
    tmp_path, monkeypatch, con_mobiliario, alteracion_gold
):
    doc_id = "a" * 64
    doc = {"slug": "sintetico", "sha256": doc_id, "categoria": "normativa", "paginas": "2"}
    cabecera = "Cabecera institucional\n" if con_mobiliario else ""
    bronce = cabecera + "Artículo 12 texto\n\f\nsecreto tabla"
    silver = "Artículo 12 texto\n\nsecreto tabla"
    inicio = silver.index("secreto")
    for capa in ("bronze", "silver", "gold"):
        (tmp_path / capa).mkdir()
    (tmp_path / "bronze" / (doc_id + ".txt")).write_text(bronce, encoding="utf-8", newline="")
    (tmp_path / "bronze" / (doc_id + ".extraction.json")).write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "sha256": doc_id,
                "chars_per_page": [15, 12],
                "ocr_pages": [2],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silver" / (doc_id + ".txt")).write_text(silver, encoding="utf-8", newline="")
    contexto = {
        "cleaned": {
            "text": silver,
            "removed_furniture_keys": [f.clave_mobiliario(cabecera)] if con_mobiliario else [],
            "offset_map": [{"source_start": len(cabecera), "source_end": len(bronce)}],
            "pages": [
                {"page": 1, "clean_start": 0, "clean_end": inicio - 2},
                {"page": 2, "clean_start": inicio, "clean_end": len(silver)},
            ],
        }
    }
    (tmp_path / "silver" / (doc_id + ".context.json")).write_text(
        json.dumps(contexto), encoding="utf-8"
    )
    gold = chunk(
        silver, 0, len(silver), cuerpo="mar abierto" if alteracion_gold == "cuerpo" else None
    )
    if alteracion_gold == "cabecera":
        gold["page_content"] = "otra cabecera\n\n" + silver
    (tmp_path / "gold" / (doc_id + ".jsonl")).write_text(json.dumps(gold), encoding="utf-8")
    u = tmp_path / "referencia.md"
    u.write_text(
        f"<!-- página 1 -->{cabecera}Artículo 12 texto<!-- página 2 --><table><tr><td>distinto</td></tr></table>",
        encoding="utf-8",
    )
    monkeypatch.setattr(f.v, "rutas_documento", lambda _: (u, None, None))
    monkeypatch.setattr(f, "REPETICIONES", 10)
    fila, paginas, eliminadas = f.evaluar_documento(doc, tmp_path, "ajuste", {("sintetico", 2)})
    assert fila["bronce_total_cer"] == 0
    assert fila["perdida_silver_otra"] == (0.4 if con_mobiliario else 0)
    assert fila["silver_perdida"] == fila["perdida_silver_otra"]
    assert (fila["silver_perdida"] > 0.05) == con_mobiliario
    assert fila["veredicto_final"] == ("rojo" if con_mobiliario or alteracion_gold else "verde")
    assert fila["silver_ruido"] == 0
    assert fila["gold_recuperacion_u"] == (0 if alteracion_gold else (0.6 if con_mobiliario else 1))
    assert fila["gold_cobertura_silver"] == 1
    assert fila["gold_cobertura_efectiva_silver"] == (0 if alteracion_gold else 1)
    if alteracion_gold:
        assert fila["motivo_principal"] == (
            "gold: cuerpo ≠ silver" if alteracion_gold == "cuerpo" else "gold: cabecera inválida"
        )
    for k, ruta in {
        "huella_u": u,
        "huella_bronce": tmp_path / "bronze" / (doc_id + ".txt"),
        "huella_gold": tmp_path / "gold" / (doc_id + ".jsonl"),
    }.items():
        assert fila[k] == f.hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert fila["tiene_tablas"] == "no"
    assert fila["tabla_paginas"] == 0
    assert fila["bronce_ocr_paginas"] == 0
    assert paginas[1]["estado"] == "excluida de U"
    assert "cer" not in paginas[1]
    assert [x["texto"] for x in eliminadas] == ([cabecera.strip()] if con_mobiliario else [])
    assert all(x["candidato_rechazado"] for x in eliminadas)


def test_md_informa_cambios_de_bytes_sin_confundirlos_con_ocr(tmp_path):
    original = tmp_path / "original.md"
    original.write_bytes(b"\xef\xbb\xbfTexto\r\nfinal")
    doc_id = f.hashlib.sha256(original.read_bytes()).hexdigest()
    raiz = tmp_path / "capas"
    (raiz / "bronze").mkdir(parents=True)
    (raiz / "bronze" / (doc_id + ".extraction.json")).write_text(
        json.dumps({"doc_id": doc_id, "original_file": doc_id + ".md"}),
        encoding="utf-8",
    )
    (raiz / "bronze" / (doc_id + ".txt")).write_bytes(b"Texto\nfinal")
    fila = f.evaluar_md(raiz, [original])[0]
    assert fila["bronce_identico_bytes"] == "no"
    assert fila["original_sha256_coincide"] == "sí"
    assert fila["cambio_bronce"] == "BOM/NFC/saltos de línea/separadores de página"
    assert fila["referencia"] == "SIN referencia de OCR"


@pytest.mark.parametrize(
    ("paginas", "apariciones", "aceptado"),
    [(2, 2, False), (10, 2, False), (10, 3, True), (11, 3, False), (11, 4, True)],
)
def test_mobiliario_umbral_de_paginas_y_treinta_por_ciento(paginas, apariciones, aceptado):
    clave = f.clave_mobiliario("Institución calle 99")
    bronce = "\n\f\n".join(
        f"Institución calle {i}\ncontenido" if i < apariciones else "contenido"
        for i in range(paginas)
    )
    assert (clave in f.mobiliario_independiente(bronce, [clave])) == aceptado
    # La repetición sin candidatura no basta.
    assert f.mobiliario_independiente(bronce, []) == set()


@pytest.mark.parametrize(
    "marcador",
    [
        "Artículo",
        "ART.",
        "Parágrafo",
        "Considerando",
        "Resuelve",
        "Decreta",
        "Capítulo",
        "Título",
        "Numeral",
        "Literal",
    ],
)
def test_marcadores_juridicos_repetidos_en_margenes_son_perdida_otra(marcador):
    linea = f"{marcador} 7 protege costa"
    bronce = "\n\f\n".join([linea + "\nconservado"] * 3)
    resultado = f.perdida_silver(
        bronce,
        bronce,
        "conservado\n" * 3,
        eliminadas=f.lineas_eliminadas(bronce, [], [f.clave_mobiliario(linea)]),
    )
    assert resultado["silver_palabras_perdidas_mobiliario"] == 0
    assert resultado["silver_palabras_perdidas_otras"] > 0
    assert all(
        x["candidato_rechazado"]
        for x in f.lineas_eliminadas(bronce, [], [f.clave_mobiliario(linea)])
        if x["texto"] == linea
    )


@pytest.mark.parametrize("posicion", [0, 2, 3, 4, 6])
def test_solo_tres_lineas_no_vacias_de_cada_margen(posicion):
    lineas = [f"texto {i}" for i in range(7)]
    lineas[posicion] = "Institución"
    # Blancos no consumen puestos y dos márgenes no duplican el voto de página.
    bronce = "\n\f\n".join(["\n\n".join(lineas)] * 3)
    assert ("institución" in f.mobiliario_independiente(bronce, ["institución"])) == (posicion != 3)
    assert f.mobiliario_independiente("Institución\nInstitución", ["institución"]) == set()


@pytest.mark.parametrize("folio", ["Página 2 de 30", "PÁGINA 12 DE 99"])
def test_folio_pagina_n_de_m_en_margen_no_necesita_repeticion(folio):
    resultado = f.perdida_silver(
        folio + "\ncosta",
        folio + "\ncosta",
        "costa",
        eliminadas=f.lineas_eliminadas(folio + "\ncosta", []),
    )
    assert resultado["perdida_silver_otra"] == 0
    assert f.es_folio(folio, 1, True, set())
    assert not f.es_folio(folio, 1, False, set())
    assert not f.es_folio(folio + " Artículo 7", 1, True, set())


def test_folio_numerico_exige_secuencia_de_paginacion():
    # Folios 11, 12, 13 en páginas 1-3: desplazamiento constante +10 en ≥ 2 páginas.
    bronce = "\n\f\n".join(f"costa {i}\n{10 + i}" for i in range(1, 4))
    silver = "\n\n".join(f"costa {i}" for i in range(1, 4))
    resultado = f.perdida_silver(bronce, bronce, silver, eliminadas=f.lineas_eliminadas(bronce, []))
    assert resultado["perdida_silver_otra"] == 0
    assert resultado["perdida_silver_mobiliario"] > 0


def test_importes_eliminados_al_final_de_pagina_no_son_folios():
    # Regresión: importes 100 y 200 eliminados no siguen la paginación → pérdida otra.
    bronce = "Total a pagar\n100\n\f\nTotal a pagar\n200"
    silver = "Total a pagar\n\nTotal a pagar"
    resultado = f.perdida_silver(bronce, bronce, silver, eliminadas=f.lineas_eliminadas(bronce, []))
    assert resultado["perdida_silver_mobiliario"] == 0
    assert resultado["perdida_silver_otra"] > 0


def test_pagina_excluida_con_articulo_borrado_impide_verde():
    # Regresión: la página 2 está excluida de U y silver borra su artículo entero.
    paginas = ["Artículo 1. Texto conservado.", "Artículo 2. Texto borrado por silver."]
    bronce = "\n\f\n".join(paginas)
    mapa = [{"source_start": 0, "source_end": len(paginas[0])}]
    resultado = f.perdida_paginas_sin_u(paginas, f.lineas_eliminadas(bronce, mapa), {1})
    assert resultado["paginas_sin_u_estado"] == "evaluada"
    assert resultado["paginas_sin_u_perdida_silver"] == 1.0
    color, motivo = f.veredicto(
        0.0, perdida_sin_u=resultado["paginas_sin_u_perdida_silver"], estado_sin_u="evaluada"
    )
    assert color == "rojo"
    assert "páginas sin U" in motivo


def test_pagina_excluida_no_evaluada_impide_verde_y_auditoria_lo_respeta():
    assert f.veredicto(0.0, estado_sin_u="no evaluada") == (
        "no distinguible de U",
        "páginas sin U no verificadas",
    )
    assert f.veredicto(0.0, estado_sin_u="sin páginas") == ("verde", "")


def test_copias_md_identicas_no_son_ambiguas(tmp_path):
    contenido = b"Decreto 2324 de 1984"
    a, b = tmp_path / "a" / "x.md", tmp_path / "b" / "x.md"
    for p in (a, b):
        p.parent.mkdir()
        p.write_bytes(contenido)
    doc_id = __import__("hashlib").sha256(contenido).hexdigest()
    assert len(f.buscar_original_md("normativa/x.md", doc_id, [a, b])) == 1
    b.write_bytes(contenido + b" distinto")
    assert len(f.buscar_original_md("normativa/x.md", "f" * 64, [a, b])) == 2


def test_frecuencia_mobiliario_usa_documento_completo_aunque_u_excluya_paginas():
    bronce = "\n\f\n".join(["Institución\ncontenido"] * 10)
    resultado = f.perdida_silver(
        "Institución contenido",
        "Institución\ncontenido",
        "contenido",
        eliminadas=[
            x for x in f.lineas_eliminadas(bronce, [], ["institución"]) if x["pagina"] == 1
        ],
    )
    assert resultado["perdida_silver_otra"] == 0
    assert resultado["perdida_silver_mobiliario"] == 0.5


def test_gold_no_recupera_u_desde_offsets_de_cuerpo_alterado():
    silver = "costa protegida"
    chunks = [chunk(silver, 0, len(silver), cuerpo="mar abierto")]
    gold, _ = f.analizar_gold(silver, chunks)
    assert gold["gold_cobertura_declarada_silver"] == 1
    assert gold["gold_cobertura_efectiva_silver"] == 0
    texto = f.reconstruir_gold(silver, chunks)
    assert texto.strip() == "mar abierto"
    assert sum((f.palabras(silver) & f.palabras(texto)).values()) == 0
    assert f.veredicto(0, gold_discrepancias_cuerpo=gold["gold_discrepancias_cuerpo"]) == (
        "rojo",
        "gold: cuerpo ≠ silver",
    )


def test_gold_deduplica_solo_cuerpos_coincidentes_sin_cortar_palabras():
    silver = "costa protegida"
    chunks = [
        chunk(silver, 0, 8),
        chunk(silver, 3, len(silver)),
        chunk(silver, 0, len(silver), cuerpo="mar abierto"),
        chunk(silver, 0, len(silver), cuerpo="mar abierto"),
    ]
    assert f.reconstruir_gold(silver, chunks) == silver + "\n\nmar abierto\n\nmar abierto"
    gold, _ = f.analizar_gold(silver, chunks)
    assert gold["gold_cobertura_efectiva_silver"] == 1
    assert gold["gold_discrepancias_cuerpo"] == 2


def test_gold_cabecera_invalida_impone_rojo_incluso_con_cer_rojo():
    silver = "costa"
    invalido = chunk(silver, 0, len(silver))
    invalido["page_content"] = "otra cabecera\n\n" + silver
    gold, _ = f.analizar_gold(silver, [invalido])
    assert gold["gold_cobertura_efectiva_silver"] == 0
    assert f.veredicto(
        0.08,
        gold_discrepancias_cuerpo=gold["gold_discrepancias_cuerpo"],
        gold_cabeceras_invalidas=gold["gold_cabeceras_invalidas"],
    ) == ("rojo", "gold: cabecera inválida")


def test_gold_excluye_paginas_sin_recortar_discrepantes_por_offsets_falsos():
    silver = "costa\n\nsecreto"
    chunks = [chunk(silver, 0, 5), chunk(silver, 7, len(silver), cuerpo="secreto alterado")]
    assert f.reconstruir_gold(silver, chunks, [(0, 5)]) == "costa"
    assert (
        f.reconstruir_gold(silver, [chunk(silver, 0, len(silver), cuerpo="secreto")], [(0, 5)])
        == ""
    )


def test_gold_discrepante_entre_paginas_evaluables_no_se_pierde_por_separadores():
    silver = "costa\n\nprotegida"
    chunks = [chunk(silver, 0, len(silver), cuerpo="mar abierto")]
    assert f.reconstruir_gold(silver, chunks, [(0, 5), (7, len(silver))]).strip() == "mar abierto"


def test_gold_discrepante_con_offset_vacio_conserva_su_texto_real():
    assert (
        f.reconstruir_gold("costa", [chunk("costa", 0, 0, cuerpo="mar abierto")]).strip()
        == "mar abierto"
    )


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        *[({k: "b" * 64}, "huellas") for k in f.HUELLAS_AUDITORIA],
        *[({k: ""}, "huellas") for k in f.HUELLAS_AUDITORIA],
        ({"veredicto_automatico": "sin evaluar"}, "incompleta"),
        ({"capas_faltantes": ["silver"]}, "incompleta"),
        ({"paginas_sin_u": [2]}, "incompleta"),
        ({"gold_cobertura_silver": None}, "cobertura"),
    ],
)
def test_auditoria_no_oculta_capas_modificadas_incompletas_o_gold_integro(tmp_path, cambio, motivo):
    ruta = tmp_path / "auditoria.csv"
    escribir_auditoria(ruta, [["922e", "verde", "U", "revisión anterior"]])
    fila = {
        "slug": "doc_922e",
        "veredicto_automatico": "rojo",
        **dict.fromkeys(f.HUELLAS_AUDITORIA, "a" * 64),
        "gold_cobertura_silver": 1,
        "gold_cobertura_efectiva_silver": 1,
        **cambio,
    }
    f.aplicar_auditoria([fila], f.cargar_auditoria(ruta, [fila]))
    assert fila["veredicto_final"] == fila["veredicto_automatico"]
    assert fila["estado_auditoria"].startswith("no aplicable: ")
    assert motivo in fila["estado_auditoria"]
    assert fila["huella_u"] == cambio.get("huella_u", "a" * 64)


def test_informe_lista_candidatos_rechazados_fuera_del_top_cinco_y_sin_limite():
    documentos = [{"slug": f"doc{i}", "perdida_silver_otra": (6 - i) / 10} for i in range(6)]
    eliminadas = {d["slug"]: [] for d in documentos}
    eliminadas["doc5"] = [
        {
            "pagina": 1,
            "linea": i + 1,
            "inicio": i * 10,
            "fin": (i + 1) * 10,
            "texto": f"Artículo rechazado {i}",
            "candidato_rechazado": True,
        }
        for i in range(20)
    ]
    texto = f.informe_lineas_eliminadas(documentos, eliminadas)
    assert "### doc5" in texto
    assert texto.count("Candidato rechazado;") == 20
    assert "Artículo rechazado 19" in texto
    assert "tres primeras" in texto and "30 %" in texto


def test_cabecera_conservada_no_exonera_la_misma_expresion_borrada_del_cuerpo():
    cabecera = "Ministerio de Defensa"
    pagina = cabecera + "\nSe informa al Ministerio de Defensa sobre costa"
    bronce = "\n\f\n".join([pagina] * 3)
    borrados = []
    for inicio in range(0, len(bronce), len(pagina) + 3):
        a = inicio + pagina.index(cabecera, len(cabecera))
        borrados.append((a, a + len(cabecera)))
    cubiertos = f.complemento(borrados, len(bronce))
    mapa = [{"source_start": a, "source_end": b} for a, b in cubiertos]
    eliminadas = f.lineas_eliminadas(bronce, mapa, [f.clave_mobiliario(cabecera)])
    assert len(eliminadas) == 3 and all(not x["mobiliario"] for x in eliminadas)
    resultado = f.perdida_silver(
        bronce, bronce, f.texto_tramos(bronce, cubiertos), eliminadas=eliminadas
    )
    assert resultado["silver_palabras_perdidas_mobiliario"] == 0
    assert resultado["silver_palabras_perdidas_otras"] == 9


def test_mobiliario_parcial_solo_exonera_las_ocurrencias_realmente_eliminadas():
    pagina = "Ministerio de Defensa\nActuación del Ministerio de Defensa"
    bronce = "\n\f\n".join([pagina] * 3)
    # Se borra solo Ministerio en las cabeceras y Defensa en el cuerpo.
    borrados = []
    for inicio in range(0, len(bronce), len(pagina) + 3):
        borrados.extend(
            [
                (inicio, inicio + len("Ministerio")),
                (inicio + pagina.rindex("Defensa"), inicio + len(pagina)),
            ]
        )
    cubiertos = f.complemento(borrados, len(bronce))
    eliminadas = f.lineas_eliminadas(
        bronce,
        [{"source_start": a, "source_end": b} for a, b in cubiertos],
        ["ministerio de defensa"],
    )
    resultado = f.perdida_silver(
        bronce, bronce, f.texto_tramos(bronce, cubiertos), eliminadas=eliminadas
    )
    assert resultado["silver_palabras_perdidas_mobiliario"] == 3
    assert resultado["silver_palabras_perdidas_otras"] == 3


@pytest.mark.parametrize(
    ("cambio", "color"),
    [
        ({"perdida_silver_otra": 0.020001}, "amarillo"),
        ({"perdida_silver_otra": 0.050001}, "rojo"),
        ({"gold_cobertura_silver": 0.989999}, "rojo"),
        ({"gold_cobertura_efectiva_silver": 0.98}, "rojo"),
        ({"gold_discrepancias_cuerpo": 1}, "rojo"),
        ({"gold_cabeceras_invalidas": 1}, "rojo"),
    ],
)
def test_auditoria_favorable_reimpone_puertas_silver_y_gold(cambio, color):
    fila = {
        "slug": "doc_922e",
        "veredicto_automatico": color,
        **dict.fromkeys(f.HUELLAS_AUDITORIA, "a" * 64),
        "gold_cobertura_silver": 1,
        "gold_cobertura_efectiva_silver": 1,
        **cambio,
    }
    revision = {"veredicto_auditado": "verde", **dict.fromkeys(f.HUELLAS_AUDITORIA, "a" * 64)}
    f.aplicar_auditoria([fila], {fila["slug"]: revision})
    assert fila["estado_auditoria"] == "aplicada"
    assert fila["veredicto_final"] == color
    assert fila["motivo_principal"]


def test_sensibilidad_grado_usa_las_capas_seleccionadas(tmp_path, monkeypatch):
    doc_id = "a" * 64
    doc = {"slug": "sintetico", "sha256": doc_id, "categoria": "normativa", "paginas": "1"}
    u = tmp_path / "u.md"
    u.write_text("<!-- página 1 -->Artículo 1° costa", encoding="utf-8")
    monkeypatch.setattr(f.v, "rutas_documento", lambda _: (u, None, None))
    monkeypatch.setattr(f, "REPETICIONES", 10)
    resultados = []
    for corrida, texto in [("runA", "Artículo 1º costa"), ("runB", "Artículo 1° costa")]:
        raiz = tmp_path / corrida
        (raiz / "bronze").mkdir(parents=True)
        (raiz / "bronze" / (doc_id + ".txt")).write_text(texto, encoding="utf-8")
        (raiz / "bronze" / (doc_id + ".extraction.json")).write_text(
            json.dumps({"doc_id": doc_id, "sha256": doc_id, "chars_per_page": [len(texto)]}),
            encoding="utf-8",
        )
        fila, paginas, _ = f.evaluar_documento(doc, raiz, "ajuste", set())
        resultados.append(f.sensibilidad_grado([fila], paginas))
        assert resultados[-1]["_corpus"]["cer"] == fila["bronce_total_cer"]
    a, b = resultados
    assert a["_corpus"]["cer"] > 0
    assert b["_corpus"]["cer"] == 0
    assert a["_corpus"]["cer_grado_unificado"] == b["_corpus"]["cer_grado_unificado"] == 0
    assert a["sintetico"]["huella_bronce"] != b["sintetico"]["huella_bronce"]


def test_veredicto_aplica_la_degradacion_mas_grave():
    # Revisión: pérdida silver amarilla y pérdida en páginas sin U roja a la vez.
    color, motivo = f.veredicto(0.0, perdida_otra=0.03, perdida_sin_u=0.90, estado_sin_u="evaluada")
    assert color == "rojo"
    assert "páginas sin U" in motivo
