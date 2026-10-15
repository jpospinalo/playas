# Informe de evaluación de ATLAS

**Para:** equipo jurídico del proyecto ATLAS  
**Preparado por:** Julian Esteban Rincón Rodríguez  
**Fecha:** 2026-10-15  
**Base de la evaluación:** 66 preguntas con respuesta de referencia construidas y validadas por el equipo jurídico (ground truth v0.2)

---

## 1. Resumen

1. **ATLAS es fiel a sus fuentes.** Ninguna respuesta se clasificó como inventada; en promedio, el 87% de lo que afirma cada respuesta está respaldado por los documentos que consultó.
2. **Sus respuestas coinciden en un 70% con las del equipo jurídico.** De 65 respuestas evaluadas, **51 se consideran correctas**, 8 fallaron porque el sistema no encontró el documento adecuado y 6 fueron incompletas o demasiado generales.
3. **Su mayor debilidad es encontrar la normativa nacional.** Cuando la respuesta depende del **REMAC 5** o del **Decreto 2324 de 1984**, el sistema los encontró en solo **2 de 18** preguntas. En su lugar suele usar reglamentos locales o sentencias, lo que a veces basta y a veces deja la respuesta incompleta.
4. **Las preguntas sobre trámites y procedimientos son las más débiles.** En "secuencia, trámite u orden jurídico" las respuestas omiten o mezclan pasos con más frecuencia que en cualquier otro tipo de pregunta.
5. **Un modelo pequeño y gratuito que corre en un computador local encuentra información equivalente, pero responde peor.** Con el mismo buscador y los mismos documentos, el modelo local (`gemma4:e2b`) acertó en **32 de 65** preguntas, frente a **51** del sistema actual. Es fiel a sus fuentes y en nuestras pruebas respondió más rápido (19 frente a 61 segundos en promedio), pero sus respuestas son más incompletas e imprecisas. Hoy no es un reemplazo adecuado.

---

## 2. Qué se evaluó y cómo

- **Qué se evaluó:** ATLAS tal como está desplegado hoy, sin ningún cambio, respondiendo las **66 preguntas** del ground truth construido por el equipo jurídico (relatos de usuarios de playa con su respuesta de referencia y el documento que la sustenta).
- **Cómo se calificó:** un evaluador automático (un modelo de lenguaje usado como juez) compara cada respuesta de ATLAS con la respuesta de referencia del equipo jurídico y con los documentos que ATLAS consultó. Además, se revisaron casos a mano para confirmar que la calificación tiene sentido.
- **Qué se midió por separado:**
  - si ATLAS **encuentra** los documentos correctos;
  - si **usa bien** lo que encuentra, sin inventar;
  - si su respuesta **se parece** a la del equipo jurídico.
- **Comparación adicional:** se repitió la misma prueba cambiando el modelo de lenguaje de ATLAS por un **modelo pequeño que corre localmente**, sin costo por consulta. Las preguntas, los documentos, el buscador y el evaluador fueron los mismos. Como el modelo también reformula la pregunta antes de buscar y decide si es del tema, los fragmentos consultados pueden variar entre un modelo y otro (ver §5).

## 3. Cómo leer las cifras

Todas las cifras van de 0 a 1: más alto es mejor (0,70 equivale a un 70%).

| Indicador | Qué responde |
|---|---|
| **Fidelidad a las fuentes** | ¿Lo que afirma ATLAS está respaldado por los documentos que consultó, o inventa? |
| **Coincidencia con la respuesta jurídica** | ¿Dice lo mismo que la respuesta de referencia del equipo jurídico, sin omitir lo importante ni agregar cosas que no están? |
| **Exactitud global** | Calificación de conjunto de qué tan correcta es la respuesta frente a la referencia |
| **Documento correcto encontrado** | ¿Entre los 4 fragmentos que ATLAS consulta estaba el documento que señaló el equipo jurídico? |
| **Evidencia necesaria encontrada** | ¿Lo que dice la respuesta jurídica aparece en lo que ATLAS consultó, aunque venga de otro documento? |

Cada respuesta se clasifica además en una de estas categorías:
- **Correcta.**
- **No encontró la evidencia:** el problema está en la búsqueda.
- **Inventó:** no se apegó a los documentos.
- **Incompleta o demasiado general:** encontró la evidencia, pero no la aprovechó.

## 4. Resultados del sistema actual

### 4.1 Por tipo de pregunta

