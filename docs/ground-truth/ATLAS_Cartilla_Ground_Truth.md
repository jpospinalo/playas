# Cartilla de construcción del Ground Truth — Proyecto ATLAS

> **Documento dirigido a las personas expertas en derecho que validarán el sistema ATLAS.**
> Esta es la única oportunidad de construcción del ground truth: no habrá segunda ronda.

---

## 1. Qué es esto y por qué lo necesitamos

ATLAS es un sistema agéntico de recuperación y síntesis sobre jurisprudencia y normativa colombiana relativa a playas y dominio público marítimo-terrestre. Para evaluar objetivamente su calidad, necesitamos un **conjunto de referencia (ground truth)**: una lista de preguntas, formuladas por usted, sobre los documentos del corpus, **acompañadas de la respuesta correcta que usted mismo daría como experto**.

Esa respuesta suya es la regla de medida. ATLAS contestará la misma pregunta y compararemos su respuesta con la suya. Si coinciden en sustancia, el sistema funciona; si no, ahí está el error que debemos corregir.

> **Importante:** esta cartilla **no le entrega preguntas escritas**. Le entrega un marco para que usted las redacte a partir de la lectura de cada documento. La calidad del proyecto depende enteramente de la calidad de las preguntas y respuestas que usted produzca.

---

## 2. Corpus y volumen de trabajo

El corpus está alojado en el bucket **Backup → carpeta `gold/`**, organizado en dos subcarpetas:

| Carpeta | Tipo documental | Documentos |
|---|---|:---:|
| `gold/jurisprudencia/` | Sentencias del Tribunal Administrativo del Magdalena | _____ |
| `gold/normativa/` | Decretos, leyes y reglamentos del orden nacional | _____ |
| **Total** | | **_____** |

Por cada documento se deben formular **10 preguntas**, una por cada categoría descrita en la Sección 3.

$$\text{Total de preguntas esperadas} = \text{N.º de documentos} \times 10$$

> Antes de empezar, identifique todos los documentos disponibles en el bucket y lleve una lista para ir marcando los avances.

---

## 3. Las 10 categorías de pregunta

Cada documento del corpus debe producir exactamente una pregunta de cada una de las siguientes categorías. La categoría determina **el tipo de capacidad de recuperación o razonamiento** que se está midiendo. Para cada categoría se indica:

- **Qué evalúa** — la capacidad del sistema que se está probando.
- **Cómo formular la pregunta** — instrucciones de redacción.
- **Qué debe incluir su respuesta de referencia** — los elementos mínimos que su respuesta debe contener para que la comparación con ATLAS sea válida.

> Reglas transversales que aplican a las 10 categorías:
> - Redacte en español técnico-jurídico.
> - Use el nombre oficial completo de entidades y normas (no siglas aisladas la primera vez).
> - La respuesta debe ser **verificable contra el texto del documento**: nada de doctrina externa.
> - Si un documento no permite formular una categoría concreta (por ejemplo, una norma sin pasos procedimentales), formule la pregunta más cercana posible y déjelo anotado.

### 3.1 Literal

- **Qué evalúa:** que el sistema localice un fragmento textual concreto y lo devuelva tal cual aparece en el documento.
- **Cómo formular la pregunta:** apunte a un dato explícito que figura en el documento con palabras propias del texto (un plazo, una cifra, un nombre, una fecha de expedición).
- **Qué debe incluir la respuesta:** el dato exacto reproducido como aparece en el documento, junto con una breve referencia al lugar donde se encuentra (sección, artículo o numeral).

### 3.2 Parafraseada

- **Qué evalúa:** que el sistema entienda la pregunta aunque esté formulada con palabras distintas a las del documento.
- **Cómo formular la pregunta:** tome un contenido del documento y reescríbalo con su propio vocabulario, evitando expresiones literales del texto.
- **Qué debe incluir la respuesta:** la misma información que daría a la versión literal de la pregunta, expresada con fidelidad al texto fuente y con la referencia a su ubicación.

### 3.3 De extracción puntual

- **Qué evalúa:** que el sistema aísle un dato específico sin añadir información innecesaria.
- **Cómo formular la pregunta:** pida un único dato concreto (número de radicado, nombre del ponente, número de artículo, fecha del fallo, identificador de la norma).
- **Qué debe incluir la respuesta:** **solo** el dato solicitado, sin contexto adicional. Si conviene aclarar la fuente, hágalo en una nota breve aparte.

### 3.4 De definición

- **Qué evalúa:** que el sistema identifique definiciones formales presentes en el corpus.
- **Cómo formular la pregunta:** pida la definición de un término jurídico o técnico que el documento defina explícitamente (por ejemplo, qué se entiende por "zona de bajamar", "bien de uso público", "playa marítima").
- **Qué debe incluir la respuesta:** la definición tal como la formula el documento, citando la fuente (artículo, considerando o sección). Si el documento solo la usa sin definirla, no fabrique la definición: indique que el documento no la define.

### 3.5 Procedimental

- **Qué evalúa:** que el sistema explique pasos o trámites documentados en el orden correcto.
- **Cómo formular la pregunta:** pregunte por un procedimiento o secuencia de actuaciones que el documento describa (por ejemplo, cómo se autoriza una concesión, cuál es el trámite de una acción popular en la providencia, qué pasos siguió el Tribunal).
- **Qué debe incluir la respuesta:** los pasos en el orden en que aparecen en el documento, sin agregar pasos que el texto no mencione.

