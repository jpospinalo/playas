# Entrada autónoma de PDF

`python -m ingest.offline intake` analiza documentos locales sin LLM, sin claves
y sin servidor web. Ejecutar los comandos desde `ingesta/`. Nunca modifica,
borra ni mueve los originales del inbox. La identidad es el SHA-256 del archivo;
renombrarlo no crea otro documento.

## Instalación

Python 3.12 o superior. En el entorno preparado de esta máquina:

```powershell
cd C:\Users\Migue\Desktop\playas\ingesta
$py = 'C:/Users/Migue/herramientas/venv-intake/Scripts/python.exe'
& $py -m pip install -e '.[offline]' PyYAML pytest ruff
New-Item -ItemType Directory -Force data/inbox
```

Para una instalación Linux independiente:

```sh
cd /srv/playas/ingesta
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[offline]' PyYAML pytest ruff
mkdir -p data/inbox
```

Los embeddings reales necesitan Ollama local con `embeddinggemma:latest`:
`ollama pull embeddinggemma`. Se comprueba el digest fijado en
`ingest/offline_embeddings.py`, dimensión 768 y valores finitos. Un modelo con
otro digest exige revisar el pin y usar otra colección. No se instala ni
descarga ningún modelo durante el intake.

Para publicar se necesita Chroma local en `127.0.0.1:8000`, por ejemplo:
`chroma run --host 127.0.0.1 --port 8000 --path .offline/chroma-intake`.
Los tests usan Chroma efímero en memoria y embeddings falsos, sin servidor.

El OCR real requiere Tesseract con el idioma español `spa` en el PATH. En Linux,
por ejemplo, `sudo apt install tesseract-ocr tesseract-ocr-spa`. En Windows hay
que instalar Tesseract y sus datos `spa` por separado. La caché OCR de referencia
puede sembrarse para pruebas como muestra
`benchmarks/ocr_referencia/sembrar_cache_ocr.py`; eso no sustituye un OCR real de
documentos nuevos.

## Comandos del operador

Simular: no conecta a Chroma/Ollama, no escribe fichas ni informes persistentes y
no copia documentos aceptados a raw. Usa un directorio temporal para el análisis
y una copia temporal del estado/caché existentes (incluido OCR); lo elimina al
terminar.

```powershell
& $py -m ingest.offline intake --collection atlas_intake_20261110 --inbox data/inbox --once --dry-run
```

Una corrida con embeddings reales:

```powershell
& $py -m ingest.offline intake --collection atlas_intake_20261110 --inbox data/inbox --once --raw-root data/documents/raw --layers-root data/intake-capas --state .offline/intake-20261110 --cache .offline/intake-cache --policy config/intake_policy.yaml --destinos config/intake_destinos.yaml --ollama http://localhost:11434 --port 8000
```

Prueba con vectores deterministas y colección de ensayo (necesita Chroma local
si se ejecuta el CLI fuera de pytest):

```powershell
& $py -m ingest.offline intake --collection bench_intake_prueba --inbox data/inbox --once --fake-embeddings --raw-root data/intake-raw-prueba --layers-root data/intake-capas-prueba --state .offline/intake-prueba --cache .offline/cache-prueba
```

Observación periódica:

```powershell
& $py -m ingest.offline intake --collection atlas_intake_20261110 --inbox data/inbox --watch --intervalo 30 --layers-root data/intake-capas --state .offline/intake-20261110 --cache .offline/intake-cache
```

`--once` es el modo predeterminado. `--once` y `--watch` son excluyentes. Ctrl+C
detiene la observación. El inbox debe existir y sus entradas se examinan en el
primer nivel; crear otra corrida para cada inbox si se necesitan varios.
Las opciones habituales de `sync` (`--chunker`, `--token-budget`, `--batch-size`,
`--from-stage`) también se admiten. La configuración de chunker por defecto es
la misma que en `sync`: `legacy`, 512 tokens. `--collection` es obligatoria.

Ollama remoto exige `--allow-remote-ollama` además de `--ollama URL`. Esta opción
no autoriza Chroma remoto. El publicador siempre conecta a `127.0.0.1`; `--host`
sirve para validar el destino declarado y sus alias loopback.

## Configuración y protecciones

`config/intake_policy.yaml` contiene la política calibrada y sus umbrales de
rechazo, revisión y advertencia. El intake la reutiliza sin alterar los umbrales.
`--policy RUTA` permite seleccionar una política explícita.