| Tipo de pregunta | Preguntas | Documento correcto encontrado | Fidelidad | Coincidencia con la respuesta jurídica | Exactitud global |
|---|---:|---:|---:|---:|---:|
| **Todas** | **65** | **0,55** | **0,87** | **0,70** | **0,72** |
| 1. Extracción puntual | 2 | 1,00 | 0,33 | 0,00 | 0,25 |
| 2. Síntesis dentro de un documento | 7 | 0,71 | 0,96 | 0,74 | 0,75 |
| 3. Cruce entre documentos | 5 | 0,40 | 0,92 | 0,72 | 0,65 |
| 4. Comparación jurídica | 7 | 0,71 | 0,88 | 0,74 | **0,54** |
| 5. Aplicación normativa o jurisprudencial | 36 | 0,48 | 0,87 | 0,75 | 0,83 |
| 6. Secuencia, trámite u orden jurídico | 8 | 0,50 | 0,89 | **0,54** | 0,56 |

*"Documento correcto encontrado" se calcula sobre las 58 preguntas que tienen documento esperado; una pregunta rechazada cuenta como no encontrado. Se usan los fragmentos que el sistema consultó de verdad; el anexo técnico reporta 0,57 porque allí la búsqueda se mide con la pregunta original, sin reformular. Los tipos 1 a 4 tienen entre 2 y 7 preguntas, así que sus cifras son orientativas.*

### 4.2 Clasificación de las respuestas

| Resultado | Respuestas |
|---|---:|
| Correcta | **51** |
| No encontró la evidencia | 8 |
| Incompleta o demasiado general | 6 |
| Inventó | 0 |

### 4.3 Otros datos del funcionamiento

- **65 de 66** preguntas se reconocieron como del tema. Una pregunta pertinente se rechazó como "fuera del ámbito" (ver §6.4).
- **Tiempo de respuesta:** en promedio **61 segundos** por pregunta.

## 5. Comparación con un modelo local

Se repitió la evaluación completa cambiando el modelo de lenguaje de ATLAS: en lugar de gpt-5-nano (servicio de OpenAI, con costo por consulta) se usó **gemma4:e2b**, un modelo pequeño y abierto que corre en un computador portátil, **sin costo por consulta y sin enviar datos a terceros**. Las preguntas, los documentos, el buscador y el evaluador fueron los mismos.

En ATLAS el modelo interviene en tres pasos: reformula la pregunta antes de buscar, decide si la pregunta es del tema y redacta la respuesta. Por eso, con cada modelo los fragmentos consultados pueden variar: solo en 13 de las 66 preguntas los dos modelos consultaron exactamente los mismos fragmentos, aunque en 60 compartieron al menos uno.

*Dos advertencias para leer la comparación:*
- *El evaluador es gpt-5-nano, el mismo modelo del sistema actual, lo que podría favorecerlo ligeramente.*
- *Los tiempos no se midieron en las mismas condiciones: el sistema actual consultaba servicios en la nube y procesaba varias preguntas a la vez, mientras que el modelo local corrió en un portátil, una pregunta a la vez. Indican una tendencia, no una medición exacta.*

### 5.1 Resultado general

| Indicador | Sistema actual (gpt-5-nano) | Modelo local (gemma4:e2b) |
|---|---:|---:|
| Respuestas correctas | **51 de 65** | 32 de 65 |
| Incompletas o demasiado generales | 6 | 22 |
| No encontró la evidencia | 8 | 11 |
| Inventó | 0 | 0 |
| Fidelidad a las fuentes | **0,87** | 0,83 |
| Coincidencia con la respuesta jurídica | **0,70** | 0,41 |
| Exactitud global | **0,72** | 0,59 |
| Evidencia necesaria encontrada | 0,80 | 0,82 |
| Documento correcto encontrado | 0,55 | 0,57 |
| Tiempo promedio por respuesta | 61 s | **19 s** |
| Costo de responder las 66 preguntas | 0,23 USD | **0 USD** |
| Preguntas pertinentes rechazadas | 1 | 1 |

### 5.2 Por tipo de pregunta (coincidencia con la respuesta jurídica)

| Tipo de pregunta | gpt-5-nano | gemma4:e2b |
|---|---:|---:|
| 1. Extracción puntual | 0,00 | 0,42 |
| 2. Síntesis dentro de un documento | 0,74 | 0,36 |
| 3. Cruce entre documentos | 0,72 | 0,34 |
| 4. Comparación jurídica | 0,74 | 0,45 |
| 5. Aplicación normativa o jurisprudencial | 0,75 | 0,43 |
| 6. Secuencia, trámite u orden jurídico | 0,54 | 0,36 |

