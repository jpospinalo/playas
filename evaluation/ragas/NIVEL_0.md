# Evaluación sin LLM

**No validado por abogados.** Mide recuperación relativa, no corrección jurídica.

`dataset_v1.jsonl` contiene 40 preguntas: 24 contenido, 10 identidad, 6 multidocumento.
Citas comprobadas NFC en textos FUENTE, referencias/páginas y SHA256. Hay 35
fuentes elegibles y 24 muestreadas; 19 extracciones insuficientes no generan preguntas.
Los 21 casos previos están aparte. `muestra_revision.md` presenta 10 casos.

El harness usa el retriever real BM25+vector/RRF del backend, k=4/candidatos=8,
pregunta cruda, sin agente/análisis LLM. Solo cambia el nombre de colección.
RAGAS 0.4.3 y RapidFuzz 3.14.3 fijados. Se verificaron NonLLMContextRecall y
NonLLMContextPrecisionWithReference, umbral 0,5, Levenshtein; imports de
compatibilidad deprecados, sin LLM. Claves LLM vacías.

Chroma 1.3.5 requiere 3 caracteres: v1 lógica se llama `atlas_v1` en localhost;
5.888 vectores, 768 dimensiones, snapshot original. `rag_playas` remota nunca se modifica.

```bash
rag/.venv/bin/python evaluation/ragas/run_level0.py \
  --collection atlas_v1 --ollama http://localhost:11434 \
  --output evaluation/ragas/results/v1.jsonl
```

Repetir reanuda IDs pendientes con hashes de configuración y dataset. Se rechaza
checkpoint de otra configuración/colección. Vectores de preguntas en `.cache/`,
ignorados, por texto+digest. Digest requerido:
`85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`.
Aquí coincide exactamente. Además, una réplica local del mismo Ollama 0.40.8
produjo coseno 1 en tres muestras frente al servicio original.
Con todas las consultas presentes en caché por digest, dimensión y finitud,
el harness puede repetir la evaluación con Ollama apagado. Si falta un vector,
comprueba `/api/tags` y exige el digest antes de calcularlo. Esto permite apagar
el cómputo de embeddings en cuanto termina su trabajo.

Hit/MRR documentales deduplican fuentes dentro de top 4 chunks. Pasaje requiere
cita dentro del chunk tras NFC+espacios. En cruces, hit/MRR usan primera evidencia;
document_recall mide todas. RAGAS textual depende del tamaño de los chunks.
Las preguntas enuncian documentos: sesgo documental y cobertura parcial.

Comparar las tres colecciones completadas:

```bash
rag/.venv/bin/python evaluation/ragas/compare_level0.py
```

Genera selection.json y comparison.json: medias/medianas por categoría, deltas
por pregunta, IC95% bootstrap pareado y diez peores casos. La selección usa
MRR documental; en empate gana v2a. Nivel 1 permanece desactivado.
