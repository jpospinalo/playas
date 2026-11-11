"""Pruebas locales sintéticas. No leen U, data/ ni revisiones visuales."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

BASE = Path(__file__).resolve().parents[2] / "benchmarks" / "ocr_referencia"


def importar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, BASE / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


m = importar("metricas")
v = importar("validar_u")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("A\u0301RBOL  Niñez\t123,45!", "árbol niñez 123,45!"),
        ("protec-\n ción", "protección"),
        ("NACIONAL-\nARMANDA", "nacional-armanda"),
        ("jurídico-\nAdministrativo", "jurídico-administrativo"),
        ("anti-\ninflamatorio", "antiinflamatorio"),
        ("23-\n42", "23- 42"),
        (
            "# Título\n**Artículo 3**\n__Ley__ *sí* _no_ ~~tachado~~ `código`",
            "título artículo 3 ley sí no tachado código",
        ),
        ("|---|:---:|\n| a | b |", "a b"),
        ("Colombia | SUIN", "colombia suin"),
        ("de 2008³ y nota¹²", "de 2008 3 y nota 12"),
        ("2008<sup>3</sup> <b>Art.</b> 4", "2008 3 art. 4"),
        (r"nota \( ^{12} \) y ^{3}", "nota 12 y 3"),
        (
            "<table><tr><td>A</td><td>2</td></tr><tr><td>Niñez &amp; mar</td><td>3</td></tr></table>",
            "a 2 niñez & mar 3",
        ),
        ("un<b>ido</b> &lt; 3 &quot;Sí&quot;", 'unido < 3 "sí"'),
        ("![alt](local.png)\n<img src='local'>\nTexto", "texto"),
        ("Página 1 de 3\nPág. 2\nPage 3 of 4\n\fTexto", "texto"),
        ("inicio Página 23 de 50 final", "inicio final"),
        ("<!-- página 1 -->A\f<!-- PÁGINA 2 -->B", "a b"),
        ("3\nArtículo 4.\nArt. 9; Ley 99 de 1993.", "3 artículo 4. art. 9; ley 99 de 1993."),
        ("a-b: 1/2; ¿sí? [enlace](local) *texto*", "a-b: 1/2; ¿sí? enlace texto"),
        ("nombre_archivo a*b 12.345,67 © ", "nombre_archivo a*b 12.345,67 © "),
        ("```texto\ncódigo\n```\n---\n> cita\n- elemento", "código cita elemento"),
        ("## Título ##\n>> cita", "título cita"),
        (
            "Antes <A la policía le corresponde actuar.\nDespués 124",
            "antes <a la policía le corresponde actuar. después 124",
        ),
        ("Texto <[... la autoridad] sin cierre", "texto <[... la autoridad] sin cierre"),
        ("1 < 2 y 3 > 1; <x> literal", "1 < 2 y 3 > 1; <x> literal"),
        ('<table class="x"><tr><td colspan="2">Dos</td><td>3</td></tr></table>', "dos 3"),
    ],
)
def test_normalizacion_simetrica_e_idempotente(entrada, esperado):
    assert m.normalizar(entrada) == esperado
    assert m.normalizar(esperado) == esperado
    assert m.metricas(entrada, esperado)["cer"] == 0
    assert m.metricas(esperado, entrada)["wer"] == 0


@pytest.mark.parametrize("modo", ["estricto", "contenido"])
@pytest.mark.parametrize(
    "prefijo",
    [">", "-", "+", "*", ">=", ">>", "> >", "> -", "> +", "> −", "> ±"],
)
@pytest.mark.parametrize("numero", ["5", "-5", "+5", "−5", "±5", ".5", ",5"])
def test_prefijos_numericos_omitidos_son_discrepancias(modo, prefijo, numero):
    ref = f"{prefijo} {numero} metros"
    hip = f"{numero} metros"
    assert m.normalizar(ref, modo=modo) == ref.lower()
    assert m.metricas(hip, ref, modo=modo)["cer"] > 0
    assert m.metricas(hip, ref, modo=modo)["wer"] > 0


@pytest.mark.parametrize("modo", ["estricto", "contenido"])
@pytest.mark.parametrize("prefijo", ["-", "+", ">", ">>", "> >"])
@pytest.mark.parametrize(
    "cantidad",
    [
        "$500",
        "€500",
        "COP 500",
        "US$500",
        "(500)",
        "($500)",
        "COP -500",
        "-US$500",
        "+(500)",
        "(−500)",
        "cop +500",
        "US$ (500)",
    ],
)
def test_prefijos_de_importes_omitidos_son_discrepancias(modo, prefijo, cantidad):
    ref = f"{prefijo} {cantidad}"
    assert m.normalizar(ref, modo=modo) == ref.lower()
    assert m.normalizar(f"Texto\n\t{ref}", modo=modo) == f"texto {ref.lower()}"
    assert m.normalizar(m.normalizar(ref, modo=modo), modo=modo) == ref.lower()
    assert m.metricas(cantidad, ref, modo=modo)["cer"] > 0
    assert m.metricas(cantidad, ref, modo=modo)["wer"] > 0


@pytest.mark.parametrize("texto", [">5 metros", "+ valor", "- (valor)", "* ¿valor?"])
def test_estricto_conserva_prefijos_sin_estructura_markdown_identificada(texto):
    assert m.normalizar(texto, modo="estricto") == texto.lower()


@pytest.mark.parametrize("texto", ["> cita", ">> cita", "> > cita", "- Árbol", "* niñez"])
@pytest.mark.parametrize("modo", ["estricto", "contenido"])
def test_marcado_identificado_se_elimina(texto, modo):
    esperado = texto.split()[-1].lower()
    assert m.normalizar(texto, modo=modo) == esperado


def distancia_oraculo(a, b):
    anterior = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        fila = [i]
        for j, y in enumerate(b, 1):
            fila.append(min(fila[-1] + 1, anterior[j] + 1, anterior[j - 1] + (x != y)))
        anterior = fila
    return anterior[-1]


def lcs_oraculo(a, b):
    anterior = [0] * (len(b) + 1)
    for x in a:
        fila = [0]
        for j, y in enumerate(b, 1):
            fila.append(anterior[j - 1] + 1 if x == y else max(fila[-1], anterior[j]))
        anterior = fila
    return anterior[-1]


def test_levenshtein_y_lcs_exhaustivos_con_oraculos_independientes():
    cadenas = ["".join(x) for n in range(5) for x in itertools.product("ab", repeat=n)]
    for a, b in itertools.product(cadenas, repeat=2):
        assert m.distancia(a, b) == distancia_oraculo(a, b)
        assert m.longitud_lcs(a, b) == lcs_oraculo(a, b)


def test_distancia_y_lcs_palabras_unicode_aleatorias():
    rng = random.Random(35)
    for _ in range(80):
        a = rng.choices(["niñez", "mar", "23", "¿sí?"], k=rng.randrange(25))
        b = rng.choices(["niñez", "mar", "23", "¿sí?"], k=rng.randrange(25))
        assert m.distancia(a, b) == distancia_oraculo(a, b)
        assert m.longitud_lcs(a, b) == lcs_oraculo(a, b)


def test_multiconjunto_y_denominadores_direccionales():
    f = m.metricas("a a c", "a b")
    assert f["wer"] == 1
    assert f["recuperacion"] == 0.5
    assert f["precision"] == 1 / 3
    assert m.metricas("a b", "a a c")["wer"] == 2 / 3
    assert m.metricas("a b", "a a c")["recuperacion"] == 1 / 3


@pytest.mark.parametrize(("hip", "ref"), [("", ""), ("extra", ""), ("", "referencia")])
def test_vacios_no_ocultan_errores(hip, ref):
    f = m.metricas(hip, ref)
    assert f["ediciones_caracteres"] == max(len(hip), len(ref))
    assert f["cer"] == (1 if ref else None)
    assert f["precision"] == (0 if hip else None)


def test_orden_distingue_permutacion_con_multiconjunto_identico():
    ref = "uno dos tres cuatro cinco seis siete ocho nueve diez"
    hip = "seis siete ocho nueve diez uno dos tres cuatro cinco"
    f = m.metricas(hip, ref)
    assert f["recuperacion"] == f["precision"] == 1
    assert f["orden_lcs"] < 0.5
    assert m.metricas(ref, ref)["orden_lcs"] == 1


@pytest.mark.parametrize(
    ("texto", "tipo", "valor"),
    [
        ("Valor 12.345,67 y 2024", "numero", "12.345,67"),
        ("12/03/2024", "fecha", "12/03/2024"),
        ("2024-03-12", "fecha", "2024-03-12"),
        ("7 de agosto de 2020", "fecha", "7 de agosto de 2020"),
        ("47001-2333-000-2021-00198-00", "radicado", "47001-2333-000-2021-00198-00"),
        ("47-001-2333-000-2021-00198-00", "radicado", "47-001-2333-000-2021-00198-00"),
        ("47001233300020210019800", "radicado", "47001233300020210019800"),
        ("Artículo 15", "articulo", "artículo 15"),
        ("Art. 9", "articulo", "art. 9"),
        ("Ley 99 de 1993", "ley", "ley 99 de 1993"),
        ("Decreto 2324 de 1984", "decreto", "decreto 2324 de 1984"),
    ],
)
def test_contenido_critico_regex(texto, tipo, valor):
    assert m.criticos(texto)[tipo][valor] == 1


def test_criticos_multiconjunto_recall_en_ambos_sentidos_y_faltantes():
    c = m.comparar_criticos("Ley 99 de 1993; Ley 70 de 1993", "Ley 99 de 1993; Ley 99 de 1993")
    assert c["ley"]["recall_ref_en_hip"] == 0.5
    assert c["ley"]["recall_hip_en_ref"] == 0.5
    assert c["ley"]["faltantes_en_hip"] == ["ley 99 de 1993"]
    assert c["ley"]["faltantes_en_ref"] == ["ley 70 de 1993"]
    inverso = m.comparar_criticos(
        "Ley 99 de 1993; Ley 99 de 1993", "Ley 99 de 1993; Ley 70 de 1993"
    )
    assert inverso["ley"]["faltantes_en_hip"] == c["ley"]["faltantes_en_ref"]


def test_criticos_ausentes_no_son_recall_perfecto():
    assert all(
        f["recall_ref_en_hip"] is None for f in m.comparar_criticos("texto", "texto").values()
    )


def test_ruido_separa_cabeceras_repetidas_paginacion_y_otro():
    hip = "TRIBUNAL DEL MAR\nTexto inventado inventado\nPágina 2"
    r = m.ruido(hip, "Texto", {"tribunal del mar"})
    assert r["encabezados_pies_repetidos"] == {"del": 1, "mar": 1, "tribunal": 1}
    assert r["otras_palabras"] == {"inventado": 2}
    assert r["etiquetas_pagina"] == ["Página 2"]
    assert r["palabras_extra"] == 5


def test_encabezados_por_frecuencia_documental_y_posicion():
    paginas = [f"Tribunal del mar\ncontenido único {i}\nPie común" for i in range(10)]
    assert m.encabezados_pies(paginas) == {"tribunal del mar", "pie común"}
    assert m.encabezados_pies(paginas[:2]) == set()


def filas_bootstrap():
    return [
        {"slug": slug, **m.metricas(hip, ref)}
        for slug, hip, ref in [
            ("a", "aa", "aa"),
            ("a", "bb", "bb"),
            ("b", "z", "c"),
            ("b", "z", "d"),
        ]
    ]


def test_agregado_micro_no_media_de_porcentajes():
    filas = [{"slug": "a", **m.metricas("a", "a")}, {"slug": "b", **m.metricas("", "b" * 9)}]
    resultado = m.agregar(filas, repeticiones=100)
    assert resultado["cer"] == 0.9
    assert resultado["documentos"] == 2
    assert resultado["paginas"] == 2


def test_bootstrap_fijo_2000_y_cluster_documental_completo():
    filas = filas_bootstrap()
    por_pagina = m.bootstrap(filas)
    por_documento = m.bootstrap(filas, unidad="documento")
    assert m.REPETICIONES == 2000
    assert por_pagina == m.bootstrap(filas)
    assert por_documento["cer"] == [0, 1]
    assert por_pagina["cer"][0] <= 1 / 3 <= por_pagina["cer"][1]
    # El remuestreo del clúster debe ser idéntico al de sus sumas, no de medias.
    agregadas = []
    for slug in ("a", "b"):
        propias = [f for f in filas if f["slug"] == slug]
        agregadas.append({"slug": slug, **{k: sum(f[k] for f in propias) for k in m.CAMPOS}})
    assert por_documento == m.bootstrap(agregadas)


@pytest.mark.parametrize("unidad", ["pagina", "documento"])
def test_bootstrap_vacio_y_denominador_cero(unidad):
    assert all(x is None for x in m.bootstrap([], unidad=unidad).values())
    filas = [{"slug": "a", **m.metricas("extra", "")}]
    assert m.bootstrap(filas, unidad=unidad)["cer"] is None


def test_bootstrap_rechaza_configuracion_invalida():
    with pytest.raises(ValueError):
        m.bootstrap([], unidad="línea")
    with pytest.raises(ValueError):
        m.bootstrap([], repeticiones=0)


@pytest.fixture(scope="module")
def calibracion():
    return m.calibrar()


@pytest.mark.parametrize("tasa", [0.005, 0.01, 0.03])
def test_calibracion_sustituciones_recupera_dosis_cer(calibracion, tasa):
    prueba = next(f for f in calibracion["pruebas"] if f.get("tasa") == tasa)
    assert prueba["cer"] == prueba["esperado"]
    assert abs(prueba["cer"] - tasa) <= 0.5 / prueba["caracteres_ref"]
    assert prueba["correcto"]


def test_calibracion_borrado_numeros_detecta_todas_las_categorias(calibracion):
    prueba = next(f for f in calibracion["pruebas"] if f["tipo"] == "borrado_numeros")
    assert prueba["cer"] > 0
    assert all(
        f["total_ref"] > 0 and f["recall_ref_en_hip"] == 0 for f in prueba["criticos"].values()
    )
    assert calibracion["correcto"]


@pytest.mark.parametrize(
    "caso",
    [
        "bucle_lineas",
        "bucle_sin_saltos",
        "control_cita_duplicada",
        "control_diverso",
        "control_frase_juridica",
        "control_catalogo_circulares",
    ],
)
def test_calibracion_bucles_y_controles(calibracion, caso):
    assert next(f for f in calibracion["bucles"] if f["caso"] == caso)["correcto"]


@pytest.mark.parametrize("texto", ["", "texto con �", " "])
def test_calibracion_rechaza_datos_sin_dosis_interpretable(texto):
    with pytest.raises(ValueError):
        m.calibrar([("mala", texto)])


def test_marcadores_duplicados_no_asignan_texto_a_pagina_incorrecta():
    numeros, paginas, prefijo = v.separar_paginas(
        "extra<!-- página 1 -->a<!-- página 1 -->b<!-- página 3 -->c"
    )
    assert numeros == [1, 1, 3]
    assert paginas == {3: "c"}
    assert prefijo == "extra"


def test_exclusion_marcadas_bucles_nuevos_y_ausencias():
    mapping = [{"slug": "a", "paginas": "4", "duplicado_de": ""}]
    meta = [
        {
            "slug": "a",
            "pagina": "1",
            "tope_alcanzado": "True",
            "repeticion": "True",
            "tokens_generados": "8192",
        }
    ]
    paginas = {
        "a": {
            1: "texto",
            2: "texto normal",
            3: "frase reiterada de longitud suficiente para marcar\n" * 12,
        }
    }
    salida = v.excluir_paginas(mapping, meta, paginas)
    assert [f["pagina"] for f in salida] == [1, 3, 4]
    assert "tope_alcanzado" in salida[0]["motivo"]
    assert "lineas_repetidas" in salida[1]["motivo"]
    assert salida[2]["motivo"] == "pagina_ausente_o_ambigua"


@pytest.mark.parametrize(
    ("campo", "valor"), [("slug", "../escape"), ("categoria", "../../data"), ("sha256", "../a")]
)
def test_datos_no_pueden_dirigir_lecturas_fuera_de_raiz(campo, valor):
    fila = {"slug": "seguro", "categoria": "normativa", "sha256": "a" * 64, campo: valor}
    with pytest.raises(ValueError):
        v.rutas_documento(fila)


def test_integridad_reporta_hash_paginas_marcadores_archivos_y_duplicado(tmp_path, monkeypatch):
    entrada = tmp_path / "entrada"
    fidelidad = tmp_path / "fidelidad"
    monkeypatch.setattr(v, "ENTRADA", entrada)
    monkeypatch.setattr(v, "FIDELIDAD", fidelidad)
    (fidelidad / "originales").mkdir(parents=True)
    mapping = []
    sha = hashlib.sha256(b"pdf sintetico").hexdigest()
    (fidelidad / "originales" / (sha[:12] + ".pdf")).write_bytes(b"pdf alterado")
    for slug, duplicado, texto in [
        ("a", "", "<!-- página 1 -->texto"),
        ("b", "a", "<!-- página 1 -->distinto<!-- página 1 --><|ref|>"),
    ]:
        fila = {
            "slug": slug,
            "categoria": "normativa",
            "sha256": sha,
            "paginas": "1",
            "duplicado_de": duplicado,
            "paginas_con_error": "0",
            "paginas_marcadas": "0",
        }
        mapping.append(fila)
        for carpeta, sufijo, contenido in (("texto", ".md", texto), ("crudo", ".raw.txt", "crudo")):
            ruta = entrada / carpeta / "normativa" / (slug + sufijo)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(contenido, encoding="utf-8")
    (entrada / "texto" / "normativa" / "extra.md").write_text("extra", encoding="utf-8")
    (fidelidad / "mapa_originales.json").write_text(
        json.dumps({sha[:12] + ".pdf": {"sha256": sha}}), encoding="utf-8"
    )
    for nombre in ("mapping.csv", "paginas.csv", "run_info.json"):
        (entrada / nombre).write_text("sintético", encoding="utf-8")

    class PDFSimulado:
        page_count = 2

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    meta = [
        {"slug": "a", "pagina": "1", "error": "", "tope_alcanzado": "False", "repeticion": "False"}
    ]
    resultado, _, _ = v.integridad(mapping, meta, SimpleNamespace(open=lambda ruta: PDFSimulado()))
    tipos = {f["tipo"] for f in resultado["discrepancias"]}
    assert {
        "sha256_pdf",
        "paginas_pdf",
        "marcadores_no_consecutivos",
        "marcas_crudas_en_md",
        "correspondencia_archivos",
        "texto_duplicado_distinto",
    } <= tipos
    assert not resultado["ok"]
    assert resultado["archivos"]["texto"]["sobrantes"] == ["normativa/extra.md"]


def test_sospecha_no_atribuye_verdad_y_detecta_omision_adicion_orden():
    assert (
        v.motivos_sospecha({"recuperacion": 0.84, "precision": 1, "orden_lcs": 1})
        == "posible_omision"
    )
    assert (
        v.motivos_sospecha({"recuperacion": 1, "precision": 0.84, "orden_lcs": 1})
        == "posible_adicion"
    )
    assert (
        v.motivos_sospecha({"recuperacion": 1, "precision": 1, "orden_lcs": 0.64})
        == "posible_desorden_o_errores"
    )
    assert not v.motivos_sospecha({"recuperacion": 0.85, "precision": 0.85, "orden_lcs": 0.65})


def test_comparacion_excluye_duplicado_del_agregado_y_aplica_umbral_digital(tmp_path, monkeypatch):
    pdf = tmp_path / "sintetico.pdf"
    pdf.write_bytes(b"simulado")
    monkeypatch.setattr(v, "rutas_documento", lambda fila: (None, None, pdf))
    texto = "texto de capa digital " * 5

    class PDFSimulado:
        page_count = 3

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __getitem__(self, i):
            return SimpleNamespace(get_text=lambda: texto)

    mapping = [
        {"slug": slug, "categoria": "normativa", "duplicado_de": duplicado}
        for slug, duplicado in [("a", ""), ("b", "a")]
    ]
    meta = [
        {
            "slug": "a",
            "pagina": str(p),
            "caracteres_capa_texto_pdf": str(len(texto) if p != 3 else 79),
        }
        for p in range(1, 4)
    ]
    paginas = {s: {p: texto for p in range(1, 4)} for s in ("a", "b")}
    filas, incidencias = v.comparar(
        mapping,
        meta,
        paginas,
        [{"slug": "a", "pagina": 2}],
        SimpleNamespace(open=lambda ruta: PDFSimulado()),
    )
    assert len(filas) == 4
    assert [(f["slug"], f["pagina"]) for f in filas if f["incluida_agregados"]] == [("a", 1)]
    assert not incidencias


f3 = importar("comparar_fuentes")
est = importar("estadistica")
f4 = importar("fase4")
des = importar("preparar_desacuerdos")
calc = importar("calcular_desacuerdos")


@pytest.mark.parametrize(
    "envoltura", [r"\( [^{12}] \)", r"\( [12] \)", r"\( [ ^{12} ] \)", r"\( [ 12 ] \)"]
)
@pytest.mark.parametrize("modo", ["estricto", "contenido"])
def test_latex_llamadas_numericas_nuevas(envoltura, modo):
    assert m.normalizar("2008" + envoltura + "fin", modo=modo) == "2008 12 fin"


def test_contenido_unifica_tipografia_sin_borrar_puntuacion():
    a = "“Niñez”—‘sí’… 12–13; «mar»"
    b = '"Niñez"-\'sí\'... 12-13; "mar"'
    assert m.normalizar(a, modo="contenido") == m.normalizar(b, modo="contenido")
    assert m.metricas(a, b, modo="contenido")["cer"] == 0
    assert m.metricas(a, b, modo="estricto")["cer"] > 0
    assert m.normalizar(m.normalizar(a, modo="contenido"), modo="contenido") == m.normalizar(
        a, modo="contenido"
    )
    assert m.normalizar("¿sí? 23,45 á", modo="contenido") == "¿sí? 23,45 á"
    assert m.orden_lectura(a, b, modo="contenido")["orden_lcs"] == 1


def test_contenido_decodifica_comillas_html_con_misma_politica():
    assert m.normalizar("&ldquo;Sí&rdquo; &mdash; &hellip;", modo="contenido") == '"sí" - ...'
    with pytest.raises(ValueError):
        m.normalizar("a", modo="otro")


def test_calibracion_64_comprobaciones_metricas_y_12_controles():
    cal = f3.calibrar()
    assert sum(len(v["pruebas"]) for v in cal.values()) == 64
    assert sum(len(v["bucles"]) for v in cal.values()) == 12
    assert all(v["correcto"] for v in cal.values())


@pytest.mark.parametrize(
    ("cer", "color"),
    [
        (0.00999, "verde"),
        (0.01, "amarillo"),
        (0.03, "amarillo"),
        (0.03001, "rojo"),
        (None, "no definido"),
    ],
)
def test_semaforo_fronteras(cer, color):
    assert f3.semaforo(cer) == color


def test_escenario_u_no_es_cota_garantizada_de_caracteres():
    f = f3.sensibilidad_u(0.01)
    assert f["envolvente"] == [0, 0.0223]
    assert f["escenarios"][0]["fraccion_discrepancia_potencial_U"] == pytest.approx(0.24)
    assert "palabra" in f["supuesto"]


def test_segmentacion_s_por_formfeed_y_rechazo_de_desplazamientos():
    assert f3.paginas_s("a\n\f\nb\n\f\n", 2) == {1: "a", 2: "b"}
    with pytest.raises(ValueError):
        f3.paginas_s("a\n\f\nb", 3)


def test_ruta_prof_nfc_respeta_nombre_y_categoria():
    a = {"archivo_original": "Niñez A\u0301.pdf", "categoria": "normativa"}
    assert f3.ruta_prof(a) == "data/documents/bronze/normativa/Niñez Á.md"


def test_agregados_ampliados_micro_criticos_lcs_y_cluster():
    filas = [
        {"slug": "a", **f3.comparar_textos("Ley 99 de 1993", "Ley 99 de 1993", "contenido")},
        {"slug": "b", **f3.comparar_textos("Ley 70 de 1993", "Ley 99 de 1993", "contenido")},
    ]
    g = f3.agregar(filas, nivel="pagina", repeticiones=100)
    assert g["recall_critico"] < 1
    assert g["orden_lcs"] < 1
    assert g["cer"] == sum(f["ediciones_caracteres"] for f in filas) / sum(
        f["caracteres_ref"] for f in filas
    )
    assert g["ic95_por_documento"]["cer"] == g["ic95_por_pagina"]["cer"]
    assert f3.agregar(filas, nivel="documento", repeticiones=20)["ic95_por_pagina"] is None


@pytest.mark.parametrize(
    ("x", "y", "esperado"),
    [([1, 2, 3], [3, 2, 1], -1), ([1, 2, 2, 3], [1, 2, 2, 3], 1), ([1, 1], [2, 3], None)],
)
def test_spearman_empates_y_constantes(x, y, esperado):
    assert est.spearman(x, y) == esperado


def test_auc_con_empates_y_pesos_contra_oraculo_por_pares():
    rng = random.Random(99)
    for _ in range(40):
        scores = [rng.randrange(4) for _ in range(12)]
        ys = [0] * 6 + [1] * 6
        pesos = [rng.randrange(1, 4) for _ in ys]
        n = sum(pesos[i] for i, y in enumerate(ys) if not y)
        p = sum(pesos[i] for i, y in enumerate(ys) if y)
        esperado = sum(
            pesos[i]
            * pesos[j]
            * (1 if scores[i] > scores[j] else 0.5 if scores[i] == scores[j] else 0)
            for i, y in enumerate(ys)
            if y
            for j, z in enumerate(ys)
            if not z
        ) / (n * p)
        assert est.roc(scores, ys, pesos)["auc"] == esperado


def test_umbrales_roc_orientados_y_sensibilidad_objetivo():
    filas = [
        {"slug": str(j), "conf": v, "cer": cer}
        for j, (v, cer) in enumerate([(20, 0.2), (30, 0.1), (90, 0.01), (95, 0.001)])
    ]
    r = est.evaluar_predictor(filas, "conf", direccion=-1, repeticiones=100)
    assert r["auc"] == 1 and r["spearman"] == -1
    assert r["youden"]["umbral"] == 30
    assert r["youden"]["operador"] == "<="
    assert r["sensibilidad_90"]["sensibilidad"] >= 0.9
    assert r == est.evaluar_predictor(filas, "conf", direccion=-1, repeticiones=100)


def test_auc_sin_dos_clases_y_predictor_constante_no_recomienda_umbral():
    assert est.roc([1, 2], [1, 1])["auc"] is None
    r = est.evaluar_predictor(
        [{"slug": "a", "v": 1, "cer": 0.1}, {"slug": "b", "v": 1, "cer": 0}], "v", repeticiones=20
    )
    assert r["auc"] == 0.5 and r["youden"] is None and r["constante"]


def test_diferencias_json_recursivas_incluyen_null_vs_ausente():
    d = f4.diferencias({"a": [1, 2], "b": None}, {"a": [1, 3]})
    assert {x["campo"] for x in d} == {"$.a[1]", "$.b"}
    assert next(x for x in d if x["campo"] == "$.b")["presente_run1"]


def test_alineacion_exacta_y_segmentos_tamano_limitado():
    r = "uno dos Artículo 15 ley 99 de 1993 fin del texto".split()
    h = "uno dos Artículo 16 ley 70 de 1993 fin del texto".split()
    ops = des.alinear(r, h)
    assert sum(x[0] != "igual" for x in ops) == m.distancia(r, h)
    seg = des.segmentos(" ".join(h), " ".join(r))
    assert seg and any(x["critico"] for x in seg)
    assert all(3 <= len(x[k].split()) <= 25 for x in seg for k in ("s", "u"))


def test_ancla_recorte_unica_y_rechazo_de_ambigua():
    palabras = [(0, 0, 1, 1, p) for p in "uno dos tres cuatro cinco".split()]
    assert des.localizar(palabras, "uno dos tres") == [0, 1, 2]
    assert not des.localizar(palabras * 2, "uno dos tres")


def test_muestreo_ciego_30_paginas_y_clave_separada(tmp_path, monkeypatch):
    monkeypatch.setattr(des.c, "BASE", tmp_path)
    monkeypatch.setattr(des, "SALIDA", tmp_path)
    monkeypatch.setattr(
        des,
        "recortar",
        lambda d, p, s, i, fitz: {"ruta": i + ".png", "metodo": "simulado", "dpi": 200},
    )
    filas = []
    datos = {}
    for tipo in ("digital", "OCR"):
        slug = tipo.lower()
        datos[slug] = {"s": {}, "u": {}}
        for p in range(1, 25):
            datos[slug]["s"][p] = "Texto Artículo 15 Ley 99 de 1993 y costa."
            datos[slug]["u"][p] = "Texto Artículo 16 Ley 70 de 1993 y costa."
            filas.append(
                {
                    "slug": slug,
                    "pagina": p,
                    "tipo_pagina": tipo,
                    "comparacion": "S_mio_vs_U",
                    "modo": "contenido",
                    "ediciones_palabras": 2,
                }
            )
    des.preparar(filas, datos, None)
    f = des.c.csv_leer(tmp_path / "desacuerdos.csv")
    clave = des.c.csv_leer(tmp_path / "clave_desacuerdos.csv")
    assert len(f) == len(clave) == 30
    assert sum(x["tipo_pagina"] == "digital" for x in f) == 15
    assert sum(x["muestreo"] == "critico" for x in f) == 15
    assert "quien_es_A" not in f[0] and all(not x["veredicto"] and not x["nota"] for x in f)
    assert len({(x["slug"], x["pagina"]) for x in f}) == 30
    primero = (tmp_path / "desacuerdos.csv").read_bytes()
    des.preparar(filas, datos, None)
    assert (tmp_path / "desacuerdos.csv").read_bytes() == primero
    f[0]["veredicto"] = "A"
    des.c.csv_guardar(tmp_path / "desacuerdos.csv", f)
    with pytest.raises(ValueError):
        des.preparar(filas, datos, None)


@pytest.mark.parametrize("quien", ["S", "U"])
@pytest.mark.parametrize("veredicto", ["A", "B", "ambos", "ninguno"])
def test_calculo_veredictos_segun_clave(quien, veredicto):
    f = [{"id": "1", "tipo_pagina": "OCR", "veredicto": veredicto}]
    r = calc.calcular(f, [{"id": "1", "quien_es_A": quien}], repeticiones=20)
    s_correcta = veredicto == "ambos" or veredicto == ("A" if quien == "S" else "B")
    u_correcta = veredicto == "ambos" or veredicto == ("B" if quien == "S" else "A")
    assert r["estimaciones"]["error_S"] == int(not s_correcta)
    assert r["estimaciones"]["error_U"] == int(not u_correcta)


def test_calculo_pendientes_no_inventa_error_y_rechaza_clave_incompleta():
    filas = [{"id": "1", "tipo_pagina": "digital", "veredicto": ""}]
    r = calc.calcular(filas, [{"id": "1", "quien_es_A": "S"}], repeticiones=20)
    assert r["estado"] == "pendiente" and r["estimaciones"]["error_S"] is None
    with pytest.raises(ValueError):
        calc.calcular(filas, [])
    filas[0]["veredicto"] = "S"
    with pytest.raises(ValueError):
        calc.calcular(filas, [{"id": "1", "quien_es_A": "S"}])


def test_spearman_bootstrap_aun_cuando_todas_las_paginas_son_malas():
    filas = [{"slug": str(j), "x": j, "cer": 0.1 + j / 100} for j in range(5)]
    r = est.evaluar_predictor(filas, "x", corte=0.03, repeticiones=50)
    assert r["auc"] is None
    assert r["ic95_spearman"] == [1, 1]
    assert r["bootstrap_validos_dos_clases"] == 0


def test_spearman_ponderado_equivale_a_expandir_la_muestra():
    rng = random.Random(51)
    for _ in range(40):
        x = [rng.randrange(4) for _ in range(10)]
        y = [rng.randrange(4) for _ in range(10)]
        pesos = [rng.randrange(4) for _ in x]
        xx = [v for v, w in zip(x, pesos, strict=True) for _ in range(w)]
        yy = [v for v, w in zip(y, pesos, strict=True) for _ in range(w)]
        assert est.spearman(x, y, pesos) == pytest.approx(est.spearman(xx, yy))


def test_cache_csv_conserva_tipos_booleanos_nulos_json_y_cientificos(tmp_path, monkeypatch):
    monkeypatch.setattr(f3.c, "BASE", tmp_path)
    ruta = tmp_path / "cache.csv"
    f3.c.csv_guardar(
        ruta,
        [
            {
                "n": 3,
                "cer": 1e-5,
                "tabla": True,
                "pagina": None,
                "criticos": {"n": 2},
                "slug": "norma_a",
            }
        ],
    )
    assert f3.cargar_metricas_csv(ruta) == [
        {
            "n": 3,
            "cer": 1e-5,
            "tabla": True,
            "pagina": None,
            "criticos": {"n": 2},
            "slug": "norma_a",
        }
    ]


def test_ruido_documental_prof_sin_inventar_paginas_y_ruido_agregado():
    datos = {
        "a": {
            "s": {
                1: "Cabecera común\ncuerpo",
                2: "Cabecera común\ncuerpo",
                3: "Cabecera común\ncuerpo",
            },
            "u": {1: "cuerpo", 2: "cuerpo", 3: "cuerpo"},
            "elegibles": [1, 2, 3],
            "prof": "Cabecera común\ncuerpo\nCabecera común\ncuerpo\nCabecera común\ncuerpo",
        }
    }
    fila = {"slug": "a", "modo": "contenido", "comparacion": "S_prof_vs_U"}
    f3.refrescar_ruido_documental([fila], datos)
    assert sum(fila["ruido"]["encabezados_pies_repetidos"].values()) == 6
    assert fila["ruido"]["palabras_extra"] == 6
    registro = {"slug": "a", **f3.comparar_textos("extra extra", "texto", "contenido")}
    g = f3.agregar([registro], nivel="pagina", repeticiones=10)
    assert g["ruido_agregado"]["palabras_extra"] == 2
    assert g["ruido_agregado"]["palabras_resto"] == 2


def test_csv_admite_faltantes_documentales_mayores_de_128_kib(tmp_path, monkeypatch):
    monkeypatch.setattr(f3.c, "BASE", tmp_path)
    ruta = tmp_path / "criticos_largos.csv"
    datos = [{"slug": "a", "criticos": {"faltantes": ["12 de agosto de 2024"] * 8000}}]
    f3.c.csv_guardar(ruta, datos)
    assert f3.cargar_metricas_csv(ruta) == datos


@pytest.mark.parametrize("comun", [f3.c, des.c], ids=["cache", "muestreo"])
@pytest.mark.parametrize("temporal", [False, True], ids=["benchmark", "temporal"])
def test_guard_escritura_protege_entrada_y_rutas_externas(tmp_path, monkeypatch, comun, temporal):
    if temporal:
        monkeypatch.setattr(comun, "BASE", tmp_path / "permitido")
    raiz = comun.BASE
    for ruta in (
        raiz / "entrada" / "prohibido.csv",
        raiz.parent / "fuera" / "prohibido.csv",
        raiz / "resultados" / ".." / "entrada" / "prohibido.csv",
        raiz / ".." / "prohibido.csv",
    ):
        with pytest.raises(ValueError, match="Escritura fuera del benchmark o dentro de entrada"):
            comun.csv_guardar(ruta, [{"sintetico": True}])
    if temporal:
        # La raíz temporal tampoco habilita escrituras en el benchmark real.
        with pytest.raises(ValueError, match="Escritura fuera del benchmark o dentro de entrada"):
            comun.json_guardar(BASE / "prohibido.json", {})
        ruta = raiz / "resultados" / "permitido.json"
        comun.json_guardar(ruta, {"sintetico": True})
        assert json.loads(ruta.read_text(encoding="utf-8")) == {"sintetico": True}


f5 = importar("evaluar_fase5")


@pytest.mark.parametrize("raya", ["–", "—"])
def test_contenido_no_desguiona_rayas_tipograficas_al_final_de_linea(raya):
    texto = f"acceso{raya}\nprohibido"
    assert m.normalizar(texto, modo="contenido") == "acceso- prohibido"
    assert m.metricas(texto, "accesoprohibido", modo="contenido")["cer"] > 0
    assert m.metricas(texto, "accesoprohibido", modo="contenido")["wer"] > 0
    assert m.normalizar("acceso-\nprohibido", modo="contenido") == "accesoprohibido"


@pytest.fixture
def escenario_fase5(tmp_path, monkeypatch):
    monkeypatch.setattr(f5, "BASE", tmp_path)
    monkeypatch.setattr(f5, "DESC", tmp_path / "entrada/descomprimido")
    monkeypatch.setitem(f5.json_guardar.__globals__, "BASE", tmp_path)

    def escribir(ruta, texto):
        destino = tmp_path / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")

    def guardar(ruta, datos):
        escribir(ruta, json.dumps(datos))

    guardar("division_ajuste_validacion.json", {"ajuste": ["a"], "validacion": [], "semilla": 1})
    escribir("entrada/descomprimido/mapping.csv", "slug,sha256,categoria\na,doc,normativa\n")
    escribir(
        "entrada/descomprimido/texto/normativa/a.md",
        "<!-- página 1 -->Ley 99 de 1993<!-- página 2 -->residuo<!-- página 3 -->digital<!-- página 4 -->excluida",
    )
    escribir("resultados/paginas_excluidas.csv", "slug,pagina\na,4\n")
    guardar(
        "trabajo/s_mio/run1/capas/bronze/doc.extraction.json",
        {
            "ocr_pages": [1, 4],
            "ocr_failed_pages": [2],
            "chars_per_page": [14, 7, 7, 8],
        },
    )
    escribir("base/doc.txt", "Ley 99 de 1993\n\f\nresiduo\n\f\ndigital\n\f\nexcluida")
    escribir("otra/doc_001.txt", "Ley 99 de 1993")

    def ejecutar(*args):
        monkeypatch.setattr(
            f5.sys,
            "argv",
            ["evaluar_fase5.py", "--conjunto", "ajuste", "--variante", "base=bronce:base", *args],
        )
        f5.main()
        return json.loads(
            (tmp_path / "resultados/fase5/ajuste_ocr.json").read_text(encoding="utf-8")
        )

    return SimpleNamespace(raiz=tmp_path, escribir=escribir, ejecutar=ejecutar)


def test_fase5_aborta_listando_faltantes_sin_reducir_poblacion(escenario_fase5, capsys):
    e = escenario_fase5
    with pytest.raises(SystemExit) as exc:
        e.ejecutar("--variante", "otra=pagina:otra", "--variante", "ausente=bronce:no_existe")
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert all(x in error for x in ["otra: a:2", "ausente: a:1", "ausente: a:2"])
    cobertura = json.loads((e.raiz / "resultados/fase5/ajuste_ocr_cobertura.json").read_text())
    assert cobertura["base"]["presentes"] == cobertura["base"]["esperadas"] == 2
    assert cobertura["otra"]["faltantes"] == 1
    assert not (e.raiz / "resultados/fase5/ajuste_ocr.json").exists()


def test_fase5_permite_faltantes_como_vacios_y_exporta_cobertura(escenario_fase5, capsys):
    resultado = escenario_fase5.ejecutar("--variante", "otra=pagina:otra", "--permitir-faltantes")
    assert all(r["paginas"] == 2 for r in resultado["resumen"].values())
    faltante = resultado["filas"]["otra"][1]
    assert faltante["faltante"] and faltante["ed_c"] == faltante["ref_c"] == len("residuo")
    assert resultado["resumen"]["base"]["cer"] == 0
    assert resultado["resumen"]["otra"]["cer"] > 0
    assert resultado["cobertura"]["otra"]["cobertura"] == 0.5
    assert resultado["cobertura"]["otra"]["paginas_faltantes"] == [
        {"slug": "a", "doc_id": "doc", "pagina": 2}
    ]
    assert "hipótesis vacías" in capsys.readouterr().out


@pytest.mark.parametrize("tipo", ["pagina", "bronce"])
def test_fase5_distingue_texto_vacio_de_archivo_o_pagina_ausente(tmp_path, tipo):
    assert f5.texto_variante(tipo, tmp_path, "doc", 1) is None
    archivo = tmp_path / ("doc.txt" if tipo == "bronce" else "doc_001.txt")
    archivo.write_text("", encoding="utf-8")
    assert f5.texto_variante(tipo, tmp_path, "doc", 1) == ""
    assert f5.texto_variante(tipo, tmp_path, "doc", 2) is None
    if tipo == "bronce":
        archivo.write_text("texto\n\f\n", encoding="utf-8")
        assert f5.texto_variante(tipo, tmp_path, "doc", 2) == ""


@pytest.mark.parametrize("residual", ["", "residuo"])
def test_fase5_evalua_ocr_fallido_y_lo_excluye_de_digital(escenario_fase5, residual):
    e = escenario_fase5
    e.escribir("base/doc.txt", f"Ley 99 de 1993\n\f\n{residual}\n\f\ndigital\n\f\nexcluida")
    r = e.ejecutar()
    assert [f["pagina"] for f in r["filas"]["base"]] == [1, 2]
    assert r["filas"]["base"][1]["ed_c"] == (0 if residual else len("residuo"))
    assert not r["filas"]["base"][1]["faltante"]
    e.ejecutar("--paginas", "digital")
    digital = json.loads((e.raiz / "resultados/fase5/ajuste_digital.json").read_text())
    assert [f["pagina"] for f in digital["filas"]["base"]] == [3]


def test_fase5_no_omite_referencia_u_ausente(escenario_fase5, capsys):
    e = escenario_fase5
    e.escribir("entrada/descomprimido/texto/normativa/a.md", "<!-- página 1 -->Ley 99 de 1993")
    with pytest.raises(SystemExit):
        e.ejecutar("--permitir-faltantes")
    assert "Faltan referencias U: a:2" in capsys.readouterr().err


@pytest.mark.parametrize("residual", ["", "residuo"])
def test_comparar_fuentes_clasifica_y_evalua_paginas_ocr_fallidas(residual):
    datos = {
        "a": {
            "doc": {"categoria": "normativa"},
            "elegibles": [1, 2],
            "extr": {
                "ocr_pages": [1],
                "ocr_failed_pages": [2],
                "ocr_confidence": {},
                "chars_per_page": [14, len(residual)],
            },
            "s": {1: "Ley 99 de 1993", 2: residual},
            "u": {1: "Ley 99 de 1993", 2: "residuo"},
            "prof": "Ley 99 de 1993 residuo",
            "capa": {1: "", 2: ""},
            "meta": {p: {"caracteres_capa_texto_pdf": 0} for p in [1, 2]},
        }
    }
    filas, documentos = f3.producir_filas(datos)
    assert len(filas) == 4
    assert all(f["tipo_pagina"] == "OCR" for f in filas + documentos)
    assert all(f["paginas_OCR"] == 2 and f["paginas_digitales"] == 0 for f in documentos)
    fallidas = [f for f in filas if f["pagina"] == 2]
    assert all(f["cer"] == (0 if residual else 1) for f in fallidas)


@pytest.mark.parametrize("completo", [False, True])
def test_claves_esperadas_coinciden_con_filas_y_documentos_producidos(completo):
    datos = {
        "a": {
            "doc": {"categoria": "normativa"},
            "elegibles": [1, 2],
            "extr": {"ocr_pages": [2], "ocr_confidence": {}, "chars_per_page": [5, 5]},
            "s": {1: "texto", 2: "texto"},
            "u": {p: "texto" for p in ([1, 2] if completo else [1, 2, 3])},
            "prof": "texto texto",
            "capa": {1: "texto"},
            "meta": {p: {"caracteres_capa_texto_pdf": n} for p, n in [(1, 80), (2, 79)]},
        }
    }
    filas, documentos = f3.producir_filas(datos)
    assert len(filas) == 6  # Dos modos, dos S_mio y una capa con >=80 caracteres.
    assert len(documentos) == (8 if completo else 2)
    assert f3.claves_esperadas(datos) == {
        "paginas.csv": f3.claves_filas(filas),
        "documentos.csv": f3.claves_filas(documentos),
    }


def fila_fase5(slug="a", **cambios):
    return {
        "slug": slug,
        "ed_c": 0,
        "ref_c": 0,
        "ed_p": 0,
        "ref_p": 0,
        "crit_ok": 0,
        "crit_ref": 0,
        "num_ok": 0,
        "num_ref": 0,
        **cambios,
    }


def test_fase5_denominadores_nulos_no_inventan_tasas():
    r = f5.agregar([fila_fase5(ed_c=3, ed_p=1)], repeticiones=10)
    for nombre in ("cer", "wer", "recall_critico", "recall_numero_anio"):
        assert r[nombre] is None
        assert r[f"ic95_{nombre}_documento"] is None
        assert r["bootstrap_validos"][nombre] == 0


def test_fase5_bootstrap_omite_replicas_indefinidas():
    filas = [fila_fase5("a"), fila_fase5("b", ed_c=2, ref_c=4, ed_p=1, ref_p=2)]
    r = f5.agregar(filas, repeticiones=100, semilla=19)
    rng = random.Random(19)
    validas = sum(
        any(d == "b" for d in [rng.choice(["a", "b"]) for _ in range(2)]) for _ in range(100)
    )
    assert 0 < validas < 100
    assert r["bootstrap_validos"] == {
        "cer": validas,
        "wer": validas,
        "recall_critico": 0,
        "recall_numero_anio": 0,
    }
    assert r["cer"] == r["wer"] == 0.5
    assert r["ic95_cer_documento"] == r["ic95_wer_documento"] == [0.5, 0.5]
    assert r["recall_critico"] is None
    assert r["ic95_recall_critico_documento"] is None


def test_fase5_recall_numero_anio_usa_solo_categoria_numero():
    filas = [fila_fase5(crit_ok=90, crit_ref=100, num_ok=2, num_ref=4)]
    r = f5.agregar(filas, repeticiones=10)
    assert r["recall_critico"] == 0.9
    assert r["recall_numero_anio"] == 0.5
    assert r["ic95_recall_numero_anio_documento"] == [0.5, 0.5]


def test_fase5_rechaza_evaluacion_sin_paginas(escenario_fase5, capsys):
    with pytest.raises(ValueError, match="sin páginas"):
        f5.agregar([])
    with pytest.raises(SystemExit):
        escenario_fase5.ejecutar("--conjunto", "validacion")
    assert "Evaluación sin páginas" in capsys.readouterr().err


def test_fase5_salida_textual_muestra_no_definidos(escenario_fase5, capsys):
    escenario_fase5.escribir(
        "entrada/descomprimido/texto/normativa/a.md", "<!-- página 1 --><!-- página 2 -->"
    )
    r = escenario_fase5.ejecutar()
    salida = capsys.readouterr().out
    assert all(x in salida for x in ["CER=n/d", "IC95doc=n/d", "WER=n/d", "recall_crit=n/d"])
    assert r["resumen"]["base"]["recall_critico"] is None


@pytest.mark.parametrize("codigo_cambiado", [None, *f3.CODIGO_CACHE])
def test_cache_recalcula_si_cambian_metricas_o_clasificacion(
    tmp_path, monkeypatch, codigo_cambiado
):
    monkeypatch.setattr(f3, "BASE", tmp_path)
    monkeypatch.setattr(f3, "SALIDA", tmp_path / "fase3")
    monkeypatch.setattr(f3.c, "BASE", tmp_path)
    monkeypatch.setattr(f3.c, "huella", lambda p: p.name)
    monkeypatch.setattr(f3, "catalogo_prof", lambda: ("version", {}))
    monkeypatch.setattr(f3, "version_pymupdf", lambda: "prueba")
    (tmp_path / "fase3").mkdir()
    (tmp_path / "resultados").mkdir()
    for nombre in ("paginas.csv", "documentos.csv"):
        f3.c.csv_guardar(f3.SALIDA / nombre, [])
    huellas = {n: n for n in f3.CODIGO_CACHE}
    if codigo_cambiado:
        huellas[codigo_cambiado] = "anterior"
    (tmp_path / "fase3/procedencia.json").write_text(
        json.dumps(
            {
                "huellas_codigo": huellas,
                "pymupdf": "prueba",
                "huellas_entrada": {"entrada/mapping.csv": "mapping.csv"},
                "huellas_fuentes": {
                    "U": {},
                    "S_mio": {},
                    "S_prof": {},
                    "capa_pdf": {},
                    "pymupdf": "prueba",
                },
                "csv_metricas": f3.procedencia_csv({}),
            }
        )
    )
    assert f3.comprobar_cache({}) is (codigo_cambiado is None)
    monkeypatch.setattr(f3.c, "huella", lambda p: "entrada_alterada")
    with pytest.raises(ValueError, match="Entrada modificada"):
        f3.comprobar_cache({})


@pytest.fixture
def escenario_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(f3, "version_pymupdf", lambda: "prueba")
    monkeypatch.setattr(f3, "BASE", tmp_path)
    monkeypatch.setattr(f3.c, "BASE", tmp_path)
    monkeypatch.setattr(f3, "SALIDA", tmp_path / "resultados/fase3")
    monkeypatch.setattr(f3, "BRONCE", tmp_path / "bronce")
    md = tmp_path / "entrada/a.md"
    md.parent.mkdir()
    md.write_text("<!-- página 1 -->texto original", encoding="utf-8")
    monkeypatch.setattr(f3.v, "rutas_documento", lambda doc: (md, None, None))
    doc = {"sha256": "doc", "categoria": "normativa", "archivo_original": "a.pdf"}
    datos = {
        "a": {
            "doc": doc,
            "elegibles": [1],
            "u": {1: "texto original"},
            "capa": {1: "texto extraído"},
            "meta": {1: {"caracteres_capa_texto_pdf": 80}},
        }
    }
    f3.BRONCE.mkdir()
    for sufijo in (".txt", ".extraction.json", ".quality.json"):
        (f3.BRONCE / ("doc" + sufijo)).write_text("original", encoding="utf-8")
    blob = {"ruta": f3.ruta_prof(doc), "blob": "objeto-git"}
    monkeypatch.setattr(f3, "catalogo_prof", lambda: ("version", {f3.ruta_prof(doc): blob}))
    monkeypatch.setattr(f3, "git", lambda *args: b"bronce profesor")
    for nombre in f3.CODIGO_CACHE:
        (tmp_path / nombre).write_text("codigo", encoding="utf-8")
    campos = ("slug", "pagina", "modo", "comparacion", "nivel", "conjunto")
    for nombre, claves in f3.claves_esperadas(datos).items():
        f3.c.csv_guardar(
            f3.SALIDA / nombre, [dict(zip(campos, clave, strict=True)) for clave in claves]
        )
    procedencia = {
        "pymupdf": "prueba",
        "huellas_entrada": {},
        "huellas_codigo": {n: f3.c.huella(tmp_path / n) for n in f3.CODIGO_CACHE},
        "huellas_fuentes": f3.huellas_fuentes(datos),
        "csv_metricas": f3.procedencia_csv(datos),
    }

    def guardar():
        f3.c.json_guardar(f3.SALIDA / "procedencia.json", procedencia)

    guardar()
    assert f3.comprobar_cache(datos)
    return SimpleNamespace(datos=datos, md=md, procedencia=procedencia, guardar=guardar)


@pytest.mark.parametrize("codigo_cambiado", [False, True])
def test_cache_invalida_u_aunque_se_regenere_integridad(escenario_cache, codigo_cambiado):
    e = escenario_cache
    e.md.write_text("<!-- página 1 -->texto modificado", encoding="utf-8")
    f3.c.json_guardar(
        f3.BASE / "resultados/integridad.json",
        {"documentos": [{"slug": "a", "sha256_md": f3.c.huella(e.md)}]},
    )
    if codigo_cambiado:
        (f3.BASE / "metricas.py").write_text("codigo nuevo", encoding="utf-8")
    with pytest.raises(ValueError, match="U cambió"):
        f3.comprobar_cache(e.datos)


@pytest.mark.parametrize("sufijo", [".txt", ".extraction.json", ".quality.json"])
def test_cache_invalida_bronce_aunque_se_regenere_repetibilidad(escenario_cache, sufijo):
    e = escenario_cache
    nombre = "doc" + sufijo
    ruta = f3.BRONCE / nombre
    ruta.write_text("modificado", encoding="utf-8")
    f3.c.json_guardar(
        f3.SALIDA / "repetibilidad.json",
        {"archivos": [{"archivo": nombre, "sha256_run1": f3.c.huella(ruta)}]},
    )
    with pytest.raises(ValueError, match="S_mio cambió"):
        f3.comprobar_cache(e.datos)


def test_cache_invalida_blob_prof_por_sha256_directo(escenario_cache, monkeypatch):
    e = escenario_cache
    esperado = hashlib.sha256(b"bronce profesor").hexdigest()
    assert next(iter(e.procedencia["huellas_fuentes"]["S_prof"].values()))["sha256"] == esperado
    monkeypatch.setattr(f3, "git", lambda *args: b"bronce profesor modificado")
    with pytest.raises(ValueError, match="S_prof cambió"):
        f3.comprobar_cache(e.datos)


def test_cache_antigua_sin_huellas_directas_no_reutiliza_csv(escenario_cache):
    e = escenario_cache
    del e.procedencia["huellas_fuentes"]
    e.guardar()
    assert not f3.comprobar_cache(e.datos)


def test_cache_antigua_sin_huellas_csv_no_reutiliza(escenario_cache):
    e = escenario_cache
    del e.procedencia["csv_metricas"]
    e.guardar()
    assert not f3.comprobar_cache(e.datos)


@pytest.mark.parametrize("modulo", f3.CODIGO_CACHE)
def test_solo_resumen_exige_regenerar_si_cambia_una_dependencia(
    escenario_cache, monkeypatch, capsys, modulo
):
    e = escenario_cache
    (f3.BASE / modulo).write_text("codigo cambiado", encoding="utf-8")
    monkeypatch.setattr(f3.sys, "argv", ["comparar_fuentes.py", "--reanudar", "--solo-resumen"])
    monkeypatch.setitem(f3.sys.modules, "fitz", SimpleNamespace())
    monkeypatch.setattr(
        f3, "sys", SimpleNamespace(stdout=SimpleNamespace(reconfigure=lambda **k: None))
    )
    monkeypatch.setattr(f3, "calibrar", lambda: {"contenido": {"correcto": True}})
    monkeypatch.setattr(f3, "cargar", lambda fitz: e.datos)
    # No se debe llegar a reutilizar los informes ni a recalcular las filas.
    monkeypatch.setattr(
        f3, "cargar_metricas_csv", lambda *a: pytest.fail("caché obsoleta reutilizada")
    )
    with pytest.raises(SystemExit) as error:
        f3.main()
    assert error.value.code == 2
    assert "recalcular FASE 4 sin --solo-resumen" in capsys.readouterr().err


@pytest.mark.parametrize("nombre", ["paginas.csv", "documentos.csv"])
@pytest.mark.parametrize("alteracion", ["truncado", "ausente", "contenido"])
def test_cache_rechaza_csv_alterado(escenario_cache, nombre, alteracion):
    e = escenario_cache
    ruta = f3.SALIDA / nombre
    if alteracion == "ausente":
        ruta.unlink()
    elif alteracion == "truncado":
        ruta.write_bytes(ruta.read_bytes()[:50])
    else:
        ruta.write_bytes(ruta.read_bytes().replace(b"S_mio", b"S_otro"))
    with pytest.raises(ValueError, match="CSV alterado o ausente"):
        f3.comprobar_cache(e.datos)


@pytest.mark.parametrize("nombre", ["paginas.csv", "documentos.csv"])
@pytest.mark.parametrize("alteracion", ["falta", "duplicada", "inesperada", "manifiesto"])
def test_cache_verifica_completitud_aun_con_hash_actualizado(escenario_cache, nombre, alteracion):
    e = escenario_cache
    ruta = f3.SALIDA / nombre
    filas = f3.c.csv_leer(ruta)
    if alteracion == "duplicada":
        filas[-1] = filas[0]  # El mismo número de filas no garantiza completitud.
    elif alteracion == "inesperada":
        filas[-1]["slug"] = "otro"
    else:
        filas.pop()
    f3.c.csv_guardar(ruta, filas)
    e.procedencia["csv_metricas"][nombre]["sha256"] = f3.c.huella(ruta)
    if alteracion == "manifiesto":
        e.procedencia["csv_metricas"][nombre]["claves"] = f3.claves_filas(filas)
    e.guardar()
    with pytest.raises(ValueError, match="CSV incompleto|Claves esperadas incompatibles"):
        f3.comprobar_cache(e.datos)


def test_csv_interrumpido_preserva_destino_y_rechaza_cache_mezclada(escenario_cache, monkeypatch):
    e = escenario_cache
    ruta = f3.SALIDA / "documentos.csv"
    original = ruta.read_bytes()
    # La primera sustitución terminó; la segunda se interrumpe antes de publicar
    # el par y su procedencia. La procedencia anterior no acredita esta mezcla.
    paginas = f3.c.csv_leer(f3.SALIDA / "paginas.csv")
    paginas[0]["cer"] = 0.125
    f3.c.csv_guardar(f3.SALIDA / "paginas.csv", paginas)

    def interrumpir(origen, destino):
        assert origen.parent == destino.parent
        assert origen.read_bytes() != original
        assert destino.read_bytes() == original
        raise OSError("escritura interrumpida")

    monkeypatch.setattr(f3.c.os, "replace", interrumpir)
    with pytest.raises(OSError, match="escritura interrumpida"):
        f3.c.csv_guardar(ruta, [{"parcial": True}])
    assert ruta.read_bytes() == original
    assert not list(f3.SALIDA.glob(".*.tmp"))
    with pytest.raises(ValueError, match="CSV alterado o ausente: paginas.csv"):
        f3.comprobar_cache(e.datos)


def test_csv_interrumpido_durante_filas_no_publica_parcial(tmp_path, monkeypatch):
    monkeypatch.setattr(f3.c, "BASE", tmp_path)
    ruta = tmp_path / "nuevo.csv"
    escribir = f3.c.csv.DictWriter.writerow

    def interrumpir(escritor, fila):
        escribir(escritor, fila)
        if fila.get("n") == 2:
            raise OSError("fila interrumpida")

    monkeypatch.setattr(f3.c.csv.DictWriter, "writerow", interrumpir)
    with pytest.raises(OSError, match="fila interrumpida"):
        f3.c.csv_guardar(ruta, [{"n": 1}, {"n": 2}, {"n": 3}])
    assert not ruta.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("fuente", ["capa", "pymupdf", "pymupdf_registrada"])
def test_cache_invalida_texto_de_capa_pdf_o_version_pymupdf(escenario_cache, monkeypatch, fuente):
    e = escenario_cache
    if fuente == "capa":
        e.datos["a"]["capa"][1] = "extracción diferente del mismo PDF"
    elif fuente == "pymupdf":
        monkeypatch.setattr(f3, "version_pymupdf", lambda: "otra versión")
    else:
        e.procedencia["pymupdf"] = "otra versión"
        e.guardar()
    assert not f3.comprobar_cache(e.datos)


@pytest.mark.parametrize("corrida", ["run1", "run2"])
@pytest.mark.parametrize("cambio", ["contenido", "nuevo", "borrado", "renombrado"])
def test_solo_resumen_recalcula_fase4_si_cambia_corrida_completa(escenario_cache, corrida, cambio):
    e = escenario_cache
    for nombre in ("run1", "run2"):
        raiz = f3.BASE / "trabajo/s_mio" / nombre / "capas/bronze"
        raiz.mkdir(parents=True)
        # Documento que no pertenece a U ni al conjunto usado por los CSV.
        (raiz / "fuera_de_U.txt").write_text("original", encoding="utf-8")
    for nombre in f3.ARCHIVOS_FASE4:
        f3.c.json_guardar(f3.SALIDA / nombre, {"origen": "cache"})
    e.procedencia["fase4"] = f3.procedencia_fase4(f3.manifiesto_corridas())
    e.guardar()
    llamadas = []

    def recalcular():
        llamadas.append(True)
        return {"origen": "recalculado"}

    fases = SimpleNamespace(
        repetibilidad=recalcular, alertas=lambda *a: recalcular(), causas=lambda *a: recalcular()
    )
    assert (
        f3.obtener_fase4(
            fases, [], [], e.datos, reutilizar=True, manifiesto=f3.manifiesto_corridas()
        )
        == ({"origen": "cache"},) * 3
    )
    assert not llamadas
    ruta = f3.BASE / "trabajo/s_mio" / corrida / "capas/bronze/fuera_de_U.txt"
    if cambio == "contenido":
        ruta.write_text("modificado", encoding="utf-8")
    elif cambio == "nuevo":
        ruta.with_name("nuevo.txt").write_text("nuevo", encoding="utf-8")
    elif cambio == "borrado":
        ruta.unlink()
    else:
        ruta.rename(ruta.with_name("renombrado.txt"))
    # La caché de métricas sigue siendo válida: solo debe invalidarse FASE 4.
    assert f3.comprobar_cache(e.datos)
    assert (
        f3.obtener_fase4(
            fases, [], [], e.datos, reutilizar=True, manifiesto=f3.manifiesto_corridas()
        )
        == ({"origen": "recalculado"},) * 3
    )
    assert len(llamadas) == 3


def test_informe_fase4_sensibilidad_none_es_no_disponible(tmp_path, monkeypatch):
    monkeypatch.setattr(f4, "SALIDA", tmp_path)
    monkeypatch.setattr(f4.c, "BASE", tmp_path)
    fila = {
        "comparacion": "S_mio_vs_U",
        "nivel": "pagina",
        "conjunto": "elegibles",
        "estrato": "total",
        "unidades": 1,
        "cer": None,
        "wer": None,
        "recall_critico": None,
        "recall_critico_inverso": None,
        "orden_lcs": None,
        "ic95_por_documento": {"cer": None},
        "semaforo": "sin evaluar",
        "sensibilidad_error_U": None,
    }
    resumen = [{**fila, "modo": modo} for modo in ("contenido", "estricto")]
    f4.informe(
        resumen,
        {"identicos": 0, "archivos_run1": 0, "diferencias": 0},
        {"resultados": [], "limitaciones": []},
        {"top_causas": [], "regla_aporte": ""},
    )
    texto = (tmp_path / "informe.md").read_text(encoding="utf-8")
    assert "| sin evaluar | — |" in texto


@pytest.mark.parametrize("campo,valor", [("veredicto", "S"), ("nota", "Revisión pendiente")])
def test_recalculo_conserva_muestreo_con_revision_humana(tmp_path, monkeypatch, campo, valor):
    monkeypatch.setattr(f3, "SALIDA", tmp_path)
    monkeypatch.setattr(des, "SALIDA", tmp_path)
    monkeypatch.setattr(f3.c, "modulo", lambda nombre: des)
    ruta = tmp_path / "desacuerdos.csv"
    ruta.write_text(f"id,{campo}\n1,{valor}\n", encoding="utf-8")
    original = ruta.read_bytes()
    f3.preparar_muestreo([], {}, None)
    assert ruta.read_bytes() == original
    # La protección original sigue rechazando la regeneración explícita.
    with pytest.raises(ValueError, match="adjudicaciones/notas existentes"):
        des.preparar([], {}, None)
