"""Resume en lenguaje claro la ficha del último documento procesado (se ejecuta en el worker)."""

import json
from pathlib import Path

fichas = sorted(
    Path("/var/lib/atlas/estado/intake").glob("*.json"), key=lambda p: p.stat().st_mtime
)
f = json.loads(fichas[-1].read_text(encoding="utf-8"))
nombres = {
    "validacion": "validación",
    "bronze": "bronce (texto/OCR)",
    "silver": "silver (limpieza)",
    "gold": "gold (fragmentos)",
    "politica": "política",
    "embeddings": "embeddings",
    "preparacion": "preparación",
    "publicacion": "publicación",
}
estado = {
    "publicado": "PUBLICADO",
    "revision_humana": "A REVISIÓN HUMANA (no entra)",
    "rechazado": "RECHAZADO (no entra)",
}.get(f["estado"], f["estado"])
t = f.get("tiempos") or {}
print("  Documento:", Path((f.get("rutas") or {}).get("inbox") or "").name)
print("  Resultado:", estado, "| fragmentos:", len(f.get("chunks") or []))
print(
    "  Fases:",
    " -> ".join(f"{n} {t[c]:.1f}s" for c, n in nombres.items() if c in t),
    f"| total {t.get('total', 0):.1f}s",
)
for m in f.get("motivos") or []:
    print("  Motivo:", m)
for a in f.get("avisos") or []:
    print("  Aviso:", a)
