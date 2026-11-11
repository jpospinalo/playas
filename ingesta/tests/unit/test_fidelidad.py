"""Pruebas sintéticas: no se accede a transcripciones ciegas ni a data/."""

from __future__ import annotations

import csv
import importlib.util
import itertools
import json
import random
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "benchmarks" / "fidelidad"


def importar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, BENCH / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


a = importar("anclas")
c = importar("comparar")
e = importar("calcular_error_real")


def test_tsv_tesseract_con_comilla_literal_no_fusiona_filas_ni_coordenadas():
    preparar = importar("preparar_fuentes")
    tsv = (
        "left\ttop\twidth\theight\ttext\n"
        '10\t20\t6\t8\t"\n'
        "30\t40\t12\t16\tArtículo\n"
        '50\t60\t4\t8\t"costa\n'
        "70\t80\t10\t12\tfinal\n"
    )
    palabras = preparar.palabras_tsv(tsv)
    assert [p["texto"] for p in palabras] == ['"', "Artículo", '"costa', "final"]
    assert [p["bbox"] for p in palabras] == [
        [5, 10, 8, 14],
        [15, 20, 21, 28],
        [25, 30, 27, 34],
        [35, 40, 40, 46],
    ]


def distancia_lenta(a, b):
    anterior = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        fila = [i]
        for j, y in enumerate(b, 1):
            fila.append(min(fila[-1] + 1, anterior[j] + 1, anterior[j - 1] + (x != y)))
        anterior = fila
    return anterior[-1]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("A\u0301RBOL  Niñez 123,45!", "árbol niñez 123,45!"),
        ("protec-\n ción", "protección"),
        ("23-\n42", "23- 42"),
        ("## Título\n**Artículo 3**\n__Ley__", "título artículo 3 ley"),
        ("|---|:---:|\n| a | b |", "a b"),
        ("Colombia | SUIN", "colombia suin"),
        ("de 2008³ y nota¹²", "de 2008 3 y nota 12"),
        ("![alt](archivo.png)\n<img src='x'>\nTexto", "texto"),
        ("Página 1 de 3\nPág. 2\nPage 3 of 4\n\fTexto", "texto"),
        ("<!-- page 9 -->\n[[página 3]]\n4\nArt. 4.", "4 art. 4."),
        ("a-b: 1/2; ¿sí? [enlace](x) *texto*", "a-b: 1/2; ¿sí? [enlace](x) *texto*"),
    ],
)
def test_normalizacion_comun(entrada, esperado):
    assert c.normalizar(entrada) == esperado
    assert c.normalizar(c.normalizar(entrada)) == esperado


def test_distancia_exhaustiva_con_oraculo_independiente():
    cadenas = ["".join(s) for n in range(4) for s in itertools.product("ab", repeat=n)]
    for a, b in itertools.product(cadenas, repeat=2):
        assert c.distancia(a, b) == distancia_lenta(a, b)


def test_distancia_aleatoria_unicode_y_palabras():
    rng = random.Random(13)
    for _ in range(100):
        a = rng.choices(["niñez", "7", "sí", "."], k=rng.randrange(30))
        b = rng.choices(["niñez", "7", "sí", "."], k=rng.randrange(30))
        assert c.distancia(a, b) == distancia_lenta(a, b)
        assert c.distancia(" ".join(a), " ".join(b)) == distancia_lenta(" ".join(a), " ".join(b))


def test_metricas_referencia_explicita_multiconjunto():
    m = c.metricas("a a c", "a b")
    assert m["wer"] == 1
    assert m["recuperacion"] == 0.5
    assert m["precision"] == 1 / 3
    assert c.metricas("a b", "a a c")["wer"] == 2 / 3


def test_referencia_vacia_no_oculta_inserciones():
    m = c.metricas("extra", "")
    assert m["cer"] is None and m["wer"] is None
    assert m["ediciones_caracteres"] == 5
    assert m["ediciones_palabras"] == 1


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("a b c", "a x c"),
        ("a b", "x a b y"),
        ("a b c", "a c"),
        ("", "x"),
        ("x", ""),
        ("a a b a", "a b a a"),
        ("", ""),
    ],
)
def test_alineacion_optima_y_reconstruccion(a, b):
    ref, hip = a.split(), b.split()
    ops = c.alinear(ref, hip)
    assert sum(op[0] != "igual" for op in ops) == c.distancia(ref, hip)
    assert [p for op in ops for p in ref[op[1] : op[2]]] == ref
    assert [p for op in ops for p in hip[op[3] : op[4]]] == hip


