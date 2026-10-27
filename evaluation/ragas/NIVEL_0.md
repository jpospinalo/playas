# Evaluación sin LLM

**No validado por abogados.** Mide recuperación relativa, no corrección jurídica.

`dataset_v1.jsonl` contiene40preguntas:24contenido,10identidad,6multi-documento.
Citas comprobadas NFC en textos FUENTE, referencias/páginas y SHA256. Hay35
fuentes elegibles y24muestreadas;19extracciones insuficientes no generan preguntas.
Los21casos previos están aparte. `muestra_revision.md` presenta10casos.

El harness usa el retriever real BM25+vector/RRF del backend, k4/candidatos8,
pregunta cruda, sin agente/análisis LLM. Solo cambia el nombre de colección.
RAGAS0.4.3 yRapidFuzz3.14.3 fijados. Se verificaron NonLLMContextRecall y
NonLLMContextPrecisionWithReference, umbral0,5, Levenshtein; imports de
compatibilidad deprecados, sin LLM. Claves LLM vacías.

Chroma1.3.5 requiere3caracteres: v1 lógica se llama `atlas_v1` en localhost;
5888vectores768dim, snapshot original. `rag_playas` remota nunca se modifica.

```bash
rag/.venv/bin/python evaluation/ragas/run_level0.py \
  --collection atlas_v1 --ollama http://localhost:11434 \
  --output evaluation/ragas/results/v1.jsonl
```

Repetir reanuda IDs pendientes con hashes de configuración y dataset. Se rechaza
checkpoint de otra configuración/colección. Vectores de preguntas en `.cache/`,
ignorados, por texto+digest. Digest requerido:
`85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`.
Aquí coincide exactamente; no se necesitó comparar cosenos.

Hit/MRR documentales deduplican fuentes dentro de top4chunks. Pasaje requiere
cita dentro del chunk tras NFC+espacios. En cruces, hit/MRR usan primera evidencia;
document_recall mide todas. RAGAS textual depende del tamaño de los chunks.
Las preguntas enuncian documentos: sesgo documental y cobertura parcial.
