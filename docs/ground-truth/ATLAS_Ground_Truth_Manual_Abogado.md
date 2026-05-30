# Proyecto ATLAS · Sistema de evaluación RAG (v2)

# Esquema de ground truth y guía del evaluador

> **Marco de referencia para construir el conjunto de evaluación**
> 10 preguntas por sentencia · **9 sentencias del Tribunal Administrativo del Magdalena** · **90 entradas en total**

---

## Índice

1. Esquema de categorías de pregunta
2. Corpus — las 9 sentencias
3. Guía del evaluador (cómo responder)
4. Formato de respuesta y checklist
5. **Formulario de ground truth** — las 90 preguntas para responder (SM-01 a SM-09)

---

## 1. Esquema de categorías de pregunta

Cada sentencia del corpus produce exactamente **10 preguntas**, distribuidas en **5 grupos temáticos** que mapean a las cuatro secciones estructurales de toda providencia. Con 9 sentencias indexadas, el conjunto completo de evaluación contiene **90 pares pregunta–respuesta de referencia**.

> La redacción del ground truth es **técnico-jurídica**: el destinatario del sistema ATLAS es un profesional del derecho que espera precisión terminológica, no simplificación.

### Secciones del documento — base de mapeo

| # | Sección | Contenido |
|---|---------|-----------|
| **1** | **Contexto del caso** | Antecedentes · Petitum · Causa petendi |
| **2** | **Desarrollo procesal** | Contestación · Instancias · Apelación |
| **3** | **Análisis del tribunal** | Consideraciones · Ratio decidendi |
| **4** | **Decisión** | Falla · Resuelve · Conclusiones |

### Las 10 categorías de pregunta

| # | Categoría | Sección | Descripción |
|---|-----------|---------|-------------|
| **Grupo A — Contexto del caso (3 preguntas · Sección 1)** ||||
| Q1 | **Identificación del expediente** | §1 | Datos únicos del caso: radicado, corporación, magistrado(a) ponente y año. |
| Q2 | **Partes procesales** | §1 | Accionante(s), demandado(s) y vinculados. Prueba si el sistema recupera la nómina completa de entidades. |
| Q3 | **Objeto y pretensiones** | §1 | Qué pidió el accionante (petitum) y por qué (causa petendi); suelen ser subsecciones separadas que el experto integra. |
| **Grupo B — Desarrollo procesal (2 preguntas · Sección 2)** ||||
| Q4 | **Postura de la defensa** | §2 | Argumentos de contestación: excepciones, falta de legitimación, cumplimiento de funciones, hechos negados. |
| Q5 | **Trámite e instancias** | §2 | Qué resolvió primera instancia y qué ocurrió en segunda (apelación), o aclaración de única instancia. |
| **Grupo C — Análisis del tribunal (3 preguntas · Sección 3)** ||||
| Q6 | **Marco normativo aplicado** | §3 | Normas, leyes, decretos y jurisprudencia citados en las consideraciones. |
| Q7 | **Ratio decidendi** | §3 | El razonamiento jurídico central que determinó el sentido del fallo. |
| Q8 | **Imputación institucional** | §1 + §3 | Quién es responsable según el tribunal y por qué; cruza identidad de entidades con análisis de responsabilidad. |
| **Grupo D — Decisión final (1 pregunta · Sección 4)** ||||
| Q9 | **Decisión y órdenes del fallo** | §4 | El resuelve exacto: qué se ordenó, a quién y en qué plazo. Todos los numerales, no solo el primero. |
| **Grupo E — Síntesis transversal (1 pregunta · Secciones 1+3+4)** ||||
| Q10 | **Cadena causa–decisión** | §1 + §3 + §4 | Conecta el problema jurídico (§1), el razonamiento (§3) y la solución ordenada (§4). La de mayor exigencia. |

### Distribución por grupo — 10 preguntas / sentencia

| Contexto | Procesal | Análisis | Decisión | Síntesis |
|:--------:|:--------:|:--------:|:--------:|:--------:|
| **3** | **2** | **3** | **1** | **1** |
| Q1·Q2·Q3 | Q4·Q5 | Q6·Q7·Q8 | Q9 | Q10 |

---

## 2. Corpus — las 9 sentencias