def test_proyeccion_insertos_y_bordes():
    ops = c.alinear("a b".split(), "x a b y".split())
    assert c.proyectar(ops, 0, 1) == (0, 2)
    assert c.proyectar(ops, 2, 2) == (3, 4)


@pytest.mark.parametrize(
    ("categoria", "texto", "n"),
    [
        ("radicado", "47001-23-31-000-2011-00842-01 y 47001-2332-000-2011-08425-02", 2),
        ("fecha", "2 de marzo de 2020 y 03/04/2021 y 2022-03-04", 3),
        ("articulo", "Artículo 4 Art. 15", 2),
        ("ley", "Ley 99 de 1993", 1),
        ("decreto", "Decreto 1120 de 2013", 1),
        ("numero", "3 3 12,5", 3),
    ],
)
def test_criticos_regex(categoria, texto, n):
    assert sum(c.criticos(texto)[categoria].values()) == n


def test_criticos_multiconjunto_y_cambios():
    filas = c.comparar_criticos("Artículo 5. 10", "Artículo 4. 10 10")
    articulo = next(f for f in filas if f["categoria"] == "articulo")
    numero = next(f for f in filas if f["categoria"] == "numero")
    assert articulo["recall"] == 0
    assert articulo["faltantes"] == ["artículo 4"]
    assert articulo["extras_o_cambiados"] == ["artículo 5"]
    assert numero["recuperados"] == 1
    assert numero["total_ref"] == 3


def test_consenso_respaldado():
    partes = c.consenso({"S": "a 4 b", "A": "a 4 b", "V": "a 5 b"}, "S")
    assert len(partes) == 1
    assert partes[0]["clase"] == "respaldado"
    assert partes[0]["n_coinciden_objetivo"] == 1
    assert partes[0]["critico"]


def test_consenso_en_disputa_con_apoyo():
    partes = c.consenso({"S": "a 4 b", "A": "a 5 b", "V": "a 5 b", "C1": "a 4 b"}, "S")
    assert partes[0]["clase"] == "en_disputa"
    assert partes[0]["grupos_contra"] == [["A", "V"]]
    assert partes[0]["caracteres_objetivo"] == 1


def test_consenso_indeterminado_y_fuentes_ausentes():
    partes = c.consenso({"S": "a 4 b", "V": "a 5 b"}, "S")
    assert partes[0]["clase"] == "indeterminado"
    assert c.consenso({"S": "a"}, "S") == []


def test_consenso_v_simetrico():
    partes = c.consenso({"S": "a 4 b", "A": "a 4 b", "V": "a 5 b"}, "V")
    assert partes[0]["clase"] == "contradicho_por_consenso"
    assert partes[0]["textos"]["V"] == "5"


def test_consenso_insercion_cero_caracteres():
    partes = c.consenso({"S": "a b", "A": "a b extra", "V": "a b extra"}, "S")
    assert partes[0]["caracteres_objetivo"] == 0
    assert partes[0]["clase"] == "contradicho_por_consenso"


def test_controles_todas_disponibles():
    texto = "uno dos tres cuatro cinco seis siete ocho nueve diez once doce"
    assert len(c.controles({"S": texto, "A": texto, "V": texto})) == 1
    assert not c.controles({"S": texto, "A": "otra lectura"})


def test_bootstrap_micro_determinista_y_extremos():
    filas = [c.metricas("ab", "aa"), c.metricas("x", "xxxxxxxxxx")]
    ic = c.bootstrap(filas)
    assert ic == c.bootstrap(filas)
    assert 0.5 <= ic["cer"][0] <= ic["cer"][1] <= 0.9
    assert c.agregar(filas)["cer"] == 10 / 12
    assert c.bootstrap([]) == {"cer": None, "wer": None}


@pytest.mark.parametrize("tasa", [0.005, 0.01, 0.03])
def test_calibracion_obligatoria_sustituciones(tasa):
    limpio = "El artículo 12 de la Ley 99 de 1993 protege la niñez. " * 200
    alterado, n = c.inyectar(limpio, tasa)
    metrica = c.metricas(alterado, limpio)
    assert abs(metrica["cer"] - tasa) <= 2 / len(c.normalizar(limpio))
    assert n == round(len(c.normalizar(limpio)) * tasa)


