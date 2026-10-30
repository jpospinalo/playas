"""Genera el SQL (Postgres) que lleva una base con el esquema de `main` al
esquema actual de los modelos, SOLO agregando tablas nuevas.

No hay Alembic en el proyecto: el backend crea lo que falte con
``Base.metadata.create_all`` al arrancar, pero ``create_all`` nunca altera una
tabla existente. Por eso esta migración solo cubre tablas nuevas; si algún día
un modelo agrega una columna a una tabla que ya existe, hay que escribir el
``ALTER TABLE ... ADD COLUMN`` a mano.

Uso (desde rag/):
    PYTHONPATH=backend uv run python infrastructure/migrations/generar_sql.py \\
        infrastructure/migrations/2026-10-30_ejercicio_validacion
"""

from __future__ import annotations

import pathlib
import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from rag.api.models import Base

# Tablas que ya existen en `main` (y, se supone, en producción).
TABLAS_MAIN = {"users", "conversations", "messages", "feedback", "message_feedback"}

CABECERA = """-- {titulo}
-- Generado por infrastructure/migrations/generar_sql.py a partir de
-- rag/backend/rag/api/models.py. No editar a mano: regenerar.
--
-- Solo {accion} las {n} tablas del ejercicio de validación (panel, cuentas,
-- evaluación, premios, aviso de datos). No toca users, conversations,
-- messages, feedback ni message_feedback.
"""


def main(destino: pathlib.Path) -> None:
    dialecto = postgresql.dialect()
    nuevas = [t for t in Base.metadata.sorted_tables if t.name not in TABLAS_MAIN]
    up = [
        CABECERA.format(titulo="Migración de subida", accion="crea", n=len(nuevas)),
        "-- Idempotente: usa IF NOT EXISTS, se puede correr dos veces.\n",
        "BEGIN;\n",
    ]
    for t in nuevas:
        up.append(str(CreateTable(t, if_not_exists=True).compile(dialect=dialecto)).strip() + ";\n")
        for i in sorted(t.indexes, key=lambda i: i.name or ""):
            up.append(
                str(CreateIndex(i, if_not_exists=True).compile(dialect=dialecto)).strip() + ";\n"
            )
    up.append("COMMIT;\n")
    down = [
        CABECERA.format(titulo="Vuelta atrás", accion="borra", n=len(nuevas)),
        "-- OJO: borra los datos guardados en esas tablas (cuentas del ejercicio,\n"
        "-- calificaciones, validaciones, premios). Sacar copia antes.\n"
        "-- RESTRICT (no CASCADE): si algo inesperado depende de ellas, falla en\n"
        "-- vez de borrar de más.\n",
        "BEGIN;\n",
    ]
    for t in reversed(nuevas):
        down.append(f"DROP TABLE IF EXISTS {t.name} RESTRICT;\n")
    down.append("COMMIT;\n")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "up.sql").write_text("\n".join(up), encoding="utf-8")
    (destino / "down.sql").write_text("\n".join(down), encoding="utf-8")
    print(f"{len(nuevas)} tablas nuevas: {', '.join(t.name for t in nuevas)}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