El corpus indexado contiene **9 sentencias** del Tribunal Administrativo del Magdalena (capa *Gold* del backend). Cada una se evalúa con las 10 preguntas del esquema → **90 entradas de ground truth**. Esta tabla es la referencia maestra de identificación: úsela para confirmar radicado, ponente y partes antes de responder. La ficha completa de cada sentencia (con sus partes procesales) se repite al inicio de su bloque de preguntas en la Sección 5.

| ID | Radicado | Ponente | Tema principal | Relación playas |
|----|----------|---------|----------------|:---------------:|
| **SM-01** | `47-001-2333-000-2018-00368-00` | Adonay Ferrari Padilla | Protección del ambiente marino en la Bahía de Santa Marta frente a vertimientos. | Indirecta |
| **SM-02** | `470012333000202100198-00` | María Victoria Quiñones Triana | Ecosistema marino-costero de la Bahía de Taganga por vertimientos de aguas residuales y pluviales. | Indirecta |
| **SM-03** | `470012333000202000687-00` | María Victoria Quiñones Triana | Erosión costera en playas del municipio de Ciénaga y responsabilidad institucional. | Directa |
| **SM-04** | `47-001-3333-005-2010-00684-01` | María Victoria Quiñones Triana *(2ª inst.)* | Espacio público en zona de playa "Los Cocos" frente a muro que restringía el acceso al litoral. | Directa |
| **SM-05** | `47-001-3333-001-2016-00473-01` | Maribel Mendoza Jiménez | Proyecto Irotama Reservado presuntamente sobre zona de playa marítima e infracción urbanística. | Directa |
| **SM-06** | `47-001-2333-000-2016-00482-00` | María Victoria Quiñones Triana | Erosión costera y desaparición de la playa Salguero en Santa Marta. | Directa |
| **SM-07** | `47-001-2333-000-2016-00270-00` | María Victoria Quiñones Triana | Uso de la playa Los Cocos para eventos masivos y afectación de derechos colectivos. | Directa |
| **SM-08** | `47-001-3333-001-2016-03261` | Maribel Mendoza Jiménez | Alteración del cauce del río Gaira y su desembocadura al mar Caribe. | Indirecta |
| **SM-09** | `47-001-2331-003-2011-08425-00` | Edgar Alexi Vásquez Contreras | Erosión costera en el sector Pozos Colorados y amenaza a derechos colectivos. | Directa |

> **Nota sobre SM-09:** existe además una **sentencia de segunda instancia** (radicado `47001-2332-000-2011-08425-02`, accionante Gabriel Antonio Carrero Torres). Si la consulta, considere ambas providencias al responder, distinguiendo lo resuelto en cada instancia.

### Entidades institucionales recurrentes

Estas entidades aparecen como demandadas o vinculadas en múltiples sentencias. Use siempre el **nombre oficial completo**, no la sigla aislada, la primera vez que la mencione:

- **DIMAR** — Dirección General Marítima
- **CORPAMAG** — Corporación Autónoma Regional del Magdalena
- **ANLA** — Autoridad Nacional de Licencias Ambientales
- **DADSA / DADMA** — autoridad ambiental distrital de Santa Marta
- **INVEMAR** — Instituto de Investigaciones Marinas y Costeras
- **ESSMAR** — Empresa de Servicios Públicos de Santa Marta
- **UNGRD** — Unidad Nacional para la Gestión del Riesgo de Desastres
- **Ministerio de Ambiente y Desarrollo Sostenible**
- **Ministerio de Defensa Nacional**

---

## 3. Guía del evaluador — cómo responder

> Esta guía explica cómo usted —como abogado(a) experto(a)— debe contestar las 10 preguntas de cada sentencia. Sus respuestas serán las **respuestas de referencia (ground truth)** con las que se medirá la calidad del sistema ATLAS. Redacte en lenguaje técnico-jurídico, con precisión terminológica.

### ¿Para qué sirven sus respuestas?

ATLAS es un motor de recuperación y síntesis jurisprudencial. Para medir si sus respuestas son correctas, las comparamos con respuestas que **usted, el experto, ya validó**. Por eso se llaman *respuestas de referencia*. Si ATLAS responde de forma equivalente a la suya → el sistema funciona. Si difiere → ahí está el error que hay que corregir.

