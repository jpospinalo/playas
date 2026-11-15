# Prueba de punta a punta REAL del intake (FASE 2.3)

Worker EC2 Linux t3.medium (Ubuntu 24.04), Tesseract 5.3.4 spa, embeddings reales de
`embeddinggemma` en el Ollama del sandbox (`--allow-remote-ollama`, IP privada), Chroma local
nuevo, colecciones `atlas_demo_e2e*`. Sin caché OCR sembrada ni embeddings falsos.

- **Corrida 1 (en frío):** tiempos reales. Recuperación inválida: el `title` de los chunks era
  el hash (defecto corregido en ff27783).
- **Corrida 2:** código corregido; caché de embeddings de la corrida 1 (declarada): sus tiempos
  NO son en frío; sirve para la recuperación y para confirmar los casos.

Base reducida: 18 documentos (15 publicados, 3 a revisión), 943 fragmentos,
1397 s en frío (~0,68 fragmentos/s con OCR incluido).

## Casos (corrida 1, en frío)

| Caso | Esperado | Obtenido | s |
|---|---|---|---:|
| nuevo: sentencia digital (a4be) | publicado | publicado | 180.9 |
| nuevo: sentencia escaneada (a7c0) | publicado | publicado | 213.1 |
| nuevo: norma digital (c8e5) | publicado | publicado | 21.4 |
| nuevo: control: rojo escaneado (Turbo) (d6b7) | revision_humana | revision_humana; 76% de páginas OCR con confianza ≤ 95 (máximo 50%) | 79.7 |
| copia exacta | sin trabajo nuevo | sin cambios | 3.5 |
| copia renombrada | mismo doc_id, sin trabajo nuevo | sin cambios; doc_id igual: True | 3.5 |
| copia modificada | cuasi-duplicado → revisión | revision_humana; cuasi-duplicado de 896646ecc76401dc95ace08f8e586bd98d368dafdfa9287ad88213cfefcc9f8f: posible versión nueva, no se fusiona; posible ve | 5.1 |
| escaneo degradado (70 dpi, 2°, ruido; OCR real) | revisión o rechazo, nunca aceptado | revision_humana; 2 página(s) OCR sin confianza; página OCR con confianza 51.9 < 70; identidad incompleta: faltan corporacion; categoría dudosa | 9.1 |
| PDF en blanco | rechazado con motivo | rechazado; sin texto útil tras la limpieza: 0 caracteres en silver; categoría dudosa |  |
| PDF cifrado | rechazado con motivo | rechazado; PDF cifrado |  |
| PDF truncado | rechazado con motivo | rechazado; PDF truncado: falta marcador final %%EOF |  |
| falso PDF | rechazado con motivo | rechazado; Firma inválida: no es un PDF (%PDF-) |  |
| PDF de 1.001 páginas | rechazado con motivo | rechazado; PDF desmesurado: supera páginas máximas |  |
| nombre hostil (.., RTL, tabulador, control, 190 car.) | neutralizado (identidad por hash) | publicado; copias en raw con nombre seguro: True |  |
| dos intakes a la vez | uno espera o falla limpio, sin corrupción | códigos 0/2 |  |
| kill -9 durante extracción (OCR) y reintento | sin duplicados, huérfanos ni worker vivo | interrumpido: True; workers vivos tras matar: 0; reintento publicado; chunks 118/118; preparación 0 | 177.3 |
| kill -9 durante embeddings y reintento | sin duplicados, huérfanos ni worker vivo | interrumpido: True; workers vivos tras matar: 0; reintento publicado; chunks 145/145; preparación 0 | 173.5 |
| retire | desaparece de Chroma | código 0; chunks 145 → 0 | 3.7 |
| colección protegida «v1» | rechazo (código 3) | código 3 |  |
| colección protegida «atlas_v1» | rechazo (código 3) | código 3 |  |
| colección protegida «rag_playas» | rechazo (código 3) | código 3 |  |
| colección protegida «rag_playas_magdalena» | rechazo (código 3) | código 3 |  |
| colección protegida «atlas_otra» | rechazo (código 3) | código 3 |  |

Cumplen: corrida 1 23/23; corrida 2 23/23.

## Tiempos por documento nuevo (corrida 1, en frío)

| Doc | Estado | Fragmentos | Total s | Bronce s | Embeddings s | Fragmentos/s |
|---|---|---:|---:|---:|---:|---:|
| a4be | publicado | 151 | 180.9 | 2.3 | 169.1 | 0.89 |
| a7c0 | publicado | 110 | 213.1 | 76.4 | 130.9 | 0.84 |
| c8e5 | publicado | 17 | 21.4 | 0.2 | 16.4 | 1.04 |
| d6b7 | revision_humana | 106 | 79.7 | 74.8 | — | — |

## Recuperación con el buscador híbrido de la aplicación (corrida 2, sin LLM)

hit@4: pasada de producción (k=4, candidatos 8); MRR: pasada profunda (k=20). Bootstrap pareado.

| Preguntas | n | hit@4 antes → después | IC95 Δ | MRR antes → después | IC95 Δ |
|---|---:|---|---|---|---|
| nuevos | 10 | 0.000 → 0.900 | [0.7, 1.0] | 0.000 → 0.800 | [0.550, 1.000] |
| resto | 48 | 0.104 → 0.104 | [0.0, 0.0] | 0.106 → 0.105 | [-0.001, 0.000] |

El «resto» es bajo porque la base es reducida: muchas preguntas del ground truth son de
documentos fuera de la base (REMAC, decreto 2324) o que la política envía a revisión (Lemus, Felipe
Campo). Añadir los nuevos no lo empeora.

Carga del worker durante la corrida 1 (vmstat cada 30 s): CPU media 14 %, máxima 52 %; ~2,3 GB
de caché del sistema siempre disponibles en 3,8 GB de RAM: t3.medium es suficiente.

Fidelidad frente a otro OCR y recuperación frente a un ground truth no validado por abogados.

Nota (revisión de código): la tabla usa la definición de hit@4 de Julián (rango en la pasada
profunda). Recalculado con el top-4 efectivo de producción (`top_prod`): nuevos 0,000 → 0,900
(IC95 [0,70, 1,00]); resto 0,104 → 0,104. Mismas cifras con ambas definiciones en esta corrida.