*El tipo 1 tiene solo 2 preguntas y uno de sus ceros es un error del evaluador (§10 del anexo técnico); no permite conclusiones.*

### 5.3 Qué significa

- **Ambos modelos encuentran información equivalente** (evidencia necesaria encontrada: 0,80 frente a 0,82), aunque no siempre los mismos fragmentos. La diferencia principal no está en la búsqueda.
- **Ambos son fieles a sus fuentes** y ninguno inventó información.
- **La diferencia está en cómo redacta la respuesta.** El modelo local escribe respuestas de la mitad de largo y con frecuencia **no llega a la conclusión**: dice que "el contexto no especifica" cuando la información sí estaba (ver el ejemplo de la §6.5). Por eso coincide mucho menos con la respuesta jurídica.
- **A favor del modelo local:** en nuestras pruebas fue más rápido, no tiene costo por consulta y no envía las preguntas de los usuarios a un tercero.
- **Conclusión:** hoy el modelo local **no es un reemplazo adecuado** del sistema actual para orientar a usuarios. Su punto débil es aprovechar la información que encuentra, no encontrarla: mejorar la búsqueda (propuestas 1 y 2 de la §7) beneficia a ambos modelos, pero para el modelo local lo decisivo sería darle instrucciones más precisas (propuesta 3) y volver a medir.
- **El radicado equivocado** de la pregunta 062 lo dan los dos modelos, porque ambos recibieron el fragmento del otro proceso: es un problema de la búsqueda, no del modelo (§6.2).
- **Cada modelo rechazó una pregunta pertinente distinta** (el sistema actual la 046 y el modelo local la 063). El filtro de temas depende del modelo, así que conviene revisarlo (propuesta 5 de la §7).


## 6. Ejemplos concretos

### 6.1 No encontró la norma vigente: el trámite del REMAC 5 (pregunta 003)

*Pregunta:* unos socios quieren un club náutico con muelle flotante en Santa Marta. ¿Basta con la concesión ante la Capitanía de Puerto?

- **Respuesta del equipo jurídico:** describe el procedimiento del **REMAC 5** en etapas: solicitud con memoria georreferenciada, **certificaciones de siete entidades**, archivo si alguna es desfavorable y **30 días hábiles de publicidad**.
- **Respuesta de ATLAS:** describe el procedimiento del **Decreto 2324 de 1984 (art. 169)**, porque no encontró el REMAC 5. Está bien citada, pero **omite las etapas vigentes.**

### 6.2 Dato equivocado: el número de radicado (pregunta 062)

*Pregunta:* ¿cuál es el número de radicación de la sentencia de segunda instancia del cerramiento de la playa Los Cocos?

- **Equipo jurídico:** `47-001-3333-005-2010-00684-01` (caso Lemus Orozco).
- **ATLAS:** `47001-2332-000-2011-08425-02`, que corresponde a **otro proceso** (la segunda instancia del caso Carrero). Para un abogado o un actor popular, este error es grave.

### 6.3 Respuesta correcta (pregunta 002)

*Pregunta:* motos acuáticas y parasailing cerca de bañistas en El Rodadero. ¿DIMAR fija zonas?

- ATLAS coincide con el equipo jurídico: hay zonas de deportes náuticos delimitadas con boyas, DIMAR ejerce el control y se puede acudir a la Capitanía. Cita el reglamento de playas de Santa Marta en lugar del Decreto 2324 que señaló el equipo jurídico.

### 6.4 Pregunta pertinente rechazada (pregunta 046)

*Pregunta:* "Mi licencia de construcción fue suspendida por una medida cautelar… ¿ese tiempo se descuenta de la vigencia?". Proviene del caso Lemus Orozco (muro en playa Los Cocos).

- ATLAS respondió que la consulta está **fuera del ámbito**, porque no menciona la playa. Un ciudadano recibiría esa respuesta ante una pregunta pertinente.

### 6.5 Misma evidencia, distinta respuesta: sistema actual frente a modelo local (pregunta 013)

*Pregunta:* organizadores de un campeonato de fútbol playa en Cartagena quieren dejar instaladas graderías y carpas un mes entre torneos. ¿Pueden hacerlo, o hay alguna obligación cuando termina el permiso?

- **Equipo jurídico:** **No.** Al terminar el permiso temporal deben entregar el área en las mismas condiciones; para otro evento deben tramitar de nuevo el permiso conforme al REMAC 5.
- **Sistema actual (gpt-5-nano):** **"No.** No pueden dejar instalada la infraestructura hasta el siguiente torneo sin gestionar extensión o un nuevo permiso…". Coincide con el equipo jurídico.
- **Modelo local (gemma4:e2b):** explica que deben cumplir las fechas autorizadas, pero concluye que *"el contexto no especifica qué sucede… una vez finalizada la actividad"*. **No responde la pregunta**, aunque tenía la misma información.