### Paso a paso

1. **Lea la providencia completa antes de responder.** Ubique las 4 secciones estructurales:

   - **Sección 1 — Contexto del caso:** antecedentes, demanda, petitum y causa petendi.
   - **Sección 2 — Desarrollo procesal:** contestación, instancias, apelación.
   - **Sección 3 — Análisis del Tribunal:** "Consideraciones de la Sala".
   - **Sección 4 — Decisión:** el "Resuelve" o "Falla".
   - Si una sección usa otro nombre (p. ej. "Síntesis del caso" en vez de "Antecedentes"), el contenido es equivalente.

2. **Responda en orden, una pregunta a la vez** (Q1 a Q10, sin saltar). Si la información genuinamente no está en el texto, escriba *"No disponible en el texto"* — **nunca deje el campo en blanco**.

3. **Redacte con precisión jurídica y economía de palabras:**

   - Frases completas, registro técnico, terminología exacta del documento.
   - Datos literales cuando existan: radicados, nombres oficiales de entidades, artículos de ley, fechas del fallo.
   - Fidelidad estricta al texto: no interprete ni añada doctrina externa a la providencia.
   - Concisión: 2–5 oraciones precisas bastan para la mayoría de preguntas (Q10 es la excepción).

4. **Para Q10 (síntesis), conecte los tres momentos del caso:** problema jurídico (§1) + razonamiento del Tribunal (§3) + lo ordenado (§4). Es la única pregunta donde se espera una respuesta de 5–8 oraciones, estructurada como *problema → análisis → decisión*.

### Guía por categoría de pregunta

**Q1 · Identificación del expediente** — *Sección 1*

- **¿Qué busca?** Radicado, corporación, magistrado(a) ponente, partes y año.
- **¿Dónde?** Encabezado del documento o primera sección (Antecedentes / Síntesis del caso).
- ✓ *Buena respuesta:* "La sentencia tiene radicado 47-001-2333-000-2018-00368-00, fue proferida por el Tribunal Administrativo del Magdalena, con ponencia del magistrado Adonay Ferrari Padilla."
- ⚠ Evite respuestas vagas como "es del Tribunal del Magdalena". Incluya siempre el radicado completo.

**Q2 · Partes procesales** — *Sección 1*

- **¿Qué busca?** Lista completa de accionante(s), demandado(s) y vinculados.
- **¿Dónde?** Encabezado o subsección "Resumen de la demanda".
- ✓ Incluya a todos los vinculados, aunque sean muchos. DIMAR, CORPAMAG, ANLA, DADSA y los municipios son recurrentes — nunca los omita.
- ⚠ No agrupe entidades informalmente. Use el nombre oficial completo.

**Q3 · Objeto y pretensiones** — *Sección 1*

- **¿Qué busca?** Qué pidió el accionante (petitum) y la fundamentación jurídica (causa petendi).
- **¿Dónde?** Subsecciones "Petitum" / "Pretensiones" y "Causa petendi" / "Fundamentos de derecho".
- ✓ Integre ambos elementos: "El accionante solicitó [petitum] con fundamento en [causa petendi]."

**Q4 · Postura de la defensa** — *Sección 2*

- **¿Qué busca?** Argumentos defensivos: excepciones, falta de legitimación en la causa, cumplimiento de funciones, hechos negados.
- **¿Dónde?** Subsección "Contestación de la demanda" / "Actuación procesal".
- ✓ Si varias entidades contestaron, sintetice la postura de cada una o agrupe por línea argumentativa común.
- ⚠ Si la sentencia no detalla las contestaciones, indíquelo expresamente.

**Q5 · Trámite e instancias** — *Sección 2*

- **¿Qué busca?** Qué resolvió la primera instancia y qué ocurrió en segunda (si la hay).
- **¿Dónde?** "Sentencia de primera instancia" y "Recurso de apelación" / "Trámite de segunda instancia".
- ✓ Estructura: "En primera instancia [corporación] resolvió [decisión] el [fecha]. [Parte] apeló alegando [razón]. En segunda instancia [resultado]."
- ⚠ Si es de única instancia, indíquelo explícitamente.

