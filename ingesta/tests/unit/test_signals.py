"""Señales de advertencia: secuencia de artículos, caída de texto e imágenes."""

from __future__ import annotations

import pytest

from ingest.offline.signals import (
    caida_texto,
    imagenes_en_paginas_digitales,
    secuencia_articulos,
    tablas_imagen_sospechosas,
)


def test_secuencia_ignora_considerandos_y_cuenta_descensos():
    texto = (
        "Que el\nArtículo 79. de la Constitución dispone\n"
        "ARTÍCULO 1. Objeto.\nARTÍCULO 2. Ámbito.\nARTÍCULO 3. Definiciones.\n"
        "ARTÍCULO 22. Zonas.\nARTÍCULO 5. Horarios.\n"
    )
    s = secuencia_articulos(texto)
    assert s["articulos"] == 5
    assert s["descensos"] == 1  # «22» (un «2°» mal leído) rompe la secuencia
    assert s["anomalias"] == 1


def test_simbolo_pegado_al_numero_solo_cuenta_en_paginas_ocr():
    texto = "ARTÍCULO 12. Uno.\nARTÍCULO 13%. Dos.\n\f\nPARÁGRAFO 4 %: Tres.\n"
    assert secuencia_articulos(texto)["simbolos_sospechosos"] == 2
    solo_pagina_2 = secuencia_articulos(texto, paginas_ocr={2})
    assert solo_pagina_2["simbolos_sospechosos"] == 1
    assert solo_pagina_2["ejemplos_simbolos"] == ["PARÁGRAFO 4 %"]
    # Un ordinal legítimo no es sospechoso.
    assert (
        secuencia_articulos("ARTÍCULO 2°. Texto.\nArtículo 3o. Otro.")["simbolos_sospechosos"] == 0
    )


def test_numeracion_con_puntos_y_cita_en_frase_no_son_anomalias():
    texto = (
        "ARTÍCULO 2.2.3.2.4 Déficit.\nARTÍCULO 2.2.3.2.5 Superávit.\n"
        "según el artículo 8 de la Ley 810 de 2003\n"
    )
    s = secuencia_articulos(texto)
    assert s["articulos"] == 2
    assert s["anomalias"] == 0


def test_paragrafos_repetidos_dentro_de_un_articulo():
    texto = "ARTÍCULO 1. A.\nPARÁGRAFO 1. x\nPARÁGRAFO 1. y\nARTÍCULO 2. B.\nPARÁGRAFO 1. z\n"
    assert secuencia_articulos(texto)["paragrafos_no_monotonos"] == 1


def test_caida_de_texto_excluye_portada_final_y_paginas_vacias():
    resultado = caida_texto([50, 1000, 900, 120, 0, 950, 40])
    assert resultado["paginas"] == [4]
    assert resultado["vacias"] == [5]
    assert caida_texto([10, 20])["paginas"] == []


def test_imagenes_grandes_en_paginas_digitales():
    fitz = pytest.importorskip("fitz")
    pdf = fitz.open()
    imagen = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
    imagen.clear_with(200)
    png = imagen.tobytes("png")
    tabla = pdf.new_page(width=600, height=800)
    tabla.insert_text((50, 50), "Perjuicios morales: " + "x" * 120)
    tabla.insert_image(fitz.Rect(50, 100, 550, 500), stream=png)  # 42 % del área
    completa = pdf.new_page(width=600, height=800)
    completa.insert_image(completa.rect, stream=png)
    completa.insert_text((50, 50), "texto oculto " * 30)
    escaneada = pdf.new_page(width=600, height=800)
    escaneada.insert_image(escaneada.rect, stream=png)
    marcadas = imagenes_en_paginas_digitales(pdf, paginas_ocr={3})
    assert [m["pagina"] for m in marcadas] == [1, 2]
    assert marcadas[0]["fraccion_imagen"] == pytest.approx(500 * 400 / (600 * 800))
    assert marcadas[1]["pagina_completa"]
    assert tablas_imagen_sospechosas(marcadas) == [1]
