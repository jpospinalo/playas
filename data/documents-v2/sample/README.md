# Muestra de capas v2 (3 documentos)

Copia de bronze, silver y gold de tres documentos de normativa, tomada de la
corrida real de 56 documentos en Linux (t3.large, Tesseract spa, chunker
`legacy`), sin modificar.

| doc_id (prefijo) | Original | Páginas OCR |
|---|---|---:|
| `4b3572e3…` | Por el cual se reglamenta parcialmente el artículo noveno de la Ley 10 de 1978 | 0 |
| `6c078770…` | Por el cual se reglamenta parcialmente la Ley 47 del 19 de febrero de 1993 | 0 |
| `9cd38a2e…` | Por el cual se modifica el artículo 16 del Decreto 3888 del 10 de octubre de 2007 | 0 |

Limitaciones:

- Los tres son PDF digitales cortos; la muestra no incluye un documento
  escaneado con OCR.
- No incluye `embeddings/`: esa corrida usó `--fake-embeddings` (solo
  benchmark), así que sus referencias no corresponden al modelo real.
- No incluye `catalog.json` ni `quality/` (cubren los 56 documentos), ni
  estado, caché o vectores.

Formato descrito en `ingesta/docs/MEDALLION.md`.