**Q6 · Marco normativo aplicado** — *Sección 3*

- **¿Qué busca?** Normas (leyes, decretos, artículos constitucionales) y jurisprudencia que el Tribunal usó.
- **¿Dónde?** "Consideraciones de la Sala". Busque citas como "según el artículo X de la Ley Y" o "conforme a la sentencia C-123".
- ✓ Liste las normas principales en orden de importancia, con identificador preciso: "Ley 99 de 1993, art. 80 — principio de precaución ambiental".

**Q7 · Ratio decidendi** — *Sección 3*

- **¿Qué busca?** La razón jurídica determinante: por qué el Tribunal decidió lo que decidió.
- **¿Dónde?** Al cierre de las "Consideraciones de la Sala" ("se configura la vulneración de…" / "no se acredita…").
- ✓ Nombre: el derecho o principio en juego + el hecho que lo vulneró + por qué se imputa a las entidades.
- ⚠ No confunda ratio decidendi con el resuelve (Q9): el ratio es el *porqué*, el resuelve es el *qué*. No incluya obiter dicta.

**Q8 · Imputación institucional** — *Sección 1 + Sección 3*

- **¿Qué busca?** A qué entidades les atribuyó responsabilidad el Tribunal y por qué omisión o acción concreta.
- **¿Dónde?** Cruce la lista de demandados (§1) con el análisis de responsabilidad (§3). El Tribunal puede exonerar a unas y responsabilizar a otras.
- ✓ Formato ideal: "El Tribunal responsabilizó a [entidad A] por [conducta] y a [entidad B] por [otra conducta]. Exoneró a [entidad C] porque [razón]."

**Q9 · Decisión y órdenes del fallo** — *Sección 4*

- **¿Qué busca?** Las órdenes del fallo: qué se ordenó, a quién y en qué plazo.
- **¿Dónde?** La sección "Resuelve" / "Falla" ("PRIMERO: ORDENAR a…", "SEGUNDO: AMPARAR…").
- ✓ Recoja **cada numeral** del resuelve. Conserve el verbo rector (ORDENAR, AMPARAR, DECLARAR) y el destinatario exacto.
- ⚠ No resuma en exceso. "Se ordenó proteger el ambiente" es insuficiente: indique qué entidad, qué acción y en qué plazo.

**Q10 · Cadena causa–decisión (síntesis)** — *§1 + §3 + §4*

- **¿Qué busca?** Una narrativa completa: situación fáctica → análisis jurídico → órdenes.
- **¿Dónde?** Integre las tres secciones principales. Es la única que exige lectura transversal de todo el documento.
- **Estructura sugerida:** "El caso trata sobre [problema fáctico del §1]. El accionante alegó [pretensión del §1]. El Tribunal analizó el caso a la luz de [normas del §3] y concluyó que [ratio decidendi], atribuyendo responsabilidad a [entidades]. En consecuencia, ordenó [decisiones del §9]."
- ✓ Puede tener 5–8 oraciones. Es la más relevante para calibrar la calidad general de ATLAS.

### Reglas generales de calidad

- **Fidelidad al texto:** su respuesta debe poder verificarse leyendo la providencia. No añada interpretación propia.
- **Exactitud en entidades:** use siempre el nombre institucional oficial (DIMAR, CORPAMAG, ANLA, DADSA, etc.).
- **Radicados completos:** tal como aparecen en el documento.
- **Si una sección no existe:** escriba "La sentencia no incluye esta sección" — nunca deje el campo en blanco.
- **Idioma y registro:** español, lenguaje técnico-jurídico del documento.
- **No especule:** si el Tribunal no menciona una fecha o plazo, no lo incluya.

---

## 4. Formato de respuesta y checklist

Una vez usted complete las respuestas de este formulario, nuestro equipo las procesará y convertirá al formato estándar de evaluación. **Usted no debe diligenciar JSON ni formatos técnicos**: basta con que escriba la respuesta de referencia en el espacio provisto bajo cada pregunta, y cualquier observación en el campo de notas.

A título informativo, cada sentencia se transformará internamente en un archivo con esta estructura (usted solo aporta el contenido de `ground_truth` y `notes`):

