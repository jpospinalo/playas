"""Prueba de punta a punta REAL del intake (Linux): OCR con Tesseract, embeddings de
Ollama remoto (--allow-remote-ollama), Chroma local nuevo y colección atlas_demo_*.

Se ejecuta en una EC2 Linux con el repositorio clonado, Tesseract spa y un Chroma
local en 127.0.0.1:PUERTO. No usa la caché OCR sembrada ni embeddings falsos.

    python e2e_aws.py --trabajo ~/e2e --ollama http://IP:11434 --puerto 8000 \
        --ground-truth gt_v02.json --rag ~/playas/rag --salida resultados
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
INGESTA = AQUI.parents[1]
REPO = INGESTA.parent
RAW = REPO / "data" / "documents" / "raw"
COLECCION = "atlas_demo_e2e"  # se puede cambiar con --coleccion
MARCADOR = ".e2e_intake"
# Base reducida (presupuesto de embeddings en CPU): documentos con preguntas del
# ground truth y normas/sentencias cortas, más tres que la política envía a revisión.
BASE = [
    "d512",
    "19a7",
    "9523",
    "0be7",
    "922e",
    "c9b9",
    "cc7b",
    "d195",
    "e4a6",
    "5f39",
    "1cd3",
    "404e",
    "2880",
    "f07f",
    "00a7",
    "7c8c",
    "ce3c",
    "a44a",
]
NUEVOS = {
    "a4be": "sentencia digital",
    "a7c0": "sentencia escaneada",
    "c8e5": "norma digital",
    "d6b7": "control: rojo escaneado (Turbo)",
}
ESPERADO = {
    "a4be": "publicado",
    "a7c0": "publicado",
    "c8e5": "publicado",
    "d6b7": "revision_humana",
}


def sh256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def validar_trabajo(trabajo, protegidas):
    """Mismas barreras que el arnés local antes de borrar una carpeta de trabajo."""
    trabajo = Path(trabajo).resolve()
    for ruta in protegidas:
        ruta = Path(ruta).resolve()
        if trabajo == ruta or trabajo.is_relative_to(ruta) or ruta.is_relative_to(trabajo):
            raise SystemExit(f"--trabajo {trabajo} se solapa con {ruta}; elige otra carpeta")
    if trabajo.exists() and any(trabajo.iterdir()) and not (trabajo / MARCADOR).exists():
        raise SystemExit(f"--trabajo {trabajo} no está vacío ni lo creó este arnés; no se borra")


def preparar_coleccion(cliente, nombre, recrear=False):
    """La corrida exige una colección vacía; borrar requiere un nombre del arnés."""
    from chromadb.errors import NotFoundError

    if recrear and not nombre.startswith("atlas_demo_e2e"):
        raise SystemExit("--recrear-coleccion solo permite colecciones atlas_demo_e2e*")
    for candidata in (nombre, nombre + "__staging"):
        try:
            coleccion = cliente.get_collection(candidata)
        except NotFoundError:
            continue
        if recrear:
            cliente.delete_collection(candidata)
        elif coleccion.count():
            raise SystemExit(
                f"La colección {candidata} contiene datos; usa otra o --recrear-coleccion "
                "(solo atlas_demo_e2e*)"
            )


class E2E:
    def __init__(self, a):
        self.a, self.t, self.filas = a, a.trabajo, []
        mapa = json.loads((AQUI / "sufijos_raw.json").read_text(encoding="utf-8"))
        self.ruta = {}
        for p in RAW.rglob("*.pdf"):
            sufijo = mapa.get(sh256(p))
            if sufijo and sufijo not in self.ruta:
                self.ruta[sufijo] = p

    def intake(self, inbox, *extra, coleccion=None, esperar=True):
        coleccion = coleccion or COLECCION
        cmd = [
            sys.executable,
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
            "--ollama",
            self.a.ollama,
            "--allow-remote-ollama",
            *extra,
        ]
        if not esperar:
            return subprocess.Popen(
                cmd,
                cwd=INGESTA,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        inicio = time.monotonic()
        r = subprocess.run(cmd, cwd=INGESTA, capture_output=True, text=True)
        fichas = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        return r.returncode, fichas, time.monotonic() - inicio, r.stdout + r.stderr

    def coleccion(self, nombre=None):
        nombre = nombre or COLECCION
        import chromadb

        return chromadb.HttpClient(host="127.0.0.1", port=self.a.puerto).get_collection(nombre)

    def ids(self, doc_id, nombre=None):
        nombre = nombre or COLECCION
        return self.coleccion(nombre).get(where={"doc_id": doc_id}, include=[])["ids"]

    def ficha(self, doc_id):
        return json.loads(
            (self.t / "estado" / "intake" / f"{doc_id}.json").read_text(encoding="utf-8")
        )

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
        print(("OK    " if ok else "FALLA ") + nombre + " | " + obtenido, flush=True)

    def buzon(self, nombre, sufijos, lateral=False):
        ib = self.t / nombre
        ib.mkdir(parents=True, exist_ok=True)
        for s in sufijos:
            origen = self.ruta[s]
            shutil.copy2(origen, ib / origen.name)
            if lateral:
                (ib / (origen.name + ".meta.json")).write_text(
                    json.dumps({"categoria": origen.parent.name}), encoding="utf-8"
                )
        return ib

    def recuperacion(self, nombre):
        salida = self.t / f"recuperacion_{nombre}.json"
        env = {
            **os.environ,
            "CHROMA_HOST": "127.0.0.1",
            "CHROMA_PORT": str(self.a.puerto),
            "CHROMA_COLLECTION": COLECCION,
            "OLLAMA_BASE_URL": self.a.ollama,
            "PYTHONPATH": str(self.a.rag / "backend"),
        }
        r = subprocess.run(
            [
                str(self.a.rag / ".venv/bin/python"),
                str(AQUI / "recuperacion_rag.py"),
                "medir",
                "--ground-truth",
                str(self.a.ground_truth),
                "--salida",
                str(salida),
            ],
            cwd=self.a.rag,
            env=env,
            capture_output=True,
            text=True,
        )
        if r.returncode:
            raise RuntimeError("Recuperación falló: " + r.stderr[-800:])
        return salida

    def correr(self):
        import chromadb

        validar_trabajo(self.t, [REPO, REPO / "data/documents", Path("/var/lib/atlas")])
        preparar_coleccion(
            chromadb.HttpClient(host="127.0.0.1", port=self.a.puerto),
            COLECCION,
            self.a.recrear_coleccion,
        )
        if self.t.exists():
            shutil.rmtree(self.t)
        (self.t / "raw").mkdir(parents=True)
        (self.t / MARCADOR).write_text("Carpeta desechable de e2e_aws.py\n", encoding="utf-8")
        if self.a.cache_embeddings:
            # Caché caliente declarada: los tiempos de esta corrida NO son en frío.
            (self.t / "cache").mkdir(parents=True)
            shutil.copy2(self.a.cache_embeddings, self.t / "cache" / "embeddings.sqlite")
        res = {}
        # 1. Base
        rc, fichas, s, _ = self.intake(self.buzon("ib_base", BASE, lateral=True))
        chunks = sum(
            len(f.get("chunks") or [])
            for f in (self.ficha(x["doc_id"]) for x in fichas)
            if f["estado"] == "publicado"
        )
        res["base"] = {
            "codigo": rc,
            "segundos": round(s, 1),
            "chunks_publicados": chunks,
            "decisiones": dict(Counter(f"{f['decision']}/{f['estado']}" for f in fichas)),
            "chunks_coleccion": self.coleccion().count(),
        }
        print("BASE", res["base"], flush=True)
        antes = self.recuperacion("antes")
        # 2. Nuevos (sin lateral: el intake clasifica)
        rc, fichas, s, _ = self.intake(self.buzon("ib_nuevos", NUEVOS))
        res["nuevos"] = []
        for f in fichas:
            sufijo = next(k for k, p in self.ruta.items() if sh256(p) == f["doc_id"])
            ficha = self.ficha(f["doc_id"])
            tiempos = {k: round(v, 1) for k, v in ficha.get("tiempos", {}).items()}
            emb = ficha.get("embeddings") or {}
            self.caso(
                f"nuevo: {NUEVOS[sufijo]} ({sufijo})",
                ESPERADO[sufijo],
                f"{ficha['estado']}; {'; '.join(ficha['motivos'])}".strip("; "),
                ficha["estado"] == ESPERADO[sufijo],
                tiempos.get("total"),
            )
            res["nuevos"].append(
                {
                    "doc": sufijo,
                    "estado": ficha["estado"],
                    "decision": ficha["decision"],
                    "motivos": ficha["motivos"],
                    "avisos": ficha["avisos"],
                    "tiempos": tiempos,
                    "chunks": len(ficha.get("chunks") or []),
                    "embeddings_nuevos": emb.get("nuevos"),
                }
            )
        despues = self.recuperacion("despues")
        nuevos_titulos = [self.ruta[s].stem for s in ("a4be", "a7c0", "c8e5")]
        comp = subprocess.run(
            [
                sys.executable,
                str(AQUI / "recuperacion_rag.py"),
                "comparar",
                str(antes),
                str(despues),
                "--nuevos",
                *nuevos_titulos,
            ],
            capture_output=True,
            text=True,
        )
        res["recuperacion"] = json.loads(comp.stdout)
        res["resumen_antes"] = json.loads(antes.read_text(encoding="utf-8"))["resumen"]
        res["resumen_despues"] = json.loads(despues.read_text(encoding="utf-8"))["resumen"]
        self.robustez()
        res["casos"] = self.filas
        return res

    def robustez(self):
        import fitz

        t = self.t
        gieseken, norma = self.ruta["a4be"], self.ruta["c8e5"]
        ib = t / "ib_copias"
        ib.mkdir()
        shutil.copy2(gieseken, ib / "copia_exacta.pdf")
        rc, f, s, _ = self.intake(ib)
        self.caso(
            "copia exacta",
            "sin trabajo nuevo",
            f"{f[0].get('resultado')}",
            f[0].get("resultado") == "sin cambios",
            s,
        )
        (ib / "copia_exacta.pdf").rename(ib / "nombre totalmente distinto.pdf")
        rc, f, s, _ = self.intake(ib)
        self.caso(
            "copia renombrada",
            "mismo doc_id, sin trabajo nuevo",
            f"{f[0].get('resultado')}; doc_id igual: {f[0]['doc_id'] == sh256(gieseken)}",
            f[0].get("resultado") == "sin cambios" and f[0]["doc_id"] == sh256(gieseken),
            s,
        )
        ibm = t / "ib_modificada"
        ibm.mkdir()
        with fitz.open(norma) as d:
            d[-1].insert_text((72, 60), "Copia de trabajo", fontsize=8)
            d.save(ibm / "norma_modificada.pdf")
        rc, f, s, _ = self.intake(ibm)
        ficha = self.ficha(f[0]["doc_id"])
        self.caso(
            "copia modificada",
            "cuasi-duplicado → revisión",
            f"{ficha['estado']}; {'; '.join(ficha['motivos'])}",
            ficha["estado"] == "revision_humana"
            and any("versión nueva" in m for m in ficha["motivos"]),
            s,
        )
        # Escaneo degradado con OCR REAL: 70 dpi, giro de 2°, ruido.
        ibd = t / "ib_degradado"
        ibd.mkdir()
        self.degradar(gieseken, ibd / "escaneo_degradado.pdf")
        rc, f, s, _ = self.intake(ibd)
        ficha = self.ficha(f[0]["doc_id"])
        self.caso(
            "escaneo degradado (70 dpi, 2°, ruido; OCR real)",
            "revisión o rechazo, nunca aceptado",
            f"{ficha['estado']}; {'; '.join(ficha['motivos'])[:200]}",
            ficha["estado"] in {"revision_humana", "rechazado"},
            s,
        )
        # Entradas hostiles
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
        datos = norma.read_bytes()
        (ibh / "truncado.pdf").write_bytes(datos[: len(datos) // 2])
        (ibh / "no_es_pdf.pdf").write_bytes(b"MZ\x90\x00" + os.urandom(4000))
        with fitz.open() as d:
            for _ in range(1001):
                d.new_page(width=200, height=200)
            d.save(ibh / "desmesurado.pdf")
        raro = "..‮fdp.exe\tnombre\x01raro " + "x" * 150 + ".pdf"
        shutil.copy2(self.ruta["0be7"], ibh / raro)
        rc, f, s, _ = self.intake(ibh)
        for archivo, etiqueta in (
            ("en_blanco.pdf", "PDF en blanco"),
            ("cifrado.pdf", "PDF cifrado"),
            ("truncado.pdf", "PDF truncado"),
            ("no_es_pdf.pdf", "falso PDF"),
            ("desmesurado.pdf", "PDF de 1.001 páginas"),
        ):
            x = next(y for y in f if y["doc_id"] == sh256(ibh / archivo))
            self.caso(
                etiqueta,
                "rechazado con motivo",
                f"{x['estado']}; {'; '.join(x['motivos'])}",
                x["estado"] == "rechazado" and x["motivos"],
            )
        x = next(y for y in f if y["doc_id"] == sh256(ibh / raro))
        copias = [p.name for p in (t / "raw").rglob("*") if p.is_file()]
        seguro = all(
            ".." not in n and "‮" not in n and "\t" not in n and "\x01" not in n for n in copias
        )
        self.caso(
            "nombre hostil (.., RTL, tabulador, control, 190 car.)",
            "neutralizado (identidad por hash)",
            f"{x.get('resultado') or x['estado']}; copias en raw con nombre seguro: {seguro}",
            seguro,
        )
        # Dos procesos a la vez
        ibc = self.buzon("ib_concurrente", ["5beb"])
        p1 = self.intake(ibc, esperar=False)
        time.sleep(1)
        p2 = self.intake(ibc, esperar=False)
        p1.communicate(timeout=1800)
        o2 = p2.communicate(timeout=1800)[0]
        self.caso(
            "dos intakes a la vez",
            "uno espera o falla limpio, sin corrupción",
            f"códigos {p1.returncode}/{p2.returncode}",
            {p1.returncode, p2.returncode} <= {0, 2, 3, 4} and 0 in {p1.returncode, p2.returncode},
            None,
            (o2[-160:]).replace("\n", " "),
        )
        # kill -9 durante la extracción (OCR real): el worker debe morir con el padre.
        self.matar_en(
            ["1d4e"],
            "ib_kill_ext",
            lambda ficha: False,
            espera_s=20,
            etiqueta="kill -9 durante extracción (OCR) y reintento",
        )
        # kill -9 durante embeddings
        self.matar_en(
            ["092f"],
            "ib_kill_emb",
            lambda ficha: ficha.get("estado") == "publicando",
            etiqueta="kill -9 durante embeddings y reintento",
        )
        # retire
        h = sh256(self.ruta["092f"])
        antes = len(self.ids(h))
        inicio = time.monotonic()
        r = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "ingest.offline",
                "retire",
                h,
                "--collection",
                COLECCION,
                "--state",
                str(t / "estado"),
                "--layers-root",
                str(t / "capas"),
                "--cache",
                str(t / "cache"),
                "--port",
                str(self.a.puerto),
                "--ollama",
                self.a.ollama,
                "--allow-remote-ollama",
            ],
            cwd=INGESTA,
            capture_output=True,
            text=True,
        )
        self.caso(
            "retire",
            "desaparece de Chroma",
            f"código {r.returncode}; chunks {antes} → {len(self.ids(h))}",
            r.returncode == 0 and antes > 0 and not self.ids(h),
            time.monotonic() - inicio,
        )
        for nombre in ("v1", "atlas_v1", "rag_playas", "rag_playas_magdalena", "atlas_otra"):
            rc, _, _, _ = self.intake(t / "ib_copias", coleccion=nombre)
            self.caso(
                f"colección protegida «{nombre}»", "rechazo (código 3)", f"código {rc}", rc == 3
            )

    def matar_en(self, sufijos, nombre, condicion, etiqueta, espera_s=None):
        ib = self.buzon(nombre, sufijos)
        h = sh256(self.ruta[sufijos[0]])
        ruta_ficha = self.t / "estado" / "intake" / f"{h}.json"
        proceso = self.intake(ib, esperar=False)
        inicio, matado = time.monotonic(), False
        while proceso.poll() is None and time.monotonic() - inicio < 1800:
            listo = espera_s is not None and time.monotonic() - inicio >= espera_s
            if not listo and ruta_ficha.exists():
                try:
                    listo = condicion(json.loads(ruta_ficha.read_text(encoding="utf-8")))
                except ValueError:
                    pass
            if listo:
                os.kill(proceso.pid, signal.SIGKILL)
                matado = True
                break
            time.sleep(0.05)
        proceso.wait()
        time.sleep(2)
        huerfanos = subprocess.run(
            ["pgrep", "-f", "intake_worker"], capture_output=True, text=True
        ).stdout.split()
        rc, f, s, _ = self.intake(ib)
        ficha = self.ficha(h)
        ids, prep = self.ids(h), self.ids(h, COLECCION + "__staging")
        esperados = sorted(c["id"] for c in ficha.get("chunks") or [])
        ok = (
            matado
            and not huerfanos
            and ficha["estado"] == "publicado"
            and sorted(ids) == esperados
            and not prep
        )
        self.caso(
            etiqueta,
            "sin duplicados, huérfanos ni worker vivo",
            f"interrumpido: {matado}; workers vivos tras matar: {len(huerfanos)}; reintento {ficha['estado']}; "
            f"chunks {len(ids)}/{len(esperados)}; preparación {len(prep)}",
            ok,
            s,
        )

    @staticmethod
    def degradar(origen, destino):
        import random

        import fitz

        rnd = random.Random(20261110)
        with fitz.open(origen) as d, fitz.open() as nuevo:
            for pagina in d.pages(0, 4):
                pix = pagina.get_pixmap(dpi=70, colorspace=fitz.csGRAY)
                for _ in range(pix.width * pix.height // 25):
                    pix.set_pixel(
                        rnd.randrange(pix.width), rnd.randrange(pix.height), (rnd.randrange(256),)
                    )
                nueva = nuevo.new_page(width=pagina.rect.width, height=pagina.rect.height)
                nueva.insert_image(nueva.rect, pixmap=pix, rotate=0)
                nueva.set_rotation(0)
            nuevo.save(destino)
        # Giro de 2°: re-render con matriz rotada sobre la página ya degradada.
        with fitz.open(destino) as d, fitz.open() as girado:
            for pagina in d:
                pix = pagina.get_pixmap(
                    matrix=fitz.Matrix(1, 1).prerotate(2), colorspace=fitz.csGRAY
                )
                nueva = girado.new_page(width=pix.width, height=pix.height)
                nueva.insert_image(nueva.rect, pixmap=pix)
            girado.save(str(destino) + ".tmp")
        os.replace(str(destino) + ".tmp", destino)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trabajo", type=Path, required=True)
    parser.add_argument("--ollama", required=True)
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--rag", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--coleccion", default=COLECCION)
    parser.add_argument("--recrear-coleccion", action="store_true")
    parser.add_argument("--cache-embeddings", type=Path, help="caché caliente (declararla)")
    args = parser.parse_args()
    globals()["COLECCION"] = args.coleccion
    res = E2E(args).correr()
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "e2e_aws.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({k: res[k] for k in ("base", "recuperacion")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