## 7. Dónde falla y qué proponemos

Ninguna de estas propuestas se ha aplicado todavía. Cada una se probaría por separado y se mediría con este mismo procedimiento, para saber si de verdad mejora.

| # | Problema | Propuesta |
|---|---|---|
| 1 | No encuentra el REMAC 5 ni el Decreto 2324 | Mejorar la búsqueda de la normativa nacional, por ejemplo dando más peso a las coincidencias exactas de términos jurídicos y reforzando la identificación de cada artículo |
| 2 | Las preguntas que cruzan varios documentos se quedan con uno solo | Hacer que ATLAS consulte fragmentos de documentos distintos y no varios del mismo |
| 3 | Los trámites salen incompletos | Pedirle explícitamente que enumere todos los pasos, en orden y con la norma que los rige |
| 4 | A veces prefiere una norma anterior a la vigente | Indicarle que priorice la norma vigente de mayor jerarquía |
| 5 | Rechaza preguntas pertinentes que no dicen "playa" | Hacer menos estricto el filtro de temas, por ejemplo con licencias y obras costeras |
| 6 | Tarda un minuto por respuesta | Ajustar cuánto "razona" el modelo antes de responder, sin perder calidad |

## 8. Asuntos de los datos que requieren al equipo jurídico

| # | Asunto | Por qué importa |
|---|---|---|
| 1 | **La numeración SM-XX del Excel no coincide con la del corpus.** Por ejemplo, en el Excel SM-01 es el caso *Lemus Orozco*; en el corpus, SM-01 es *Procuraduría vs Corpamag* y *Lemus Orozco* es SM-04 | Si ATLAS muestra un código SM a un usuario, podría señalar otro documento. Hay que definir cuál numeración es la oficial |
| 2 | **Los tipos de pregunta del Excel (6) no son los que se nombraron en la reunión** (localización, extracción, síntesis, relación causal, juicio de valor) | Definir cuál clasificación se usará para medir |
| 3 | **39 de las 66 preguntas no tienen revisor** registrado | Conviene completar la revisión, sobre todo antes de calibrar |
| 4 | **No hay preguntas "fuera del corpus"** | Sin ellas no se puede medir si ATLAS reconoce cuándo no tiene información para responder |

## 9. Registro de evaluaciones

Cada evaluación queda anotada en un registro (`docs/REGISTRO_EVALUACIONES.md` en el repositorio) con la fecha, la versión del sistema, el modelo utilizado y sus resultados principales. Así se puede ver con datos si cada cambio a ATLAS lo mejora o lo empeora.

| Fecha | Modelo que responde | Respuestas correctas | Coincidencia con la respuesta jurídica | Fidelidad | Tiempo por respuesta | Costo |
|---|---|---:|---:|---:|---:|---:|
| 2026-10-08 | gpt-5-nano (sistema actual) | 51 / 65 | 0,70 | 0,87 | 61 s | 0,23 USD |
| 2026-10-14 | gemma4:e2b (local) | 32 / 65 | 0,41 | 0,83 | 19 s | 0 USD |

Ambas corridas evaluaron la misma versión del sistema (`4c2186e`) con el mismo evaluador (gpt-5-nano).

## 10. Decisiones que necesitamos del equipo jurídico

1. **¿Qué fuente debe citar ATLAS** cuando el contenido está tanto en el REMAC 5 como en un reglamento local o en una sentencia? ¿La norma vigente de mayor jerarquía?
2. **¿Cuál numeración SM-XX es la oficial?** (§8, asunto 1)
3. **¿Qué clasificación de tipos de pregunta usaremos?** (§8, asunto 2)
4. **¿Pueden revisar las 14 respuestas que no salieron correctas** para confirmar el diagnóstico del evaluador?
5. **¿Pueden aportar preguntas "fuera del corpus"** para medir si ATLAS sabe decir que no tiene la información?
6. **¿Interesa seguir explorando un modelo local** (sin costo por consulta y sin enviar datos a terceros), aceptando por ahora una calidad menor, o mantenemos el modelo actual mientras mejoramos la búsqueda?

---

*Anexo técnico:* el detalle de las métricas, la reproducción de la evaluación y el código están en el repositorio, rama `julian-rincon/evaluacion-ragas-linea-base` (`rag/docs/EVALUACION_LINEA_BASE.md`).