```json
{
  "sentencia_id": "SM-04",
  "radicado": "47-001-3333-005-2010-00684-01",
  "corporacion": "Tribunal Administrativo del Magdalena",
  "evaluacion": [
    {
      "q_id": "Q1",
      "categoria": "Identificación del expediente",
      "seccion_documento": "§1 — Contexto del caso",
      "question": "¿Cuál es el número de radicado, la corporación y el magistrado ponente de esta sentencia?",
      "ground_truth": "[LO QUE USTED RESPONDA]",
      "atlas_answer": null,
      "atlas_contexts": [],
      "notes": "[SUS COMENTARIOS OPCIONALES]"
    }
  ]
}
```

### Checklist final antes de entregar

- [ ] Las 9 sentencias (SM-01 a SM-09) tienen todas sus respuestas completas
- [ ] Cada sentencia tiene las 10 preguntas (Q1–Q10) respondidas
- [ ] Q1 incluye radicado completo y magistrado(a) ponente
- [ ] Q2 lista todas las entidades demandadas y vinculadas con nombre oficial
- [ ] Q3 incluye tanto petitum como causa petendi
- [ ] Q5 menciona primera y segunda instancia (o aclara que es única instancia)
- [ ] Q7 (ratio) es distinta de Q9 (decisión): una explica el *porqué*, la otra el *qué*
- [ ] Q8 identifica entidades responsables Y exoneradas (si las hay)
- [ ] Q9 incluye todos los numerales del resuelve, no solo el primero
- [ ] Q10 conecta los 3 momentos: problema fáctico → análisis → órdenes

### Ejemplo aplicado — sentencia SM-04 (Los Cocos, acceso al litoral)

> **Contexto de SM-04:** Acción sobre construcción de muro en Los Cocos, Santa Marta, que restringía el acceso al litoral. Segunda instancia. Ponente: María Victoria Quiñones Triana.

**Ejemplo Q1 — Identificación del expediente**
> "La sentencia tiene radicado 47-001-3333-005-2010-00684-01, fue proferida por el Tribunal Administrativo del Magdalena (segunda instancia), con ponencia de la magistrada María Victoria Quiñones Triana."

**Ejemplo Q9 — Decisión y órdenes del fallo**
> "El Tribunal resolvió: PRIMERO, declarar la vulneración del derecho colectivo al uso del espacio público. SEGUNDO, ordenar al Distrito de Santa Marta y a DIMAR retirar la estructura que restringía el acceso a la playa Los Cocos en el plazo de [X días]. TERCERO, prohibir cualquier construcción futura que impida el libre tránsito al litoral."

**Ejemplo Q10 — Cadena causa–decisión**
> "El caso surge por la construcción de un muro en zona de playa (Los Cocos, Santa Marta) que impedía el acceso público al litoral. El accionante alegó la vulneración del derecho colectivo al uso del espacio público y el dominio inalienable de las playas. El Tribunal analizó el caso a la luz del artículo 63 de la Constitución y del Código Nacional de Recursos Naturales, concluyendo que las playas marítimas son bienes de uso público no susceptibles de restricción. Atribuyó responsabilidad al Distrito de Santa Marta y a DIMAR por permitir u omitir la remoción de la estructura. En consecuencia, ordenó el retiro del muro y la restauración del libre acceso al litoral."

> ⚠ **Los ejemplos anteriores son ilustrativos del formato esperado, no respuestas validadas.** La respuesta de referencia real debe extraerla usted de la lectura de la providencia.

---

## 5. Formulario de ground truth — 90 preguntas

Responda cada pregunta en el espacio provisto, siguiendo la guía de la Sección 3. Una sentencia = 10 preguntas. **No deje campos en blanco**: si la información no consta, escriba *"No disponible en el texto"*.

---

### SM-01 — Protección del ambiente marino en la Bahía de Santa Marta frente a vertimientos contaminantes y omisiones institucionales.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-2333-000-2018-00368-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | Adonay Ferrari Padilla |
| **Partes** | Accionante: Procuraduría General de la Nación – Procuraduría Delegada para Asuntos Ambientales. Demandados: Nación – ANLA, Ministerio de Defensa, DIMAR, CORPAMAG, Distrito de Santa Marta, DADSA, Proactiva Santa Marta S.A. E.S.P. |
| **Relación con playas** | Indirecta |
| **Temática** | Ambiental |

