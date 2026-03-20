# Contrato JSONL Silver para sentencias judiciales (Bronze -> Silver)

## 1) Alcance

Este documento define el contrato de datos para la transformacion **solo de Bronze a Silver** en el pipeline de sentencias judiciales.

- Entrada Bronze: PDF original en `data/bronze/`.
- Salida Silver: JSONL normalizado y seccionado en `data/silver/`.
- Fuera de alcance: chunking semantico para embedding, enriquecimiento Gold, indexacion vectorial y consumo en frontend.

## 2) Estrategia de parseo (Docling)

Se establece la siguiente prioridad de extraccion:

1. Metodo principal: `Docling ExportType.DOC_CHUNKS`
2. Respaldo: `Docling ExportType.MARKDOWN`

Regla operativa:

- Si `DOC_CHUNKS` entrega bloques validos (texto util y metadatos minimos), se usa como fuente oficial para construir `sections`.
- Si `DOC_CHUNKS` falla, queda vacio, o no cumple validaciones minimas, se ejecuta `MARKDOWN` y se deriva `sections` por reglas de segmentacion.
- No agregar campos adicionales fuera del esquema minimo definido en este contrato.

## 3) Formato de salida

El contrato base de Silver para sentencias usa un `.jsonl` por documento.

Cada archivo representa un documento fuente y contiene 1 linea JSON con esta forma:

- Objeto raiz con metadatos de documento.
- Arreglo `sections` con el orden narrativo de la sentencia.

## 4) Especificacion de campos

### 4.1 Metadatos de documento (objeto raiz)

| Campo            | Tipo          | Requerido | Descripcion                                              |
| ---------------- | ------------- | --------- | -------------------------------------------------------- |
| `source_file`    | string        | si        | Nombre de archivo PDF origen, ej. `"exp_1234_2021.pdf"`. |
| `case_number`    | string        | si        | Numero de expediente/causa.                              |
| `judgement_date` | string (date) | si        | Fecha ISO `YYYY-MM-DD`.                                  |
| `sections`       | array[object] | si        | Lista ordenada de secciones detectadas.                  |

### 4.2 Secciones (`sections[]`)

| Campo   | Tipo   | Requerido | Descripcion                                        |
| ------- | ------ | --------- | -------------------------------------------------- |
| `title` | string | si        | Encabezado detectado para la seccion.              |
| `text`  | string | si        | Texto de la seccion, limpio pero fiel al original. |

## 5) Convencion sugerida para `title`

Valores sugeridos para facilitar lectura y recuperacion:

- `Caratula`
- `Vistos`
- `Resultandos`
- `Considerandos`
- `Fundamentos de derecho`
- `Resuelve`
- `Fallo`
- `Parte dispositiva`
- `Costas`
- `Honorarios`
- `Disidencia`
- `Aclaratoria`
- `Anexo`
- `Otro`

Regla:

- Si no hay encabezado claro, usar `Otro`.

## 6) Reglas minimas de validacion

1. Obligatorios:
   - Documento: `source_file`, `case_number`, `judgement_date`, `sections`.
   - Seccion: `title`, `text`.
2. Tipos basicos:
   - `source_file`, `case_number`, `judgement_date` son `string`.
   - `sections` es `array` de objetos.
3. No vacios:
   - `source_file`, `case_number`, `judgement_date` no pueden ser cadena vacia ni solo espacios.
   - `sections` debe tener al menos 1 elemento.
   - En cada seccion, `title` y `text` no pueden ser cadena vacia ni solo espacios.
4. Estructura de `sections`:
   - Cada elemento debe incluir exactamente `title` y `text`.
   - No se permiten campos extra a nivel documento ni a nivel seccion.
5. Formato de fecha:
   - `judgement_date` debe cumplir ISO `YYYY-MM-DD`.

## 7) Ejemplo JSONL (1 documento, 5 secciones)

Nota: en JSONL real, cada registro va en una sola linea.

```json
{
  "source_file": "exp_1234_2021.pdf",
  "case_number": "EXP 1234/2021",
  "judgement_date": "2021-09-14",
  "sections": [
    {
      "title": "Caratula",
      "text": "Autos: Perez Juan c/ Seguros del Sur S.A. s/ danos y perjuicios."
    },
    {
      "title": "Vistos",
      "text": "Vistos los autos para resolver el recurso de apelacion interpuesto por la parte actora contra la sentencia de primera instancia."
    },
    {
      "title": "Considerandos",
      "text": "I. La responsabilidad contractual invocada requiere prueba del incumplimiento y del nexo causal. II. Del analisis de la pericia contable y testimonial surge que la demandada rechazo cobertura sin fundamento suficiente."
    },
    {
      "title": "Fundamentos de derecho",
      "text": "Resultan aplicables los articulos 1716, 1724 y concordantes del Codigo Civil y Comercial, asi como la doctrina legal vigente de esta Camara."
    },
    {
      "title": "Fallo",
      "text": "Se hace lugar parcialmente al recurso, se revoca la sentencia apelada en lo pertinente y se imponen las costas en un 70% a la demandada y 30% a la actora."
    }
  ]
}
```

## 8) Checklist de implementacion (sin codigo)

1. Definir y documentar el esquema minimo (`source_file`, `case_number`, `judgement_date`, `sections`).
2. Configurar loader con prioridad `DOC_CHUNKS` y fallback `MARKDOWN`.
3. Implementar normalizacion de secciones en la salida canonica (objeto raiz con `sections` en un `.jsonl` por documento).
4. Implementar validaciones minimas (obligatorios, tipos basicos, no vacios, estructura).
5. Garantizar que cada seccion incluya solo `title` y `text`.
6. Emitir JSONL canonico en `data/silver/`.
7. Verificar que no se emitan campos extra fuera del esquema minimo.

## 9) Pendiente de revision sobre tablas e imagenes

> **Nota:** Queda pendiente revisar en una etapa posterior que se hara con los datos correspondientes a tablas e imagenes.
