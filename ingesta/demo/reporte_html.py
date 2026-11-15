"""Genera un reporte HTML estático y autocontenido de una corrida real del intake.

Lee las fichas (``<estado>/intake/*.json``) y, opcionalmente, el resultado de la
E2E (``e2e_aws.json``). Solo muestra metadatos: nombre del documento, fases,
decisión, motivos, avisos y tiempos; nunca el texto de los documentos, así que no
puede reproducir datos de particulares de las tablas. Sin enlaces externos.

    python reporte_html.py --fichas <dir con fichas> [--e2e e2e_aws.json] --salida reporte_demo.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path

FASES = [
    ("validacion", "Validación"),
    ("bronze", "Bronce (texto/OCR)"),
    ("silver", "Silver (limpieza y metadatos)"),
    ("gold", "Gold (fragmentos)"),
    ("politica", "Política"),
    ("embeddings", "Embeddings"),
    ("preparacion", "Preparación"),
    ("publicacion", "Publicación"),
]
COLOR = {
    "publicado": ("#1b7f3b", "Publicado"),
    "revision_humana": ("#b26a00", "A revisión humana"),
    "rechazado": ("#b3261e", "Rechazado"),
    "retirado": ("#5f6368", "Retirado"),
}
CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1d1f23}
main{max-width:1000px;margin:0 auto;padding:24px 16px}
h1{font-size:1.6rem;margin:.2rem 0}h2{font-size:1.2rem;margin-top:2rem}
.nota{background:#fff8e1;border-left:4px solid #e0a800;padding:10px 14px;border-radius:6px}
.doc{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:14px 16px;margin:14px 0}
.etiqueta{display:inline-block;color:#fff;border-radius:999px;padding:2px 10px;font-size:.85rem}
.fases{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.fase{background:#eef2f7;border-radius:6px;padding:4px 8px;font-size:.85rem}
table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #dfe3e8;padding:6px 8px;text-align:left;font-size:.9rem}
th{background:#eef2f7}.ok{color:#1b7f3b}.mal{color:#b3261e}
"""


def e(texto):
    return html.escape(str(texto))


def tarjeta(ficha):
    color, etiqueta = COLOR.get(ficha.get("estado"), ("#5f6368", ficha.get("estado")))
    rutas = ficha.get("rutas") or {}
    nombre = Path(rutas.get("inbox") or ficha.get("doc_id", "")).name
    tiempos = ficha.get("tiempos") or {}
    fases = "".join(
        f'<span class="fase">{e(t)}: {tiempos[c]:.1f} s</span>' for c, t in FASES if c in tiempos
    )
    motivos = "".join(f"<li>{e(m)}</li>" for m in ficha.get("motivos") or [])
    avisos = "".join(f"<li>{e(a)}</li>" for a in ficha.get("avisos") or [])
    chunks = len(ficha.get("chunks") or [])
    return f"""<div class="doc">
<div><span class="etiqueta" style="background:{color}">{e(etiqueta)}</span>
<strong> {e(nombre)}</strong></div>
<div style="color:#5f6368;font-size:.85rem">Identidad (SHA-256): {e(str(ficha.get("doc_id"))[:16])}… ·
Decisión de la política: {e(ficha.get("decision"))} · Fragmentos: {chunks} ·
Total: {tiempos.get("total", 0):.1f} s</div>
<div class="fases">{fases}</div>
{"<p><strong>Motivos:</strong></p><ul>" + motivos + "</ul>" if motivos else ""}
{"<p><strong>Advertencias:</strong></p><ul>" + avisos + "</ul>" if avisos else ""}
</div>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fichas", type=Path, required=True)
    parser.add_argument("--e2e", type=Path)
    parser.add_argument("--titulo", default="Ingreso autónomo de documentos — corrida real")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    fichas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.fichas.glob("*.json"))]
    fichas.sort(key=lambda f: f.get("fecha", ""))
    partes = [
        f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>Reporte del intake</title>"
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>{e(args.titulo)}</h1>",
        f"<p>Generado el {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC a partir de las fichas "
        "reales del worker. OCR con Tesseract y embeddings de Ollama en CPU.</p>",
        "<p class='nota'>Las cifras de calidad comparan con otro OCR, no con una transcripción "
        "humana, y nada de esto está validado por abogados. Solo se muestran metadatos de cada "
        "documento: nunca su texto.</p>",
        "<h2>Documentos procesados</h2>",
        *[tarjeta(f) for f in fichas],
    ]
    if args.e2e and args.e2e.exists():
        r = json.loads(args.e2e.read_text(encoding="utf-8"))
        filas = "".join(
            f"<tr><td>{e(c['caso'])}</td><td>{e(c['esperado'])}</td><td>{e(c['obtenido'][:160])}</td>"
            f"<td>{'' if c.get('segundos') is None else c['segundos']}</td>"
            f"<td class='{'ok' if c['ok'] else 'mal'}'>{'sí' if c['ok'] else 'NO'}</td></tr>"
            for c in r.get("casos", [])
        )
        partes += [
            "<h2>Pruebas de robustez (corrida real)</h2>",
            "<table><tr><th>Caso</th><th>Esperado</th><th>Obtenido</th><th>s</th><th>¿Cumple?</th></tr>",
            filas,
            "</table>",
        ]
        rec = r.get("recuperacion") or {}
        if rec:
            partes.append(
                "<h2>Recuperación (buscador real de la aplicación, sin LLM)</h2><table>"
                "<tr><th>Preguntas</th><th>n</th><th>hit@4 antes → después</th>"
                "<th>MRR antes → después</th></tr>"
            )
            for nombre, x in rec.items():
                partes.append(
                    f"<tr><td>{e(nombre)}</td><td>{x['n']}</td>"
                    f"<td>{x['hit4_antes']:.2f} → {x['hit4_despues']:.2f}</td>"
                    f"<td>{x['mrr_antes']:.2f} → {x['mrr_despues']:.2f}</td></tr>"
                )
            partes.append("</table>")
    partes.append("</main></body></html>")
    args.salida.write_text("\n".join(partes), encoding="utf-8")
    print("Reporte:", args.salida)


if __name__ == "__main__":
    main()