def test_calibracion_obligatoria_borrado_numeros():
    limpio = "Artículo 12. Ley 99 de 1993. Decreto 1120 de 2013. 4 de junio de 2020. Radicado 47001-23-31-000-2011-00842-01."
    resultado = c.calibrar([("sintetica", limpio * 20)])
    assert resultado["correcto"]
    prueba = resultado["pruebas"][-1]
    assert prueba["ocurrencias_ref"] > 0
    assert prueba["ocurrencias_recuperadas"] == 0


def test_carga_fuente_sin_listar_directorios(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "iterdir", lambda *a: pytest.fail("No listar fuentes"))
    assert c.cargar_pagina(tmp_path, "S", "d", 1) == (None, "fuente ausente")
    ruta = tmp_path / "fuentes" / "S" / "d" / "001.txt"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("\f", encoding="utf-8")
    assert c.cargar_pagina(tmp_path, "S", "d", 1) == ("\f", "disponible")


def test_integracion_solo_s_a_v_sinteticas(tmp_path):
    seleccion = {"documentos": [{"id": "prueba", "paginas": [1, 2], "tipo_pagina": "digital"}]}
    c.guardar_json(tmp_path / "seleccion.json", seleccion)
    for fuente, texto in (
        ("S", "Artículo 1. texto legal correcto común " * 8),
        ("A", "Artículo 1. texto legal correcto común " * 8),
        ("V", "Artículo 2. texto legal correcto común " * 8),
    ):
        ruta = tmp_path / "fuentes" / fuente / "prueba" / "001.txt"
        ruta.parent.mkdir(parents=True)
        ruta.write_text(texto, encoding="utf-8")
    resultado = c.ejecutar(tmp_path, ["S", "A", "V"], recortes=False)
    assert resultado["filas_metricas"] == 6
    datos = json.loads(
        (tmp_path / "resultados" / "metricas_resumen.json").read_text(encoding="utf-8")
    )
    assert sum(p["estado"] == "fuente ausente" for p in datos["disponibilidad"]) == 3
    with (tmp_path / "resultados" / "desacuerdos.csv").open(
        encoding="utf-8", newline=""
    ) as archivo:
        filas = list(csv.DictReader(archivo))
    for fila in filas:
        fila["quien_acierta"] = "S"
    # También verifica que la selección no duplique intervalos entre S y V.
    assert e.evaluar(filas)["filas_revisadas"] == len(filas)


def fila_revision(**cambios):
    fila = {
        "id": "r1",
        "documento": "d",
        "pagina": "1",
        "tipo_pagina": "digital",
        "tipo": "desacuerdo",
        "texto_S": "artículo 4",
        "texto_A": "artículo 5",
        "texto_V": "artículo 5",
        "fuentes_presentes": "S,A,V",
        "quien_acierta": "A",
        "nota": "",
    }
    return {**fila, **cambios}


def test_error_real_reconstruye_referencia_y_fidelidad():
    resultado = e.evaluar([fila_revision()])
    assert resultado["referencia_verificada_segmentos"][0]["referencia"] == "artículo 5"
    s = next(
        m
        for m in resultado["resumen"]
        if m["fuente"] == "S" and m["tipo"] == "TODOS" and m["tipo_pagina"] == "TODAS"
    )
    assert s["cer"] == 1 / 10
    assert s["wer"] == 0.5
    assert s["fidelidad_1_menos_cer"] == 0.9
    assert s["fidelidad_ic95"] == [0.9, 0.9]


def test_error_real_ninguna_y_error_control():
    resultado = e.evaluar(
        [fila_revision(tipo="control", quien_acierta="ninguna", nota="artículo 6")]
    )
    assert resultado["tasa_error_lineas_control"]["S"]["tasa"] == 1
    assert resultado["controles_todas_fuentes_erradas"] == 1


@pytest.mark.parametrize(
    "cambios",
    [
        {"quien_acierta": "otra"},
        {"quien_acierta": "ninguna"},
        {"quien_acierta": "C1"},
        {"quien_acierta": ""},
        {"tipo": "otro"},
    ],
)
def test_error_real_rechaza_adjudicacion_invalida(cambios):
    with pytest.raises(ValueError):
        e.evaluar([fila_revision(**cambios)])


