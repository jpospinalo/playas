# Prueba de punta a punta del intake (FASE 5, local)

Entorno: Windows, Chroma local `127.0.0.1:8011`, colección `bench_intake_e2e`, embeddings FALSOS
deterministas. **Limitaciones:** sin Tesseract, el OCR de los PDF del corpus se sirvió desde la caché
sembrada de runA (Linux) y un escaneo nuevo no puede pasar por OCR; sin Ollama/AWS no hay embeddings
reales, así que la recuperación vectorial (hit@4/MRR) queda **PENDIENTE** y se informa un proxy BM25.
Script reproducible: `benchmarks/intake/e2e_local.py`.

## Base (48 documentos por el propio intake): 84 s

```json
{"aceptado/publicado": 22, "revision_humana/revision_humana": 15, "aceptado_con_advertencias/publicado": 6, "rechazado/rechazado": 2}
```

2989 chunks publicados. Los 2 rechazados son PDF del corpus dañados: empiezan con
«	
» antes de `%PDF-` y les faltan los dos últimos bytes de `%%EOF` (Decreto 415 de 2017 y Decreto 1766
de 2013 en raw). Los 15 en revisión siguen la política calibrada (identidad incompleta, OCR, tablas-imagen).

## Casos

| Caso | Esperado | Obtenido | s | ¿Cumple? |
|---|---|---|---:|---|
| nuevo: sentencia digital (a4be) | publicado | publicado | 5.9 | sí |
| nuevo: sentencia escaneada (a7c0) | publicado | publicado | 2.5 | sí |
| nuevo: norma digital (c8e5) | publicado | publicado | 1.5 | sí |
| nuevo: rojo escaneado (Turbo) (d6b7) | revision_humana | revision_humana; 76% de páginas OCR con confianza ≤ 95 (máximo 50%) | 1.5 | sí |
| nuevo: norma escaneada (1ee0) | publicado | publicado | 1.8 | sí |
| copia exacta (mismos bytes) | sin trabajo nuevo | sin cambios; doc_id igual: True | 2.1 | sí |
| copia renombrada | mismo doc_id, sin trabajo nuevo | sin cambios; doc_id igual: True | 2.1 | sí |
| copia modificada | cuasi-duplicado → revisión | revision_humana; cuasi-duplicado de 896646ecc76401dc95ace08f8e586bd98d368dafdfa9287ad88213cfefcc9f8f: posible versión nueva, no se fusiona; posible versión nuev | 1.4 | sí |
| escaneo degradado (70 dpi, sin capa de texto) | revisión o rechazo, nunca aceptado | rechazado; sin texto útil: 0 caracteres (mínimo 200); categoría dudosa | 1.4 | sí |
| PDF en blanco | rechazado con motivo | rechazado; sin texto útil: 0 caracteres (mínimo 200); categoría dudosa |  | sí |
| PDF cifrado | rechazado con motivo | rechazado; PDF cifrado |  | sí |
| PDF truncado | rechazado con motivo | rechazado; PDF truncado: falta marcador final %%EOF |  | sí |
| no PDF con .pdf | rechazado con motivo | rechazado; Firma inválida: no es un PDF (%PDF-) |  | sí |
| PDF desmesurado (1001 páginas) | rechazado con motivo | rechazado; PDF desmesurado: supera páginas máximas |  | sí |
| dos intakes a la vez | uno espera o falla limpio, sin corrupción | códigos 0/2; chunks 86 sin duplicados: True |  | sí |
| kill -9 durante publicación y reintento | sin duplicados ni huérfanos | interrumpido en 'publicando': True; reintento publicado; chunks 293/293; preparación 0 | 5.2 | sí |
| retire de un documento publicado | desaparece de Chroma | código 0; chunks 293 → 0 | 2.1 | sí |
| colección protegida «v1» | rechazo (código 3) antes de leer el inbox | código 3 |  | sí |
| colección protegida «atlas_v1» | rechazo (código 3) antes de leer el inbox | código 3 |  | sí |
| colección protegida «rag_playas» | rechazo (código 3) antes de leer el inbox | código 3 |  | sí |
| colección protegida «rag_playas_magdalena» | rechazo (código 3) antes de leer el inbox | código 3 |  | sí |
| colección protegida «atlas_otra» | rechazo (código 3) antes de leer el inbox | código 3 |  | sí |
| nombre hostil («..», RTL, 190 caracteres; prueba aparte) | rechazado con motivo | publicado: la identidad es el SHA-256 y la copia en raw se llama `<sha256>.pdf` | | neutralizado, no rechazado |

El nombre de archivo no participa en la identidad ni en ninguna ruta de salida, por eso no se rechaza;
un tabulador en el nombre no es posible en Windows (cubierto por test unitario).

## Recuperación proxy (BM25 léxico sobre los chunks de la colección, sin LLM)

| Preguntas | n | hit@4 antes → después | IC95 Δ | MRR antes → después | IC95 Δ |
|---|---:|---|---|---|---|
| de los documentos nuevos | 10 | 0.000 → 0.900 | [0.700, 1.000] | 0.000 → 0.647 | [0.410, 0.867] |
| del resto | 48 | 0.188 → 0.146 | [-0.104, 0.000] | 0.164 → 0.149 | [-0.039, -0.000] |

Las preguntas de los documentos nuevos pasan a recuperarlos (hit@4 0 → 0,9). En el resto, el BM25
empeora un poco (−0,04 en hit@4; el IC toca 0): más documentos compiten por los mismos términos. Es un
proxy léxico; el efecto en el recuperador híbrido real (BM25 + vectores) no se midió.

## Tiempos

Por documento nuevo (s): ver `e2e.json` (`nuevos[].tiempos`). Embeddings falsos: no
representan el coste real (~0,7 embeddings/s en CPU con Ollama, medido antes).

## Invariantes

- `data/documents`: 424/424 archivos de git y 56/56 en disco con el mismo SHA-256 que al inicio.
- Colecciones de producción rechazadas por configuración: v1, atlas_v1, rag_playas, rag_playas_magdalena y
  cualquier nombre fuera de `atlas_intake_`/`bench_intake_` (código 3, antes de leer el inbox).
- Ningún archivo fuera de las carpetas previstas (trabajo en `C:/Users/Migue/herramientas/e2e3`).
- Colecciones del sandbox AWS (UUID y conteo): **PENDIENTE**, no hubo credenciales.

Todo es fidelidad frente a otro OCR o recuperación léxica; nada está validado por abogados.
