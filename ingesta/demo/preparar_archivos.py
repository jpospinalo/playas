"""Prepara los PDF del demo en ingesta/demo/archivos/ (no versionados).

- «Decreto 474 de 2015 - concesiones portuarias.pdf»: escaneado real del corpus
  (3 páginas OCR, ~16 fragmentos), corto para procesarse en vivo.
- «Escaneo degradado.pdf»: 4 páginas de una sentencia a 70 dpi, giradas 2° y con
  ruido: el intake debe enviarlo a revisión o rechazarlo, nunca publicarlo.
- «Documento cifrado.pdf»: PDF con contraseña: se rechaza con motivo.

    python preparar_archivos.py --raw <ruta a data/documents/raw>
Requiere PyMuPDF (pip install pymupdf).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SUFIJOS = AQUI.parent / "benchmarks" / "demo_aws" / "sufijos_raw.json"


def buscar(raw, sufijo):
    mapa = json.loads(SUFIJOS.read_text(encoding="utf-8"))
    for p in sorted(raw.rglob("*.pdf")):
        if mapa.get(hashlib.sha256(p.read_bytes()).hexdigest()) == sufijo:
            return p
    raise SystemExit(f"No encontré el documento {sufijo} en {raw}")


def degradar(origen, destino):
    import fitz

    rnd = random.Random(20261110)
    with fitz.open(origen) as d, fitz.open() as nuevo:
        for pagina in d.pages(0, 4):
            pix = pagina.get_pixmap(dpi=70, colorspace=fitz.csGRAY)
            for _ in range(pix.width * pix.height // 25):
                pix.set_pixel(
                    rnd.randrange(pix.width), rnd.randrange(pix.height), (rnd.randrange(256),)
                )
            img = fitz.Pixmap(pix, 0) if pix.alpha else pix
            girada = fitz.open()
            tmp = girada.new_page(width=pagina.rect.width, height=pagina.rect.height)
            tmp.insert_image(tmp.rect, pixmap=img)
            final = tmp.get_pixmap(matrix=fitz.Matrix(1, 1).prerotate(2), colorspace=fitz.csGRAY)
            hoja = nuevo.new_page(width=final.width, height=final.height)
            hoja.insert_image(hoja.rect, pixmap=final)
        nuevo.save(destino)


def main():
    import fitz

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    args = parser.parse_args()
    salida = AQUI / "archivos"
    salida.mkdir(exist_ok=True)
    shutil.copy2(
        buscar(args.raw, "1ee0"), salida / "Decreto 474 de 2015 - concesiones portuarias.pdf"
    )
    degradar(buscar(args.raw, "a4be"), salida / "Escaneo degradado.pdf")
    with fitz.open() as d:
        d.new_page().insert_text((72, 72), "Documento de prueba con contraseña. " * 20)
        d.save(
            salida / "Documento cifrado.pdf",
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="demo",
            user_pw="demo",
        )
    for p in sorted(salida.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