def test_error_real_incompleto_explicito():
    resultado = e.evaluar(
        [fila_revision(), fila_revision(quien_acierta="")], permitir_incompleto=True
    )
    assert resultado["filas_pendientes"] == 1


def test_error_real_borrado_correcto_referencia_vacia():
    resultado = e.evaluar([fila_revision(texto_A="", quien_acierta="A")])
    s = next(m for m in resultado["resumen"] if m["fuente"] == "S")
    assert s["cer"] is None and s["ediciones_caracteres"] == 10


def test_error_real_rechaza_duplicados():
    fila = fila_revision(rangos=json.dumps({"S": [0, 2], "A": [0, 2], "V": [0, 2]}))
    with pytest.raises(ValueError, match="superpuestos"):
        e.evaluar([fila, fila])


def test_error_real_control_correcto_y_agrupacion_por_pagina():
    resultado = e.evaluar(
        [
            fila_revision(),
            fila_revision(
                id="r2", tipo="control", texto_S="igual", texto_A="igual", texto_V="igual"
            ),
        ]
    )
    assert resultado["tasa_error_lineas_control"]["S"]["tasa"] == 0
    global_s = next(
        m
        for m in resultado["resumen"]
        if m["fuente"] == "S" and m["tipo"] == "TODOS" and m["tipo_pagina"] == "TODAS"
    )
    assert global_s["paginas"] == 1


def test_error_real_ninguna_con_lectura_vacia():
    resultado = e.evaluar([fila_revision(quien_acierta="ninguna", nota="[VACÍO]")])
    assert resultado["referencia_verificada_segmentos"][0]["referencia"] == ""


def test_no_usa_texto_obsoleto_si_pagina_pendiente(tmp_path):
    ruta = tmp_path / "fuentes" / "S" / "d" / "001.txt"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("extracción anterior", encoding="utf-8")
    c.guardar_json(
        ruta.parents[1] / "paginas.json",
        {"paginas": [{"documento": "d", "pagina": 1, "estado": "PENDIENTE"}]},
    )
    assert c.cargar_pagina(tmp_path, "S", "d", 1) == (None, "PENDIENTE")


def test_anclas_v_no_amplian_parrafo_entre_paginas():
    primera = " ".join(f"termino{i}" for i in range(80))
    segunda = " ".join(f"termino{i}" for i in range(80, 160))
    markdown = primera + " " + segunda
    rango1, _ = a.anclas(primera, markdown)
    rango2, _ = a.anclas(segunda, markdown)
    assert rango1 and rango2
    assert rango1[1] <= rango2[0]
    assert "termino80" not in markdown[slice(*rango1)]
    assert "termino79" not in markdown[slice(*rango2)]


def preparar_caso(tmp_path, textos, paginas=(1,)):
    c.guardar_json(
        tmp_path / "seleccion.json",
        {"documentos": [{"id": "d", "paginas": list(paginas), "tipo_pagina": "digital"}]},
    )
    for fuente, texto in textos.items():
        for pagina in paginas:
            ruta = tmp_path / "fuentes" / fuente / "d" / f"{pagina:03d}.txt"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(texto, encoding="utf-8")


def leer_revision(tmp_path):
    with (tmp_path / "resultados" / "desacuerdos.csv").open(
        encoding="utf-8", newline=""
    ) as archivo:
        return list(csv.DictReader(archivo))