`config/intake_destinos.yaml` controla lo siguiente:

| Campo | Valor inicial / función |
|---|---|
| `colecciones_protegidas` | `v1`, `atlas_v1`, `rag_playas`, `rag_playas_magdalena`; se pueden añadir otras |
| `prefijos_permitidos` | `atlas_intake_`, `bench_intake_`; todo nombre fuera de ellos se rechaza |
| `hosts_chroma_permitidos` | Solo loopback; no se pueden autorizar hosts remotos |
| `hosts_protegidos` | Vacío inicialmente; una persona puede registrar los hosts de producción |
| `tamano_maximo_bytes` | 104857600 (100 MiB) |
| `paginas_maximas` | 1000 |
| `tiempo_maximo_documento_segundos` | 600 por subproceso de documento |
| `memoria_maxima_mb` | 2048, mediante `resource.setrlimit` en Linux |
| `simhash_umbral` | Hamming ≤ 3 implica posible versión nueva |
| `simhash_palabras_shingle` | 3 palabras por shingle |
| `gancho_notificacion` | Ruta opcional de archivo JSONL; nunca se ejecuta como comando |

Tanto la colección viva como `<colección>__staging` deben pasar la validación
antes de leer el inbox. Las cuatro colecciones históricas y la restricción a
loopback permanecen protegidas aunque se cambie el YAML. Los prefijos de la
configuración solo pueden restringir los espacios `atlas_intake_` y
`bench_intake_`. Los embeddings falsos exigen `bench_`.

Separar inbox, raw, estado, capas y caché en raíces independientes. Las salidas
no admiten enlaces simbólicos. La única escritura autorizada en
`data/documents/raw` es la copia de un documento publicable con nombre
`<sha256>.pdf`. No se relajan las protecciones de las capas v1. La ruta total
de esa copia debe medir menos de 240 caracteres, también en Windows.

## Decisiones y revisión

| Decisión | Resultado |
|---|---|
| `aceptado` | Copia segura en raw, embeddings y publicación verificada |
| `aceptado_con_advertencias` | Publica y conserva los avisos, por ejemplo identidad recomendada incompleta |
| `revision_humana` | Conserva capas/ficha y añade una fila a la cola; no publica |
| `rechazado` | Conserva el motivo; no publica ni copia a raw |

Firma distinta de `%PDF-`, cifrado, truncamiento, reparación necesaria, cero
páginas, error al iterar, tamaño/páginas excesivos y falta de texto útil producen
rechazo. Los errores de extracción/timeout y publicación se registran como
`error_documento` / `error_publicacion` y permiten continuar con los demás.
PyMuPDF no ejecuta JavaScript; no se abren anexos embebidos. El aislamiento limita
tiempo y memoria, pero no constituye un contenedor de seguridad del sistema.

La categoría se deduce por reglas del encabezado de las dos primeras páginas del
bronce, con confianza registrada en la ficha. Una clasificación ambigua produce
`categoría dudosa`. Una persona puede crear, junto al PDF, este archivo:

`data/inbox/ejemplo.pdf.meta.json`:

```json
{"categoria": "normativa"}
```

También puede usar `data/inbox/metadata_intake.csv`:

```csv
hash,nombre,categoria
,ejemplo.pdf,normativa
```

Se admite una fila por SHA-256 en la columna `hash`. El lateral tiene prioridad
sobre el CSV. Solo `normativa` y `jurisprudencia` son válidas. Los laterales y
`metadata_intake.csv` nunca se procesan como PDF. La corrección de categoría no
inventa identidad legal ni anula otras reglas de calidad: si sigue faltando
identidad, permanece en revisión.

Consultar `<state>/review_queue.csv`, acumulativo y con una fila por hash.
Revisar el original y `<state>/intake/<doc_id>.json`, corregir la categoría y
repetir exactamente el comando de intake. El cambio manual invalida la decisión
anterior. La cola conserva el historial y actualiza su columna `estado`.
Para recalcular deliberadamente una decisión sin cambios de entrada, usar
`--from-stage silver` (o `bronze`, `gold`, `embeddings` según corresponda):

```powershell
& $py -m ingest.offline intake --collection atlas_intake_20261110 --inbox data/inbox --once --from-stage silver --layers-root data/intake-capas --state .offline/intake-20261110 --cache .offline/intake-cache
```