#### SM-01 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-01 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular promovida por la Procuraduría General de la Nación por la contaminación de la Bahía de Santa Marta (SM-01): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-02 — Protección del ecosistema marino-costero de la Bahía de Taganga por vertimientos de aguas residuales y pluviales.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `470012333000202100198-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | María Victoria Quiñones Triana |
| **Partes** | Demandantes: Carlos Alberto Zúñiga Mejía y otros. Demandados: Nación – Ministerio de Ambiente, Distrito de Santa Marta, ESSMAR, DADSA. Vinculados: DIMAR, CORPAMAG, INVEMAR, Policía Nacional, entre otros. |
| **Relación con playas** | Indirecta |
| **Temática** | Ambiental |

#### SM-02 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-02 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre la protección del ecosistema marino-costero de la Bahía de Taganga (SM-02): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-03 — Erosión costera en playas del municipio de Ciénaga y responsabilidad institucional frente al riesgo ambiental y territorial.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `470012333000202000687-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | María Victoria Quiñones Triana |
| **Partes** | Actor: Felipe José Campo Fernández. Demandados: Departamento del Magdalena y municipio de Ciénaga. Vinculados: DIMAR, CORPAMAG, UNGRD, ANLA, INVEMAR, Ministerio de Ambiente, entre otros. |
| **Relación con playas** | Directa |
| **Temática** | Gestión del riesgo |

#### SM-03 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-03 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre la erosión costera en las playas del municipio de Ciénaga (SM-03): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-04 — Protección del espacio público en zona de playa (“Los Cocos”) frente a construcción de muro que restringía el acceso al litoral.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-3333-005-2010-00684-01` |
| **Corporación** | Tribunal Administrativo del Magdalena (segunda instancia) |
| **Magistrado(a) ponente** | María Victoria Quiñones Triana |
| **Partes** | Actor: Gerardo Antenor Lemus Orozco. Demandados: Nación – Ministerio de Ambiente, Distrito de Santa Marta, Curaduría Urbana No. 2, DIMAR, Pevesca Ltda. e Inversiones Vives Ltda. |
| **Relación con playas** | Directa |
| **Temática** | Acceso |

#### SM-04 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-04 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre el muro en zona de playa “Los Cocos” que restringía el acceso al litoral (SM-04, segunda instancia): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-05 — Construcción del proyecto Irotama Reservado presuntamente sobre zona de playa marítima e infracción de normas urbanísticas.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-3333-001-2016-00473-01` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | Maribel Mendoza Jiménez |
| **Partes** | Accionante: Gieseken Cuello & Cía. S. en C. Demandados: DIMAR, Distrito de Santa Marta, Curaduría Urbana, Irotama S.A.S. y Valor S.A. |
| **Relación con playas** | Directa |
| **Temática** | Usufructo |

#### SM-05 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-05 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre la construcción del proyecto Irotama Reservado en zona de playa marítima (SM-05): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-06 — Acción popular por erosión costera y desaparición de la playa Salguero en Santa Marta.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-2333-000-2016-00482-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | María Victoria Quiñones Triana |
| **Partes** | Actores: Rodrigo Martínez Silva y Yulín Yasira Serbousse Castro. Demandados: Nación – Ministerio de Ambiente, Ministerio de Defensa, DIMAR, Distrito de Santa Marta, DADSA, CORPAMAG. |
| **Relación con playas** | Directa |
| **Temática** | Gestión del riesgo |

#### SM-06 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-06 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular por la erosión costera y desaparición de la playa Salguero en Santa Marta (SM-06): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-07 — Uso de playa Los Cocos para eventos masivos y afectación de derechos colectivos al ambiente sano y espacio público.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-2333-000-2016-00270-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | María Victoria Quiñones Triana |
| **Partes** | Actores: Inversiones E y D S.A.S. y Verónica Carolina Dávila Dávila. Demandados: Nación – Ministerio de Defensa, DIMAR, Distrito de Santa Marta, DADSA. |
| **Relación con playas** | Directa |
| **Temática** | Usufructo |