@pytest.mark.parametrize("vacio", ["", "\f", "Página 1 de 2"])
def test_disponible_vacia_participa_en_pares_criticos_y_consenso(tmp_path, vacio):
    preparar_caso(tmp_path, {"S": vacio, "A": "artículo 4", "C1": "artículo 4"})
    c.guardar_json(
        tmp_path / "fuentes" / "S" / "paginas.json",
        {"paginas": [{"documento": "d", "pagina": 1, "estado": "disponible"}]},
    )
    assert c.cargar_pagina(tmp_path, "S", "d", 1) == (vacio, "disponible")
    resultado = c.ejecutar(tmp_path, ["S", "A", "C1"], recortes=False)
    assert resultado["filas_metricas"] == 6
    with (tmp_path / "resultados" / "metricas_paginas.csv").open(encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    pares_s = [f for f in filas if f["fuente"] == "S"]
    assert len(pares_s) == 2
    assert all(float(f["cer"]) == float(f["wer"]) == 1 for f in pares_s)
    with (tmp_path / "resultados" / "criticos.csv").open(encoding="utf-8") as archivo:
        articulos = [f for f in csv.DictReader(archivo) if f["categoria"] == "articulo"]
    assert len(articulos) == 2
    assert all(f["recall"] == "0.0" for f in articulos)
    datos = json.loads((tmp_path / "resultados" / "consenso.json").read_text(encoding="utf-8"))
    assert datos["segmentos"][0]["clase"] == "contradicho_por_consenso"
    assert datos["segmentos"][0]["textos"]["S"] == ""


@pytest.mark.parametrize("estado", ["PENDIENTE", "fuente ausente", "no aplica", "solo_documento"])
def test_estado_excluido_no_vota_aunque_haya_texto_obsoleto(tmp_path, estado):
    preparar_caso(tmp_path, {"S": "a 4 b", "A": "a 5 b", "V": "a 5 b"})
    c.guardar_json(
        tmp_path / "fuentes" / "V" / "paginas.json",
        {"paginas": [{"documento": "d", "pagina": 1, "estado": estado}]},
    )
    c.ejecutar(tmp_path, ["S", "A", "V"], recortes=False)
    datos = json.loads((tmp_path / "resultados" / "consenso.json").read_text(encoding="utf-8"))
    assert datos["segmentos"][0]["clase"] == "indeterminado"
    assert datos["paginas"][0]["fuentes_comparadas"] == ["A"]
    assert all(s["objetivo"] != "V" and "V" not in s["textos"] for s in datos["segmentos"])


@pytest.mark.parametrize("texto", ["page 3", "página 7", "<!-- page 9 -->", "---"])
@pytest.mark.parametrize("quien", ["A", "ninguna"])
def test_error_real_no_borra_fragmentos_adjudicados(texto, quien):
    fila = fila_revision(
        texto_S=texto,
        texto_A=texto,
        texto_V="",
        quien_acierta=quien,
        nota=texto.upper() if quien == "ninguna" else "",
    )
    resultado = e.evaluar([fila])
    assert resultado["referencia_verificada_segmentos"][0]["referencia"] == texto
    s = next(m for m in resultado["resumen"] if m["fuente"] == "S")
    v = next(m for m in resultado["resumen"] if m["fuente"] == "V")
    assert s["caracteres_ref"] == len(texto) and s["cer"] == 0
    assert v["cer"] == v["wer"] == 1


def test_control_compara_fragmentos_sin_renormalizar():
    resultado = e.evaluar(
        [fila_revision(tipo="control", texto_S="page 3", texto_A="", quien_acierta="A")]
    )
    assert resultado["tasa_error_lineas_control"]["S"]["tasa"] == 1


@pytest.mark.parametrize("objetivo,otras", [("S", ("A", "V")), ("V", ("S", "A"))])
@pytest.mark.parametrize("visual", [False, True])
def test_consenso_dos_vacios_solo_con_visual(objetivo, otras, visual):
    fuentes = {objetivo: "cabecera", otras[0]: "", "C1" if visual else otras[1]: ""}
    segmento = c.consenso(fuentes, objetivo)[0]
    assert segmento["clase"] == ("contradicho_por_consenso" if visual else "indeterminado")
    assert bool(segmento["grupos_contra"]) == visual


@pytest.mark.parametrize("objetivo", ["S", "V"])
def test_consenso_respaldo_y_contradiccion_siempre_en_disputa(objetivo):
    otro = "V" if objetivo == "S" else "S"
    parte = c.consenso({objetivo: "a x b", otro: "a y b", "A": "a y b", "C2": "a x b"}, objetivo)[0]
    assert parte["clase"] == "en_disputa"
    assert parte["coinciden_objetivo"] == ["C2"]


@pytest.mark.parametrize("objetivo", ["S", "V"])
def test_resumen_dos_porcentajes_provisionales(tmp_path, objetivo):
    otro = "V" if objetivo == "S" else "S"
    preparar_caso(tmp_path, {objetivo: "a x b", otro: "a y b", "A": "a y b", "C1": "a x b"})
    c.ejecutar(tmp_path, ["S", "A", "V", "C1"], recortes=False)
    datos = json.loads((tmp_path / "resultados" / "consenso.json").read_text(encoding="utf-8"))
    for fila in datos["paginas"] + datos["resumen"]:
        if fila["objetivo"] == objetivo and fila["caracteres"]:
            assert fila["porcentaje_PROVISIONAL"] == 0
            assert fila["porcentaje_con_disputa_PROVISIONAL"] == 20
            assert fila["caracteres_en_disputa"] == 1


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("https://ejemplo.test Página 3 de 7", "https://ejemplo.test"),
        ("antes Page 3 of 7 después", "antes después"),
        ("Página 2 de 5 | cuerpo | PAGE 4 OF 8", "cuerpo"),
        ("ver page 3 en el artículo 4", "ver page 3 en el artículo 4"),
    ],
)
def test_marcadores_en_cualquier_posicion(entrada, esperado):
    assert c.normalizar(entrada) == esperado
    assert c.normalizar(esperado) == esperado