Las fases anteriores se reutilizan y se verifican. Una fase previa ausente o
incompatible exige reiniciar desde ella. Un cambio de categoría requiere silver;
no basta con gold o embeddings. Un cambio de extractor/chunker/modelo exige
estado y colección nuevos. La huella de colección del intake incluye todas esas
versiones.

Un SHA-256 ya procesado con igual configuración y corrección manual da
`sin cambios`, incluidos archivos renombrados. Los ids de los documentos
publicados se vuelven a comprobar. SimHash de 64 bits sobre shingles del silver
detecta posibles versiones de documentos publicados: distancia ≤ umbral implica
`revision_humana`, con `posible versión nueva de <doc_id>`; nunca se fusionan.
La categoría manual no elimina esa revisión: comparar los originales y decidir
con una persona qué versión conservar. Retirar la anterior y reintentar la nueva
desde silver permite reevaluar sin compararla contra la versión retirada.

## Publicación, recuperación y retiro

El orden es bronze → silver → gold → señales/política → embeddings → preparación
→ verificación → viva → verificación. La verificación compara conteos e ids y
consulta un canario con el embedding de un chunk propio (filtrado por doc_id),
que debe recuperar ese chunk primero. La preparación se vacía por doc_id tras
el éxito. Un fallo elimina el documento de ambas colecciones y registra el
error; una reversión incompleta queda pendiente para el siguiente intento.

Hay bloqueos de escritor sobre estado, capas, caché y Chroma. Otro escritor falla
limpio; no ejecutar dos programaciones sobre las mismas raíces. El cerrojo del
sistema se libera tras un cierre forzado; `.writer.guard` permanece en disco y
`.writer.lock` es solo una marca informativa que se sustituye al adquirir el
cerrojo. No borrar archivos de bloqueo de un escritor activo.

Tras `kill -9`, repetir el mismo comando. SQLite conserva los lotes de embeddings
confirmados; los ids deterministas y la reconciliación por doc_id eliminan
sobrantes y evitan duplicados. Conservar el inbox hasta completar la recuperación.
No borrar estado, caché o capas durante un proceso activo.

Retirar usando los mismos destinos, estado y configuración (añadir
`--fake-embeddings` si se usaron vectores falsos):

```powershell
& $py -m ingest.offline retire SHA256_DE_64_CARACTERES --collection atlas_intake_20261110 --inbox data/inbox --layers-root data/intake-capas --state .offline/intake-20261110 --cache .offline/intake-cache
```

`retire` borra por doc_id de viva y preparación, conserva raw, capas y ficha,
y marca `retirado`. Una corrida normal no lo publica de nuevo por estar aún en
el inbox. Un retiro interrumpido conserva la intención y se termina al reanudar.

Cada ficha incluye decisión, motivos, avisos, señales, métricas por capa,
clasificación, tiempos, chunks, embeddings, configuración, colección, rutas y
hash. Cada corrida deja `intake_report.md`; `intake.log.jsonl` registra decisiones
con tiempos y `llm_api_calls: 0`. El gancho añade esas decisiones al archivo local
configurado, sin servicios externos.

Códigos de salida: **0** corrida procesada, aunque haya revisiones/rechazos;
**2** algún documento falló o hay un error operativo; **3** configuración inválida
o destino protegido.

## Exportación y verificación

Exportar el estado de intake usa exclusivamente embeddings de la caché confirmada,
sin conexión a Ollama/Chroma. Solo incluye fichas `publicado`:

```powershell
& $py -m ingest.offline --collection atlas_intake_20261110 --state .offline/intake-20261110 --cache .offline/intake-cache --layers-root data/intake-capas export data/exports/intake.jsonl.gz
& $py -m ingest.offline verify-export data/exports/intake.jsonl.gz
```

Entregar juntos `intake.jsonl.gz` e `intake.jsonl.gz.manifest.json`. El manifiesto
incluye SHA-256 de cada archivo de datos exportado, SHA-256 de los registros,
conteos de documentos/chunks, configuración, `config_hash`, colección y fecha UTC.
No se incluye su propio hash para evitar una referencia circular. La fecha se
conserva al repetir una instantánea idéntica. `verify-export` recalcula hashes,
conteos, ids únicos y valida vectores; devuelve 2 ante discrepancias. El hash
permite detectar cambios respecto al manifiesto recibido; no es una firma de
autenticidad de su autor.

