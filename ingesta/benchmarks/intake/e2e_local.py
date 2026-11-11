"""FASE 5: prueba de punta a punta LOCAL del intake (Chroma local, embeddings falsos).

Limitaciones declaradas: sin Tesseract el OCR de los PDF del corpus se sirve desde
la caché sembrada de runA (sembrar_cache_ocr.py) y un escaneo NUEVO no puede
pasar por OCR; sin Ollama los embeddings son falsos (colección bench_intake_*), así
que la recuperación vectorial no se mide: se informa un proxy BM25.

Requiere un Chroma local ya en marcha (chroma run --host 127.0.0.1 --port PUERTO).

    python -X utf8 e2e_local.py --trabajo C:/Users/Migue/herramientas/e2e2 --raw C:/Users/Migue/r \
        --puerto 8011 --salida resultados/e2e
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
INGESTA = BASE.parents[1]
REPO = INGESTA.parent
NUEVOS = {
    "a4be": "sentencia digital",
    "a7c0": "sentencia escaneada",
    "1ee0": "norma escaneada",
    "c8e5": "norma digital",
    "d6b7": "rojo escaneado (Turbo)",
}
ESPERADO_NUEVOS = {
    "a4be": "publicado",
    "a7c0": "publicado",
    "1ee0": "publicado",
    "c8e5": "publicado",
    "d6b7": "revision_humana",
}


MARCADOR = ".e2e_intake"


def validar_trabajo(trabajo, protegidas):
    """Antes de borrar --trabajo: sin solapes con repo, raw ni referencias, y con marcador.

    Revisión: un --trabajo mal puesto (p. ej. data/documents o un ancestro de raw)
    se habría borrado entero. Solo se borra una carpeta creada por este arnés.
    """
    trabajo = Path(trabajo).resolve()
    for ruta in protegidas:
        ruta = Path(ruta).resolve()
        if trabajo == ruta or trabajo.is_relative_to(ruta) or ruta.is_relative_to(trabajo):
            raise SystemExit(f"--trabajo {trabajo} se solapa con {ruta}; elige otra carpeta")
    if trabajo.exists() and any(trabajo.iterdir()) and not (trabajo / MARCADOR).exists():
        raise SystemExit(f"--trabajo {trabajo} no está vacío ni lo creó este arnés; no se borra")


def sh256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class E2E:
    def __init__(self, args):
        self.a = args
        self.t = args.trabajo
        self.py = sys.executable
        self.filas = []
        mapping = BASE.parent / "ocr_referencia/entrada/descomprimido/mapping.csv"
        self.slug = {r["sha256"]: r["slug"] for r in csv.DictReader(mapping.open(encoding="utf-8"))}

    def intake(self, inbox, *extra, coleccion="bench_intake_e2e", esperar=True):
        cmd = [
            self.py,
            "-X",
            "utf8",
            "-m",
            "ingest.offline",
            "intake",
            "--collection",
            coleccion,
            "--inbox",
            str(inbox),
            "--once",
            "--fake-embeddings",
            "--raw-root",
            str(self.t / "raw"),
            "--layers-root",
            str(self.t / "capas"),
            "--state",
            str(self.t / "estado"),
            "--cache",
            str(self.t / "cache"),
            "--port",
            str(self.a.puerto),
            *extra,
        ]
        # Sin Tesseract en el PATH: un escaneo nuevo no puede pasar por OCR.
        env = {
            **os.environ,
            "PATH": os.pathsep.join(
                p for p in os.environ["PATH"].split(os.pathsep) if "tesseract" not in p.lower()
            ),
        }
        if not esperar:
            return subprocess.Popen(
                cmd,
                cwd=INGESTA,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        inicio = time.monotonic()
        r = subprocess.run(
            cmd, cwd=INGESTA, env=env, capture_output=True, text=True, encoding="utf-8"
        )
        fichas = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        return r.returncode, fichas, time.monotonic() - inicio, r.stdout + r.stderr

    def coleccion(self, nombre="bench_intake_e2e"):
        import chromadb

        return chromadb.HttpClient(host="127.0.0.1", port=self.a.puerto).get_collection(nombre)

    def ids_doc(self, doc_id, nombre="bench_intake_e2e"):
        return self.coleccion(nombre).get(where={"doc_id": doc_id}, include=[])["ids"]

    def caso(self, nombre, esperado, obtenido, ok, segundos=None, detalle=""):
        self.filas.append(
            {
                "caso": nombre,
                "esperado": esperado,
                "obtenido": obtenido,
                "ok": bool(ok),
                "segundos": round(segundos, 1) if segundos else None,
                "detalle": detalle,
            }
        )
        print(("OK  " if ok else "FALLA ") + nombre + " | " + obtenido, flush=True)

    def preparar(self):
        validar_trabajo(self.t, [REPO, self.a.raw, self.a.capas_referencia])
        if self.t.exists():
            shutil.rmtree(self.t)
        for d in ("ib_base", "ib_nuevos", "raw"):
            (self.t / d).mkdir(parents=True)
        (self.t / MARCADOR).write_text("Carpeta desechable de e2e_local.py\n", encoding="utf-8")
        subprocess.run(
            [
                self.py,
                "-I",
                "-X",
                "utf8",
                str(BASE.parent / "ocr_referencia/sembrar_cache_ocr.py"),
                "--referencia",
                str(self.a.capas_referencia),
                "--cache",
                str(self.t / "cache"),
            ],
            check=True,
            cwd=INGESTA,
        )
        vistos = set()
        self.pdf = {}
        for p in sorted(self.a.raw.rglob("*.pdf")):
            h = sh256(p)
            if h in vistos:
                continue
            vistos.add(h)
            self.pdf[h] = p
            corto = self.slug[h][-4:]
            nombre = self.slug[h][:40] + ".pdf"
            if corto in NUEVOS:
                shutil.copy2(p, self.t / "ib_nuevos" / nombre)
            else:
                shutil.copy2(p, self.t / "ib_base" / nombre)
                (self.t / "ib_base" / (nombre + ".meta.json")).write_text(
                    json.dumps({"categoria": p.parent.name}), encoding="utf-8"
                )

    def bm25(self, nombre):
        salida = self.t / f"bm25_{nombre}.json"
        subprocess.run(
            [
                self.py,
                "-I",
                "-X",
                "utf8",
                str(BASE / "recuperacion_bm25.py"),
                "--coleccion",
                "bench_intake_e2e",
                "--puerto",
                str(self.a.puerto),
                "--ground-truth",
                str(self.a.ground_truth),
                "--raw",
                str(self.a.raw),
                "--salida",
                str(salida),
            ],
            check=True,
            cwd=INGESTA,
            capture_output=True,
        )
        return salida

    def correr(self):
        self.preparar()
        resultado = {}
        # 1. Base
        rc, fichas, s, _ = self.intake(self.t / "ib_base")
        resultado["base"] = {
            "codigo": rc,
            "segundos": s,
            "decisiones": _contar(fichas),
            "chunks_coleccion": self.coleccion().count(),
        }
        antes = self.bm25("antes")
        # 2. Nuevos
        rc, fichas, s, _ = self.intake(self.t / "ib_nuevos")
        resultado["nuevos"] = []
        for f in fichas:
            corto = self.slug[f["doc_id"]][-4:]
            obtenido = f["estado"]
            self.caso(
                f"nuevo: {NUEVOS[corto]} ({corto})",
                ESPERADO_NUEVOS[corto],
                f"{obtenido}; {'; '.join(f['motivos'])}".strip("; "),
                obtenido == ESPERADO_NUEVOS[corto],
                sum(v for k, v in f["tiempos"].items() if k != "total"),
            )
            resultado["nuevos"].append(
                {
                    "doc": corto,
                    **{k: f[k] for k in ("decision", "estado", "motivos", "avisos", "tiempos")},
                }
            )
        despues = self.bm25("despues")
        claves = [self.pdf[h].name for h in self.pdf if self.slug[h][-4:] in NUEVOS]
        comp = subprocess.run(
            [
                self.py,
                "-I",
                "-X",
                "utf8",
                str(BASE / "recuperacion_bm25.py"),
                "--comparar",
                str(antes),
                str(despues),
                "--nuevos",
                *claves,
            ],
            check=True,
            cwd=INGESTA,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        resultado["bm25"] = json.loads(comp.stdout)
        self.casos_robustez(resultado)
        return resultado

    def casos_robustez(self, resultado):
        import fitz

        t = self.t
        gieseken = next(h for h in self.pdf if self.slug[h].endswith("a4be"))
        norma = next(h for h in self.pdf if self.slug[h].endswith("c8e5"))
        # 3. Copias
        ib = t / "ib_copias"
        ib.mkdir()
        shutil.copy2(self.pdf[gieseken], ib / "copia_exacta.pdf")
        rc, fichas, s, _ = self.intake(ib)
        self.caso(
            "copia exacta (mismos bytes)",
            "sin trabajo nuevo",
            f"{fichas[0].get('resultado')}; doc_id igual: {fichas[0]['doc_id'] == gieseken}",
            fichas[0].get("resultado") == "sin cambios" and fichas[0]["doc_id"] == gieseken,
            s,
        )
        (ib / "copia_exacta.pdf").rename(ib / "nombre totalmente distinto.pdf")
        rc, fichas, s, _ = self.intake(ib)
        self.caso(
            "copia renombrada",
            "mismo doc_id, sin trabajo nuevo",
            f"{fichas[0].get('resultado')}; doc_id igual: {fichas[0]['doc_id'] == gieseken}",
            fichas[0]["doc_id"] == gieseken and fichas[0].get("resultado") == "sin cambios",
            s,
        )
        ibm = t / "ib_modificada"
        ibm.mkdir()
        with fitz.open(self.pdf[norma]) as d:
            d[-1].insert_text((72, 60), "Copia de trabajo", fontsize=8)
            d.save(ibm / "norma_modificada.pdf")
        rc, fichas, s, _ = self.intake(ibm)
        f = fichas[0]
        self.caso(
            "copia modificada",
            "cuasi-duplicado → revisión",
            f"{f['estado']}; {'; '.join(f['motivos'])}",
            f["estado"] == "revision_humana" and any("versión nueva" in m for m in f["motivos"]),
            s,
        )
        # 4. Escaneo degradado (sin Tesseract no hay OCR posible)
        ibd = t / "ib_degradado"
        ibd.mkdir()
        with fitz.open(self.pdf[gieseken]) as d, fitz.open() as nuevo:
            for pagina in d.pages(0, 4):
                pix = pagina.get_pixmap(dpi=70, colorspace=fitz.csGRAY)
                pagina_nueva = nuevo.new_page(width=pagina.rect.width, height=pagina.rect.height)
                pagina_nueva.insert_image(pagina_nueva.rect, pixmap=pix, rotate=0)
                pagina_nueva.set_rotation(0)
            nuevo.save(ibd / "escaneo_degradado.pdf")
        rc, fichas, s, _ = self.intake(ibd)
        f = fichas[0]
        self.caso(
            "escaneo degradado (70 dpi, sin capa de texto)",
            "revisión o rechazo, nunca aceptado",
            f"{f['estado']}; {'; '.join(f['motivos'])}",
            f["estado"] in {"revision_humana", "rechazado"},
            s,
            "Sin Tesseract: el OCR falla y la política no acepta. Giro y ruido con OCR real: PENDIENTE.",
        )
        # 5. Entradas hostiles
        ibh = t / "ib_hostil"
        ibh.mkdir()
        with fitz.open() as d:
            d.new_page()
            d.save(ibh / "en_blanco.pdf")
        with fitz.open() as d:
            d.new_page().insert_text((72, 72), "Texto confidencial " * 40)
            d.save(
                ibh / "cifrado.pdf", encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"
            )
        datos = self.pdf[norma].read_bytes()
        (ibh / "truncado.pdf").write_bytes(datos[: len(datos) // 2])
        (ibh / "no_es_pdf.pdf").write_bytes(b"MZ\x90\x00" + os.urandom(4000))
        with fitz.open() as d:
            for _ in range(1001):
                d.new_page(width=200, height=200)
            d.save(ibh / "desmesurado.pdf")
        raro = "..‮fdp.exe ‎nombre\tcon controles" + "x" * 150 + ".pdf"
        try:
            shutil.copy2(self.pdf[norma], ibh / raro)
        except OSError:
            raro = None
        rc, fichas, s, _ = self.intake(ibh)
        for nombre_archivo, etiqueta in (
            ("en_blanco.pdf", "PDF en blanco"),
            ("cifrado.pdf", "PDF cifrado"),
            ("truncado.pdf", "PDF truncado"),
            ("no_es_pdf.pdf", "no PDF con .pdf"),
            ("desmesurado.pdf", "PDF desmesurado (1001 páginas)"),
        ):
            h = sh256(ibh / nombre_archivo)
            f = next(x for x in fichas if x["doc_id"] == h)
            self.caso(
                etiqueta,
                "rechazado con motivo",
                f"{f['estado']}; {'; '.join(f['motivos'])}",
                f["estado"] == "rechazado" and f["motivos"],
                None,
            )
        if raro:
            h = sh256(ibh / raro)
            f = next(x for x in fichas if x["doc_id"] == h)
            copias = [p.name for p in (t / "raw").rglob("*") if p.is_file()]
            seguro = all(".." not in n and "‮" not in n and "\t" not in n for n in copias)
            self.caso(
                "nombre hostil (.., RTL, tabulador, 190 caracteres)",
                "rechazado con motivo (o neutralizado)",
                f"{f['estado']}: identidad por hash; copia en raw con nombre seguro: {seguro}",
                seguro,
                None,
                "No se rechaza: el nombre no participa en la identidad ni en rutas.",
            )
        # 6. Dos procesos a la vez
        ibc = t / "ib_concurrente"
        ibc.mkdir()
        shutil.copy2(
            next(p for h, p in self.pdf.items() if self.slug[h].endswith("ffab")), ibc / "a.pdf"
        )
        p1 = self.intake(ibc, esperar=False)
        time.sleep(0.5)
        p2 = self.intake(ibc, esperar=False)
        o1, o2 = p1.communicate(timeout=900)[0], p2.communicate(timeout=900)[0]
        h = sh256(ibc / "a.pdf")
        ids = self.ids_doc(h)
        unicos = len(set(ids)) == len(ids)
        self.caso(
            "dos intakes a la vez",
            "uno espera o falla limpio, sin corrupción",
            f"códigos {p1.returncode}/{p2.returncode}; chunks {len(ids)} sin duplicados: {unicos}",
            unicos and {p1.returncode, p2.returncode} <= {0, 2, 3, 4},
            None,
            (o1[-200:] + " || " + o2[-200:]).replace("\n", " "),
        )
        # 7. kill -9 a mitad de embeddings
        ibk = t / "ib_kill"
        ibk.mkdir()
        grande = next(p for h, p in self.pdf.items() if self.slug[h].endswith("19a7"))
        shutil.copy2(grande, ibk / "grande.pdf")
        hk = sh256(grande)
        proceso = self.intake(ibk, esperar=False)
        ficha = t / "estado" / "intake" / f"{hk}.json"
        interrumpido = False
        limite = time.monotonic() + 600
        while proceso.poll() is None and time.monotonic() < limite:
            try:
                if json.loads(ficha.read_text(encoding="utf-8")).get("estado") == "publicando":
                    proceso.kill()
                    interrumpido = True
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.01)
        proceso.wait()
        rc, fichas, s, _ = self.intake(ibk)
        # La línea de resumen no trae la lista de chunks: se lee la ficha guardada.
        esperados = json.loads(ficha.read_text(encoding="utf-8")).get("chunks") or []
        ids = self.ids_doc(hk)
        staging = self.ids_doc(hk, "bench_intake_e2e__staging")
        ok = sorted(ids) == sorted(c["id"] for c in esperados) and not staging
        self.caso(
            "kill -9 durante publicación y reintento",
            "sin duplicados ni huérfanos",
            f"interrumpido en 'publicando': {interrumpido}; reintento {fichas[0]['estado']}; "
            f"chunks {len(ids)}/{len(esperados)}; preparación {len(staging)}",
            ok and interrumpido,
            s,
            "Si no se alcanzó a interrumpir, el caso queda cubierto solo por el test unitario.",
        )
        # 8. retire
        antes = len(self.ids_doc(hk))
        inicio = time.monotonic()
        r = subprocess.run(
            [
                self.py,
                "-X",
                "utf8",
                "-m",
                "ingest.offline",
                "retire",
                hk,
                "--collection",
                "bench_intake_e2e",
                "--state",
                str(t / "estado"),
                "--layers-root",
                str(t / "capas"),
                "--cache",
                str(t / "cache"),
                "--port",
                str(self.a.puerto),
                "--fake-embeddings",
            ],
            cwd=INGESTA,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        despues = len(self.ids_doc(hk))
        self.caso(
            "retire de un documento publicado",
            "desaparece de Chroma",
            f"código {r.returncode}; chunks {antes} → {despues}",
            r.returncode == 0 and despues == 0,
            time.monotonic() - inicio,
            (r.stdout + r.stderr)[-200:],
        )
        # Nombres de producción rechazados
        for nombre in ("v1", "atlas_v1", "rag_playas", "rag_playas_magdalena", "atlas_otra"):
            rc, _, _, salida = self.intake(t / "ib_copias", coleccion=nombre)
            self.caso(
                f"colección protegida «{nombre}»",
                "rechazo (código 3) antes de leer el inbox",
                f"código {rc}",
                rc == 3,
                None,
                salida[-160:].replace("\n", " "),
            )


def _contar(fichas):
    from collections import Counter

    return dict(Counter(f"{f['decision']}/{f['estado']}" for f in fichas))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trabajo", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--puerto", type=int, default=8011)
    parser.add_argument(
        "--capas-referencia",
        type=Path,
        default=BASE.parent / "ocr_referencia/trabajo/corridas/runA/pdf/capas",
    )
    parser.add_argument("--ground-truth", type=Path, default=BASE / "trabajo/gt_v02.json")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    e2e = E2E(args)
    resultado = e2e.correr()
    resultado["casos"] = e2e.filas
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "e2e.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {"base": resultado["base"], "bm25": resultado["bm25"]}, ensure_ascii=False, indent=1
        )
    )


if __name__ == "__main__":
    main()