#### SM-07 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-07 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre el uso de la playa Los Cocos para eventos masivos (SM-07): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-08 — Alteración del cauce del río Gaira y su desembocadura al mar Caribe, con impacto ambiental y urbano.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-3333-001-2016-03261` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | Maribel Mendoza Jiménez |
| **Partes** | Accionante: Miguel Ángel Enciso Pava. Demandados: CORPAMAG, Distrito de Santa Marta, DADMA y Nación – DIMAR. |
| **Relación con playas** | Indirecta |
| **Temática** | Ambiental |

#### SM-08 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-08 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular sobre la alteración del cauce del río Gaira y su desembocadura al mar Caribe (SM-08): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

### SM-09 — Acción popular por erosión costera en el sector Pozos Colorados y amenaza a derechos colectivos.

| Campo | Dato de referencia |
|---|---|
| **Radicado** | `47-001-2331-003-2011-08425-00` |
| **Corporación** | Tribunal Administrativo del Magdalena |
| **Magistrado(a) ponente** | Edgar Alexi Vásquez Contreras |
| **Partes** | Accionante: Gabriel Antonio Carrero Torres. Demandados: Departamento del Magdalena, DIMAR, Distrito de Santa Marta, Ministerio de Ambiente. |
| **Relación con playas** | Directa |
| **Temática** | Gestión del riesgo |

> **Nota:** existe sentencia de segunda instancia, radicado `47001-2332-000-2011-08425-02`. Considérela al responder, distinguiendo lo resuelto en cada instancia.

#### SM-09 · Q1 — Identificación del expediente
*Sección 1 — Contexto del caso*

> **Pregunta:** Indique el número de radicado completo, la corporación que profirió la providencia, el/la magistrado(a) ponente y el año de la decisión en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09).

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q2 — Partes procesales
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué partes intervinieron en el proceso (accionante(s), entidades demandadas y vinculados, con su nombre oficial completo) en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q3 — Objeto y pretensiones
*Sección 1 — Contexto del caso*

> **Pregunta:** ¿Qué pretensiones formuló el accionante (petitum) y cuál fue la causa petendi (los fundamentos de hecho y de derecho) que las sustentó en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q4 — Postura de la defensa
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué argumentos de defensa y excepciones propusieron las entidades demandadas al contestar la demanda en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q5 — Trámite e instancias
*Sección 2 — Desarrollo procesal*

> **Pregunta:** ¿Qué se resolvió en primera instancia y, de existir, qué decidió la segunda instancia (recurso de apelación) en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)? Si fue de única instancia, indíquelo expresamente.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q6 — Marco normativo aplicado
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Qué normas (leyes, decretos, artículos constitucionales) y qué jurisprudencia citó el Tribunal en sus consideraciones para analizar la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q7 — Ratio decidendi
*Sección 3 — Análisis del tribunal*

> **Pregunta:** ¿Cuál fue la ratio decidendi (el razonamiento jurídico central que determinó el sentido del fallo) en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q8 — Imputación institucional
*Sección 1 + Sección 3 — Contexto + Análisis*

> **Pregunta:** ¿A qué entidades atribuyó responsabilidad el Tribunal y por qué conducta concreta (acción u omisión), y a cuáles exoneró y por qué, en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q9 — Decisión y órdenes del fallo
*Sección 4 — Decisión*

> **Pregunta:** ¿Cuáles fueron las órdenes concretas del resuelve (qué se ordenó, a quién y en qué plazo), recogiendo todos los numerales del fallo, en la acción popular por la erosión costera en el sector Pozos Colorados (SM-09)?

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

#### SM-09 · Q10 — Cadena causa–decisión (síntesis)
*Sección 1 + 3 + 4 — Síntesis transversal*

> **Pregunta:** Sintetice la cadena causa–decisión de la acción popular por la erosión costera en el sector Pozos Colorados (SM-09): el problema fáctico planteado, el análisis jurídico del Tribunal, las entidades a las que atribuyó responsabilidad y las órdenes impartidas.

**Respuesta de referencia:**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

**Notas (opcional):** ____________________________________________________

---

*Documento generado para el proyecto ATLAS — Sistema agéntico de orientación normativa y jurisprudencial sobre playas en Colombia. Corpus base: capa Gold del backend (9 sentencias del Tribunal Administrativo del Magdalena).*
