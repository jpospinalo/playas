# Archivo histórico de preparación

**Estado actual:** el diseño anterior con LLM fue sustituido por evaluación
offline sin LLM. La línea base está ejecutada y congelada en `results/v1.jsonl`.
Instrucciones actuales: [NIVEL_0.md](NIVEL_0.md). El texto siguiente documenta
únicamente la preparación anterior, no el estado vigente del experimento.

**No validado por abogados.** Las métricas futuras medirán fidelidad y mejora
relativa; no demostrarán corrección jurídica. No hay resultados RAGAS nuevos.

La fase 0 se detuvo según el límite de 1.500 llamadas. Estimación del diseño
explorado: **2.547 solicitudes**, unos **637 minutos mínimos a 4/min**, incluyendo
reserva de 40 reintentos. No se llamó a Gemini, no se modificó v1 y no se crearon
colecciones. El número no es una cota mínima para cualquier diseño posible.

## Reutilización del trabajo existente

Se leyó el [issue #20](https://github.com/jpospinalo/playas/issues/20) y la rama
`julian-rincon/evaluacion-ragas-linea-base`, commit
`6ab886ac85b6b9c69950eaa4a1da6842836b8d8f`.
De allí se recuperaron los documentos fuente raw/bronze/silver/gold; no se
generaron preguntas a partir de chunks. Se revisaron `generation_cache.py`,
`ragas_v02.py` y `retrieval_baseline.py`: ya separan generación, métricas y
checkpoint. No se copió un segundo harness antes de decidir su adaptación.
Sus resultados de otros modelos, datasets y configuración no se usan como
baseline de este experimento. Tampoco se adopta su afirmación de validación
jurídica como validación disponible para esta tarea.

## Archivos

- `casos_existentes_21.jsonl`: copia aparte de los 21 casos originales,
  todos marcados `validado_por_abogado=false`; no evaluados en esta fase.
  `.gitattributes` conserva LF para que el SHA256 no cambie entre checkouts.
- `preparation/source_manifest.json`: 56 documentos fuente extraídos en Linux
  desde MD/PDF, hashes de originales y de texto NFC, tipo y páginas detectadas.
  19 entradas tienen menos de 200 caracteres; requieren revisar OCR o la
  conversión bronze antes de generar el dataset. No se excluyeron ni indexaron.
- `preparation/ingesta-inspect.json`: lectura de Chroma/Ollama, sin escrituras.
- `preparation/ingesta-budget-final.json`: estimación de llamadas y similitud.
- `preparation/ingesta_budget.py`, `ingesta_reuse.py`, `ingesta_inspect.py`:
  scripts exactos de la exploración ejecutada en Linux; rutas de laboratorio
  `~/atlas-ingesta`, puertos/hosts del sandbox y snapshot local. No son una
  implementación de la nueva ingesta ni entrypoints generales.
- `preparation/ingesta-corpus-provenance.json`: rama, commit y lista de archivos.
- `preparation/ingesta-remote-close.json`, `ingesta-final-status.json`: cierre.

Los scripts exploratorios solo usan GET/lecturas locales. `ingesta_inspect.py`
escribe el texto extraído en un directorio local del host de trabajo, nunca
en Chroma ni S3. El corpus completo y sus textos extraídos se conservaron en
un archivo externo al repositorio antes de eliminar la EC2 temporal.

## Supuestos del presupuesto

40 preguntas: 24 de contenido, 10 de identidad y 6 de cruce/normativa; generación
de referencia todavía pendiente. RAGAS instalado/verificado: **0.4.3**.
Una evaluación de 40 casos en v1 y otra en la versión seleccionada, más diez
repeticiones del juez: 90 casos. Se presupuestan diez llamadas por caso:
faithfulness 2, answer_relevancy 3, context_precision 4 (k=4), context_recall 1.
El tráfico real y los reintentos del SDK no fueron medidos: no hubo corridas.

La previsualización v2a conserva el texto de los 5.888 chunks tras NFC y quitar
controles; presupone reutilización exacta completa, sin ejecutar la ingesta
desde fuentes. La previsualización v2b corta esos textos en encabezados Markdown
y marcadores jurídicos explícitos. Cuenta 6.692 pares únicos fuente+texto:
5.230 coinciden exactamente y 75 tienen similitud >=98%; quedarían 1.387
enriquecimientos. Se compara con SequenceMatcher sin autojunk, solo contra la
misma fuente. No es aún chunking por tokens, no evalúa calidad de cortes y puede
sobreesgmentar encabezados de mobiliario. El pipeline final podría requerir más
o menos llamadas: este resultado es una estimación del diseño explorado.

## Reanudación pendiente

No existen todavía `dataset_v1.jsonl`, `muestra_revision.md`, caché del juez,
`results/v1.jsonl`, v2a ni v2b. No se eligieron modelos generador/juez, no se
verificó su listado y no se fijó un hash de configuración de corrida.
Primero resolver el presupuesto del experimento y verificar credenciales
temporales mediante STS; después adaptar el evaluador existente. Conservar v1
intacta y generar preguntas desde textos fuente verificando citas NFC.
La fase de mejoras ING-01/02/04/08/09/11 no ha comenzado.