def test_controles_sin_solape_en_todas_las_fuentes_con_texto_repetido(tmp_path):
    base = "uno dos tres cuatro cinco seis".split() * 12
    a, v = base.copy(), base.copy()
    a[71:79] = "seis uno dos tres cuatro cinco".split()
    a[49:53] = ["otro"]
    a[18:27] = ["otro"]
    v[37:43] = ["otro"]
    v[64:71] = ["otro"]
    v[62:69] = ["otro"]
    textos = {"S": " ".join(base), "A": " ".join(a), "V": " ".join(v)}
    partes = [
        {"documento": "d", "pagina": 1, **s}
        for objetivo in ("S", "V")
        for s in c.consenso(textos, objetivo)
    ]
    controles = [{"documento": "d", "pagina": 1, **s} for s in c.controles(textos)]
    assert any(c.solapan_segmentos(s, control) for s in partes for control in controles)
    preparar_caso(tmp_path, textos)
    c.ejecutar(tmp_path, ["S", "A", "V"], recortes=False)
    filas = leer_revision(tmp_path)
    assert any(f["tipo"] == "control" for f in filas)
    for fila in filas:
        fila["quien_acierta"] = "S"
    assert e.evaluar(filas)["filas_revisadas"] == len(filas)


@pytest.mark.parametrize(
    "objetivo,clase,critico,textos,esperado",
    [
        ("S", "contradicho_por_consenso", False, {}, "a"),
        ("S", "en_disputa", False, {}, "a"),
        ("S", "indeterminado", False, {}, "a"),
        ("S", "respaldado", True, {"S": "x", "C1": "y"}, "b"),
        ("S", "respaldado", False, {"S": "x", "C2": ""}, "b"),
        ("S", "respaldado", True, {"S": "x", "C1": "x"}, "c"),
        ("V", "respaldado", True, {}, "c"),
        ("V", "contradicho_por_consenso", False, {}, "d"),
        ("V", "en_disputa", False, {}, "d"),
        ("S", "respaldado", False, {"S": "x", "A": "y"}, "e"),
        ("V", "indeterminado", False, {}, "e"),
    ],
)
def test_prioridad_revision(objetivo, clase, critico, textos, esperado):
    assert (
        c.prioridad({"objetivo": objetivo, "clase": clase, "critico": critico, "textos": textos})
        == esperado
    )


def test_agrupacion_vecinos_hasta_tres_palabras_y_orden_estable():
    palabras = {k: "a b c d e f g h i j k l".split() for k in ("S", "A", "V")}

    def segmento(inicio, fin, objetivo="S", clase="respaldado", critico=False):
        return {
            "documento": "d",
            "pagina": 1,
            "objetivo": objetivo,
            "inicio": inicio,
            "fin": fin,
            "clase": clase,
            "critico": critico,
            "rangos": {k: [inicio, fin] for k in palabras},
            "textos": {k: " ".join(v[inicio:fin]) for k, v in palabras.items()},
        }

    entrada = [segmento(0, 1), segmento(4, 5, clase="indeterminado"), segmento(9, 10)]
    salida = c.agrupar_desacuerdos(entrada, {("d", 1): palabras})
    assert salida == c.agrupar_desacuerdos(list(reversed(entrada)), {("d", 1): palabras})
    assert len(salida) == 2
    assert salida[0]["rangos"]["S"] == [0, 5]
    assert salida[0]["textos"]["S"] == "a b c d e"
    assert [f["prioridad"] for f in salida] == ["a", "e"]
    assert salida[0]["clase"] == "indeterminado"