### 3.6 Condicional

- **Qué evalúa:** que el sistema aplique correctamente una regla que depende de una condición.
- **Cómo formular la pregunta:** plantee un supuesto de hecho concreto que active una regla descrita en el documento (por ejemplo, "qué procede si la construcción se ubica en zona de bajamar", "qué ocurre cuando el accionado no contesta dentro del término").
- **Qué debe incluir la respuesta:** la regla aplicable al supuesto, su fundamento textual en el documento y, si el documento contempla varias condiciones, distíngalas.

### 3.7 Multi-hop

- **Qué evalúa:** que el sistema integre dos o más fragmentos del **mismo documento** para construir una respuesta única.
- **Cómo formular la pregunta:** plantee una pregunta cuya respuesta requiera enlazar dos elementos separados (por ejemplo, conectar una pretensión del accionante con la decisión final, o un considerando con un numeral del resuelve).
- **Qué debe incluir la respuesta:** la síntesis articulada de los fragmentos, identificando cada uno de los pasos del razonamiento y la sección de la que proviene.

### 3.8 Multi-documento

- **Qué evalúa:** que el sistema combine evidencia proveniente de **más de un documento** del corpus.
- **Cómo formular la pregunta:** elija un punto donde el documento que está trabajando se relaciona con otro del corpus (una norma que se aplica en una sentencia, dos sentencias sobre el mismo asunto, un decreto invocado por una providencia) y formule una pregunta cuya respuesta exija ambos.
- **Qué debe incluir la respuesta:** la información extraída de cada documento, claramente atribuida a su fuente, y la conclusión combinada.

### 3.9 Comparativa

- **Qué evalúa:** que el sistema contraste reglas, posturas, decisiones o regímenes con un criterio explícito.
- **Cómo formular la pregunta:** pida una comparación con un criterio definido (por ejemplo, cómo difiere el tratamiento de la erosión costera entre dos sentencias, qué obligaciones impone una norma frente a otra, en qué se distinguen las posturas de dos entidades demandadas).
- **Qué debe incluir la respuesta:** los elementos comparados, el criterio de comparación y las diferencias o coincidencias relevantes, con fundamento textual en cada fuente.

### 3.10 De ranking

- **Qué evalúa:** que el sistema ordene opciones según un criterio explícito.
- **Cómo formular la pregunta:** pida un ordenamiento de elementos presentes en el documento o entre documentos (por ejemplo, ordenar los numerales del resuelve por destinatario, ordenar las normas citadas por jerarquía, ordenar decisiones por antigüedad).
- **Qué debe incluir la respuesta:** la lista en el orden correcto, el criterio de ordenamiento y, brevemente, la justificación con base en el documento.

---

## 4. Procedimiento sugerido

1. **Tome un documento del bucket** (jurisprudencia o normativa) y léalo íntegramente antes de redactar nada.
2. **Recorra las 10 categorías en orden** (de 3.1 a 3.10) y para cada una redacte una pregunta y la respuesta de referencia. Una categoría = una pregunta y una respuesta.
3. **No deje respuestas en blanco.** Si la categoría no aplica al documento, escriba la pregunta más cercana posible y registre por qué la categoría no se acomoda bien.
4. **Pase al siguiente documento** solo cuando termine las 10 categorías del anterior.
5. **Marque su lista** de documentos al cerrar cada uno.

---

## 5. Regla de cumplimiento (umbral del 70 %)

El ground truth se considera **válido** si cubre **al menos el 70 %** del total esperado de preguntas. Es decir, si el tiempo disponible no alcanza para cubrir todos los documentos, **es preferible omitir documentos completos** (con sus 10 preguntas) y conservar los restantes íntegros, antes que dejar documentos a medio responder.

$$\text{Cobertura mínima válida} = 0{,}70 \times (\text{N.º documentos} \times 10)$$

Reglas operativas del umbral:

- Si decide omitir un documento, **omítalo completo**: no formule solo algunas categorías de un mismo documento.
- Mantenga proporciones razonables entre jurisprudencia y normativa al decidir qué omitir (no concentre la omisión en un único tipo documental).
- Por debajo del 70 % el ground truth se considera incompleto y no podrá usarse para evaluar ATLAS.

---

## 6. Entrega

Entregue el material en un único archivo (texto plano, Markdown o documento estructurado) con la siguiente organización mínima por cada documento trabajado:

- Identificador del documento (radicado, número de decreto o nombre del archivo en `gold/`).
- Tipo (`jurisprudencia` o `normativa`).
- Para cada una de las 10 categorías: la pregunta, la respuesta de referencia y, opcionalmente, una nota.

El equipo técnico transformará su entrega al formato interno de evaluación. **Usted no debe diligenciar JSON ni formatos técnicos.**

---

## 7. Recordatorios finales

- Esta es la **única ronda**: no habrá revisiones posteriores ni segunda oportunidad.
- La calidad de su redacción —precisión terminológica, fidelidad al texto, claridad de la respuesta— determina la validez del proyecto entero.
- Si surge una duda sobre la interpretación de una categoría o la aplicabilidad a un documento concreto, anótela y continúe; no se detenga.