Una PERSONA que haya verificado y revisado el paquete podría ejecutar desde la
raíz del repositorio el importador existente, indicando explícitamente el destino:

```sh
python data/import_to_chromadb.py ingesta/data/exports/intake.jsonl.gz --host HOST_REVISADO --port 8000 --collection COLECCION_NUEVA_REVISADA
```

Ese paso es manual; el intake no lo ejecuta ni importa a producción. No importar
paquetes de embeddings falsos en colecciones reales. Conservar el manifiesto
junto al paquete para revisión independiente.

## Programación

Usar rutas absolutas y `--once` en cada invocación del programador. Los ejemplos
Linux suponen `/srv/playas/ingesta`, Python en `.venv` y Chroma/Ollama ya iniciados.

Cron cada cinco minutos:

```cron
*/5 * * * * cd /srv/playas/ingesta && .venv/bin/python -m ingest.offline intake --collection atlas_intake_20261110 --inbox /srv/playas/ingesta/data/inbox --once --layers-root /srv/playas/ingesta/data/intake-capas --state /srv/playas/ingesta/.offline/intake-20261110 --cache /srv/playas/ingesta/.offline/intake-cache >> /srv/playas/ingesta/.offline/programador.log 2>&1
```

Crear previamente `.offline/` para el log. Para systemd, guardar
`/etc/systemd/system/playas-intake.service`:

```ini
[Unit]
Description=Entrada local de documentos de playas
After=network.target

[Service]
Type=oneshot
User=playas
WorkingDirectory=/srv/playas/ingesta
ExecStart=/srv/playas/ingesta/.venv/bin/python -m ingest.offline intake --collection atlas_intake_20261110 --inbox /srv/playas/ingesta/data/inbox --once --layers-root /srv/playas/ingesta/data/intake-capas --state /srv/playas/ingesta/.offline/intake-20261110 --cache /srv/playas/ingesta/.offline/intake-cache
```

Y `playas-intake.timer`:

```ini
[Unit]
Description=Revisión periódica del inbox
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
[Install]
WantedBy=timers.target
```

Una persona configura permisos del usuario `playas` y habilita el temporizador
con `sudo systemctl enable --now playas-intake.timer`. Consultar
`journalctl -u playas-intake.service`.

En el Programador de tareas de Windows, crear una tarea para el usuario operador,
desencadenador cada cinco minutos y acción:

- Programa: `C:\Users\Migue\herramientas\venv-intake\Scripts\python.exe`
- Argumentos: `-m ingest.offline intake --collection atlas_intake_20261110 --inbox data/inbox --once --layers-root data/intake-capas --state .offline/intake-20261110 --cache .offline/intake-cache`
- Iniciar en: `C:\Users\Migue\Desktop\playas\ingesta`
- Si ya se ejecuta: no iniciar una instancia nueva.

## Limitaciones y adaptación

En Windows **no hay límite de memoria**; se aplica timeout de documento y límite
OCR de 120 segundos por página. Linux añade `resource.setrlimit(RLIMIT_AS)`.
La calidad del OCR depende de Tesseract `spa`; las pruebas con caché sembrada no
miden su calidad real. Los embeddings reales requieren Ollama y el digest fijado
de embeddinggemma. No se prueban servicios externos en la suite unitaria.

Las reglas del encabezado y SimHash pueden dar revisiones legítimas; no sustituyen
la revisión jurídica. Un PDF reparable se rechaza de forma conservadora. Cada
archivo debe estar completamente copiado al inbox antes de la corrida.

No hay dependencia de `origin/corpus`. Para esa estructura hay que elegir las
rutas reales de entrada y copias mediante `--inbox` y `--raw-root`, reservar una
raíz nueva con `--layers-root` y estados/cachés separados, y preparar la categoría
por lateral o CSV cuando el encabezado no sea concluyente. El intake clasifica
explícitamente; no necesita carpetas llamadas `normativa` o `jurisprudencia`.

## Validación local

```powershell
& $py -m pytest tests/unit/test_intake.py --basetemp "$env:TEMP/pytest-intake" -q
& $py -m pytest --basetemp "$env:TEMP/pytest-intake-suite" -q
& $py -m ruff check ingest/offline tests/unit/test_intake.py
& $py -m ruff format --check ingest/offline tests/unit/test_intake.py
```