def test_seleccion_cubre_s_prioritarios_y_limite_informa_exceso(tmp_path):
    # Diferencias distantes, sin agrupar: 151 candidatos de nivel a.
    s = []
    a = []
    for i in range(151):
        s.extend([f"dato{i}", "uno", "dos", "tres", "cuatro"])
        a.extend([f"otro{i}", "uno", "dos", "tres", "cuatro"])
    preparar_caso(tmp_path, {"S": " ".join(s), "A": " ".join(a)})
    resultado = c.ejecutar(tmp_path, ["S", "A"], recortes=False)
    assert resultado["desacuerdos"] == 150
    assert resultado["limite_a_b_superado"]
    assert resultado["filas_a_b_fuera"] == 1
    assert resultado["filas_por_prioridad"] == {"a": 150}
    assert resultado["cobertura_segmentos_S"]["indeterminado"] == {"total": 151, "incluidos": 150}
    filas = leer_revision(tmp_path)
    assert all(f["objetivo"] == "S" and f["clase"] == "indeterminado" for f in filas)
    assert [json.loads(f["rangos"])["S"][0] for f in filas] == list(range(0, 750, 5))


def test_seleccion_s_en_disputa_y_veinte_controles_reproducibles(tmp_path):
    textos = {
        "S": "a x b " + "uno dos tres cuatro cinco seis " * 80,
        "A": "a y b " + "uno dos tres cuatro cinco seis " * 80,
        "V": "a y b " + "uno dos tres cuatro cinco seis " * 80,
        "C1": "a x b " + "uno dos tres cuatro cinco seis " * 80,
    }
    preparar_caso(tmp_path, textos)
    resultado = c.ejecutar(tmp_path, list(textos), recortes=False)
    filas = leer_revision(tmp_path)
    assert resultado["controles"] == 20
    assert resultado["todos_S_contradichos_en_disputa_incluidos"]
    assert resultado["cobertura_segmentos_S"]["en_disputa"] == {"total": 1, "incluidos": 1}
    assert filas[0]["prioridad"] == "a" and filas[0]["clase"] == "en_disputa"
    for fila in filas:
        fila["quien_acierta"] = "C1"
    assert e.evaluar(filas)["filas_revisadas"] == len(filas)
    c.ejecutar(tmp_path, list(reversed(textos)), recortes=False)
    repetidas = leer_revision(tmp_path)
    assert [(f["rangos"], f["prioridad"]) for f in repetidas] == [
        (f["rangos"], f["prioridad"]) for f in filas
    ]


def test_seleccion_s_a_b_prevalece_sobre_mas_de_150_diferencias_criticas_de_a(tmp_path):
    palabras = {fuente: [] for fuente in c.FUENTES}
    for i in range(152):
        for fuente in c.FUENTES:
            numero = i + (2000 if fuente == "A" else 1000)
            palabras[fuente].extend([str(numero), "uno", "dos", "tres", "cuatro"])
    # Los dos segmentos prioritarios están después de todo el ruido numérico.
    for fuente in c.FUENTES:
        palabras[fuente].extend(
            [
                "errado" if fuente == "S" else "correcto",
                "uno",
                "dos",
                "tres",
                "cuatro",
                "visual" if fuente == "C1" else "lectura",
            ]
        )
    preparar_caso(tmp_path, {k: " ".join(v) for k, v in palabras.items()})
    resultado = c.ejecutar(tmp_path, list(c.FUENTES), recortes=False)
    assert resultado["desacuerdos"] == 150
    assert resultado["filas_por_prioridad"] == {"a": 1, "b": 1, "c": 148}
    assert resultado["todos_S_contradichos_en_disputa_incluidos"]
    filas = leer_revision(tmp_path)
    assert [f["prioridad"] for f in filas[:2]] == ["a", "b"]
    assert [f["texto_S"] for f in filas[:2]] == ["errado", "lectura"]
    assert [json.loads(f["rangos"])["S"][0] for f in filas[2:]] == list(range(0, 740, 5))
