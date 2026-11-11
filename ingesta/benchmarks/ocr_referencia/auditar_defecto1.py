"""Audita las 1.224 páginas sin OCR nuevo ni cambios a la normalización.

Compara bytes de bronce por página y prueba el ordenador de palabras sin
sustituciones contra get_text('text', sort=True), incluso en páginas OCR.
Ejecutar con python -I -X utf8 desde la raíz del repositorio.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1]))
sys.path.insert(0, str(BASE))

from ingest.offline.extract import SUPERINDICES, _PalabrasPagina, sha256_file  # noqa: E402


def diferencias_pareadas(resultados):
    """Mismos documentos remuestreados para antes y después; tasas micro."""
    from evaluar_fase5 import agregar
    from fiabilidad import calibracion_existente

    result = {
        "semilla": 20261110,
        "repeticiones": 2000,
        "sentido": "despues menos antes",
        "calibracion": calibracion_existente(),
        "conjuntos": {},
    }
    for name in ("ajuste", "validacion"):
        data = json.loads((resultados / f"{name}_digital.json").read_bytes())
        differences = []
        for a, b in zip(data["filas"]["antes"], data["filas"]["despues"], strict=True):
            assert (a["slug"], a["pagina"]) == (b["slug"], b["pagina"])
            delta = {"slug": a["slug"]}
            for denominator in ("ref_c", "ref_p", "crit_ref", "num_ref"):
                assert a[denominator] == b[denominator]
                delta[denominator] = a[denominator]
            for numerator in ("ed_c", "ed_p", "crit_ok", "num_ok"):
                delta[numerator] = b[numerator] - a[numerator]
            differences.append(delta)
        result["conjuntos"][name] = agregar(differences)
    return result


def auditar(entrada, antes, despues):
    paths = {}
    for path in sorted(entrada.rglob("*.pdf")):
        paths.setdefault(sha256_file(path), path)
    counts = Counter(documentos=len(paths))
    rows, examples = [], []
    for doc_id, path in sorted(paths.items()):
        old = (antes / "bronze" / (doc_id + ".txt")).read_bytes().split(b"\n\f\n")
        new = (despues / "bronze" / (doc_id + ".txt")).read_bytes().split(b"\n\f\n")
        meta = json.loads((antes / "bronze" / (doc_id + ".extraction.json")).read_bytes())
        new_meta = json.loads((despues / "bronze" / (doc_id + ".extraction.json")).read_bytes())
        assert meta["ocr_pages"] == new_meta["ocr_pages"]
        assert meta["ocr_failed_pages"] == new_meta["ocr_failed_pages"]
        ocr = set(meta["ocr_pages"]) | set(meta["ocr_failed_pages"])
        with fitz.open(path) as pdf:
            assert len(pdf) == len(old) == len(new)
            for number, page in enumerate(pdf, 1):
                baseline = page.get_text("text", sort=True)
                words = page.get_text("words", flags=fitz.TEXTFLAGS_TEXT)
                plain = page.get_text("text", sort=True, textpage=_PalabrasPagina(page, words))
                data = page.get_text("dict", sort=True, flags=fitz.TEXTFLAGS_TEXT)
                rebuilt = "".join(
                    "".join(s["text"] for s in line["spans"]) + "\n"
                    for b in data["blocks"]
                    for line in b["lines"]
                )
                spans = [
                    s
                    for b in data["blocks"]
                    for line in b["lines"]
                    for s in line["spans"]
                    if s["flags"] & 1 and re.fullmatch(r"[0-9]+", s["text"].strip())
                ]
                is_ocr, changed = number in ocr, old[number - 1] != new[number - 1]
                a, b = old[number - 1].decode("utf-8"), new[number - 1].decode("utf-8")
                only = len(a) == len(b) and all(
                    x == y or (x in "0123456789" and x.translate(SUPERINDICES) == y)
                    for x, y in zip(a, b, strict=True)
                )
                row = {
                    "doc_id": doc_id,
                    "pagina": number,
                    "ocr": is_ocr,
                    "spans_numericos": len(spans),
                    "cambio": changed,
                    "ordenador_identico": plain.encode() == baseline.encode(),
                    "dict_identico": rebuilt.encode() == baseline.encode(),
                    "solo_sustituciones_1a1": only,
                }
                rows.append(row)
                counts["paginas"] += 1
                counts["ordenador_identicas"] += row["ordenador_identico"]
                counts["dict_no_identicas"] += not row["dict_identico"]
                counts["ocr" if is_ocr else "digitales"] += 1
                counts["ocr_cambiadas" if is_ocr else "digitales_cambiadas"] += changed
                if not is_ocr:
                    assert a == unicodedata.normalize("NFC", baseline)
                    counts["spans_numericos_digitales"] += len(spans)
                    counts["digitos_detectados"] += sum(len(s["text"].strip()) for s in spans)
                    counts["digitos_sustituidos"] += sum(x != y for x, y in zip(a, b, strict=True))
                    if not spans:
                        counts["digitales_sin_candidatos"] += 1
                        assert not changed
                assert row["ordenador_identico"] and only
                assert not (is_ocr and changed)
                if changed:
                    for m in re.finditer(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", b):
                        if a[m.start() : m.end()] == m[0]:
                            continue
                        examples.append(
                            {
                                "doc_id": doc_id,
                                "pagina": number,
                                "antes": a[max(0, m.start() - 35) : m.end() + 25],
                                "despues": b[max(0, m.start() - 35) : m.end() + 25],
                            }
                        )
    return {"recuentos": dict(counts), "paginas": rows, "ejemplos": examples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--antes", type=Path, required=True)
    parser.add_argument("--despues", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument(
        "--metricas", type=Path, help="Directorio con las dos evaluaciones de fase 5"
    )
    args = parser.parse_args()
    result = auditar(args.entrada, args.antes, args.despues)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["recuentos"], ensure_ascii=False))
    if args.metricas:
        paired = diferencias_pareadas(args.metricas)
        (args.metricas / "diferencias_pareadas.json").write_text(
            json.dumps(paired, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(json.dumps(paired["calibracion"], ensure_ascii=False))


if __name__ == "__main__":
    main()
