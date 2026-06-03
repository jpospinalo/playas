# Tutorial de construcción del ground truth · Proyecto ATLAS

> **Dirigido a los profesionales en derecho** que participan en la evaluación del sistema ATLAS.
> No se requiere ningún conocimiento técnico fuera del área jurídica.

---

## 1. Para qué sirve este tutorial

Este tutorial le explica, paso a paso, cómo construir el conjunto de preguntas y respuestas de referencia (el *ground truth*) que el equipo del proyecto usará para medir qué tan bien responde el sistema ATLAS.

Su aporte consiste en dos cosas: **formular preguntas** sobre los documentos del corpus y **redactar la respuesta correcta** a cada una de ellas desde su perspectiva como experto en derecho costero y de playas. Ese par pregunta-respuesta es el patrón de medición: cuando ATLAS reciba la misma pregunta, su respuesta se comparará con la suya para determinar si el sistema acierta.

No necesita manejar ninguna herramienta informática especial. Solo necesita acceso al **OneDrive compartido del proyecto**, donde están los documentos, y este tutorial como guía.

---

## 2. El sistema ATLAS y los documentos a los que tiene acceso

ATLAS es un asistente de consulta jurídica especializado en playas y dominio público marítimo-terrestre colombiano. Cuando alguien le formula una pregunta, el sistema busca la respuesta dentro de un corpus documental fijo y cerrado.

**El sistema únicamente tiene acceso a los siguientes documentos:**

### Jurisprudencia: Tribunal Administrativo del Magdalena (10 sentencias)

| # | Documento |
|:---:|---|
| 1 | AP Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros |
| 2 | AP Felipe José Campo Fernández VS Corpamag y otros |
| 3 | AP Gabriel Antonio Carrero VS DIMAR y otros |
| 4 | AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Marta y otros |
| 5 | AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros |
| 6 | AP Inversiones E y D S.A.S VS DIMAR y otros |
| 7 | AP Miguel Ángel Enciso VS Distrito y otros |
| 8 | AP Procuraduría General de la Nación VS Corpamag y otros |
| 9 | AP Rodrigo Martínez Silva VS Minambiente y otros |
| 10 | Sentencia de Segunda Instancia 47001-2332-000-2011-08425-02 (Gabriel Carrero) |

### Normativa (2 documentos)

| # | Documento |
|:---:|---|
| 1 | Decreto 2324 de 1984 |
| 2 | Reglamento Marítimo Colombiano REMAC 5 - DIMAR (edición 2021) |

> **Tenga esto siempre presente:** todas las preguntas que usted formule deben poder responderse a partir de uno o más de estos documentos. Si la respuesta correcta depende de doctrina, normativa o jurisprudencia que no está en esta lista, la pregunta no es válida para este ejercicio.

---

## 3. Qué es el ground truth y por qué importa su criterio

El *ground truth* es, en términos sencillos, el solucionario del examen. Usted formula las preguntas y escribe la respuesta correcta como lo haría un experto que acaba de leer el documento. Cuando el equipo técnico evalúe a ATLAS, le hará las mismas preguntas y cotejará las respuestas del sistema con las suyas.

Si ATLAS responde igual que usted en lo sustancial, el sistema está funcionando bien. Si hay diferencias relevantes, ahí está el error que hay que corregir.

Su participación es insustituible porque determinar si una respuesta sobre dominio público marítimo-terrestre, concesiones de playa o jurisprudencia del Tribunal Administrativo del Magdalena es correcta, incompleta o errada requiere criterio jurídico especializado. Ese criterio es el que usted aporta.

---

## 4. Volumen de trabajo

Usted debe trabajar un documento a la vez. Para cada uno de los 12 documentos del corpus formulará **10 preguntas** (una por cada tipo descrito en la Sección 5) acompañadas de su respuesta de referencia.

| Tipo de documento | N.º de documentos | Preguntas por documento | Total |
|---|:---:|:---:|:---:|
| Jurisprudencia (sentencias TAM) | 10 | 10 | 100 |
| Normativa | 2 | 10 | 20 |
| **Total** | **12** | **10** | **120** |

La regla fundamental es: **cierre un documento antes de abrir el siguiente**. No deje documentos con preguntas a medias.

---

## 5. Los 10 tipos de pregunta: explicación y ejemplos

Cada tipo de pregunta está diseñado para verificar que el sistema sea capaz de hacer algo distinto: encontrar un dato, aplicar una regla, conectar información de varias secciones, comparar documentos, etc. A continuación se explica cada uno con ejemplos aplicados al tipo de documentos que usted va a trabajar.

---

### Tipo 1 · Pregunta literal

**Qué verifica:** que el sistema localice y reproduzca fielmente un dato que figura textualmente en el documento.

**Cómo redactarla:** identifique un dato concreto y explícito del documento (un plazo, una fecha, un número de artículo, el nombre de una entidad demandada, una cifra) y pregunte por él de manera directa. La respuesta debe poder darse con una cita del texto.

**Qué debe contener su respuesta:** el dato exacto tal como aparece en el documento y la referencia al lugar donde se encuentra (artículo, numeral del resuelve, considerando, etc.).

> **Ejemplo:**
> *Pregunta:* ¿Qué plazo fijó el Tribunal Administrativo del Magdalena para que DIMAR cumpliera la orden de remoción en la sentencia de la acción popular de Gerardo Antenor Lemus Orozco?
>
> *Respuesta de referencia:* [Plazo exacto tal como aparece en el numeral correspondiente del resuelve, con referencia a ese numeral.]

---

### Tipo 2 · Pregunta parafraseada

**Qué verifica:** que el sistema comprenda la pregunta aunque esté formulada con palabras distintas a las del documento.

**Cómo redactarla:** tome un contenido del documento y redacte la pregunta con su propio vocabulario, evitando copiar expresiones literales del texto. Piense en cómo formularía esa pregunta alguien que no conoce el documento pero sí el tema.

**Qué debe contener su respuesta:** la misma información que daría si la pregunta hubiera empleado las palabras exactas del documento.

> **Ejemplo:**
> En lugar de preguntar *"¿qué establece el artículo X sobre la franja de bajamar?"*, redacte: *"¿qué parte de la orilla del mar queda fuera del alcance de los particulares cuando la marea baja, según el Decreto 2324 de 1984?"*
>
> La respuesta es idéntica en ambos casos; solo difiere el punto de partida de la pregunta.

---

### Tipo 3 · Pregunta de dato puntual

**Qué verifica:** que el sistema extraiga un único dato sin añadir información que no se solicitó.

**Cómo redactarla:** pida un solo elemento: número de radicado, nombre del magistrado ponente, fecha del fallo, número de artículo, nombre de la norma citada en la sentencia. La respuesta ideal cabe en una sola línea.

**Qué debe contener su respuesta:** únicamente el dato solicitado. Si quiere precisar de qué parte del documento proviene, hágalo en una nota breve separada de la respuesta.

> **Ejemplo:**
> *Pregunta:* ¿Cuál es el número de radicado de la acción popular instaurada por Felipe José Campo Fernández?
>
> *Respuesta de referencia:* [Número de radicado exacto.]

---

### Tipo 4 · Pregunta de definición

**Qué verifica:** que el sistema identifique y reproduzca definiciones jurídicas o técnicas que el documento establece de manera formal.

**Cómo redactarla:** pida la definición de un concepto que el documento defina explícitamente. El Decreto 2324 de 1984 y el REMAC 5 contienen múltiples definiciones formales; las sentencias suelen citarlas o aplicarlas.

**Qué debe contener su respuesta:** la definición tal como la formula el documento, con la cita del artículo o sección. Si el documento usa el concepto sin definirlo formalmente, indíquelo: **no complemente la respuesta con fuentes externas**.

> **Ejemplo:**
> *Pregunta:* ¿Cómo define el Decreto 2324 de 1984 el concepto de "playa marítima"?
>
> *Respuesta de referencia:* [Definición textual del artículo correspondiente + número del artículo.]

---

### Tipo 5 · Pregunta procedimental

**Qué verifica:** que el sistema explique una secuencia de actuaciones o trámite en el orden correcto, sin saltarse ni agregar pasos.

**Cómo redactarla:** pregunte por un procedimiento o secuencia que el documento describa. En las sentencias: la secuencia de actuaciones procesales (admisión, notificaciones, traslados, pruebas, fallo); en la normativa: el trámite para obtener una concesión, permiso o autorización.

**Qué debe contener su respuesta:** los pasos en el orden en que aparecen en el documento, sin agregar etapas que el texto no mencione explícitamente.

> **Ejemplo:**
> *Pregunta:* ¿Qué actuaciones procesales describe la sentencia de la acción popular de Inversiones E y D S.A.S desde la admisión de la demanda hasta el fallo de primera instancia?
>
> *Respuesta de referencia:* [Secuencia de actuaciones en el orden en que aparecen en el documento.]

---

### Tipo 6 · Pregunta condicional

**Qué verifica:** que el sistema aplique correctamente una regla jurídica cuando se presenta el supuesto de hecho que la activa.

**Cómo redactarla:** plantee un supuesto concreto y pregunte qué establece el documento que debe ocurrir en ese caso. Este tipo es especialmente útil con la normativa (Decreto 2324, REMAC 5) y con los considerandos de las sentencias donde el Tribunal aplica una regla a una situación específica.

**Qué debe contener su respuesta:** la regla que aplica al supuesto, su fundamento en el documento y, si el documento contempla varias condiciones o excepciones, la distinción entre ellas.

> **Ejemplo:**
> *Pregunta:* Según el Decreto 2324 de 1984, ¿qué consecuencias jurídicas acarrea construir en zona de bajamar sin autorización de la Dirección General Marítima?
>
> *Respuesta de referencia:* [Consecuencias previstas en el artículo correspondiente + número del artículo.]

---

### Tipo 7 · Pregunta de integración dentro del mismo documento

**Qué verifica:** que el sistema conecte información que está dispersa en dos o más partes del mismo documento para construir una respuesta completa.

**Cómo redactarla:** plantee una pregunta cuya respuesta exija relacionar elementos de secciones distintas del mismo documento. En una sentencia: conectar una pretensión de la parte expositiva con la decisión del resuelve; o un considerando con un numeral de la parte resolutiva. En la normativa: relacionar una disposición del articulado con la definición que la fundamenta.

**Qué debe contener su respuesta:** la síntesis articulada de los dos fragmentos, indicando de qué sección o artículo proviene cada uno.

> **Ejemplo:**
> *Pregunta:* ¿Cuál fue la pretensión principal de los accionantes en la acción popular de Carlos Alberto Zúñiga Mejía y de qué manera se pronunció el Tribunal sobre ella en la parte resolutiva?
>
> *Respuesta de referencia:* [Pretensión identificada en la parte expositiva + decisión del Tribunal en el resuelve + referencia a ambas secciones.]

---

### Tipo 8 · Pregunta que cruza dos documentos del corpus

**Qué verifica:** que el sistema combine información de más de un documento del corpus para construir una respuesta completa.

**Cómo redactarla:** identifique un punto de conexión entre dos documentos del corpus. Las sentencias suelen invocar el Decreto 2324 o el REMAC 5; dos sentencias pueden referirse al mismo predio, al mismo tramo de playa o a la misma entidad. Formule una pregunta cuya respuesta exija consultar ambos documentos.

**Qué debe contener su respuesta:** la información extraída de cada documento, claramente atribuida a su fuente, y la conclusión que resulta de combinarlas.

> **Ejemplo:**
> *Pregunta:* ¿Qué disposición del Decreto 2324 de 1984 invoca el Tribunal Administrativo del Magdalena en la sentencia de la acción popular de Rodrigo Martínez Silva, y cuál es el texto exacto de esa disposición en el decreto original?
>
> *Respuesta de referencia:* [Cita de la sentencia donde se invoca la norma + texto del artículo en el decreto + referencia a ambas fuentes.]

---

### Tipo 9 · Pregunta comparativa

**Qué verifica:** que el sistema contraste posturas, decisiones o reglas con un criterio claro y explicit.

**Cómo redactarla:** pida una comparación con un criterio definido. Puede comparar la postura de dos entidades demandadas dentro de una misma sentencia, el tratamiento que dan a un mismo problema jurídico dos sentencias distintas, o las obligaciones que impone el Decreto 2324 frente a las que establece el REMAC 5 sobre un mismo asunto.

**Qué debe contener su respuesta:** los elementos comparados, el criterio de comparación y las diferencias o coincidencias relevantes, con fundamento textual en cada fuente citada.

> **Ejemplo:**
> *Pregunta:* ¿En qué se diferencian las medidas de protección ordenadas por el Tribunal en la sentencia de Miguel Ángel Enciso y en la de Felipe José Campo Fernández respecto al uso ilegal de playas?
>
> *Respuesta de referencia:* [Medidas ordenadas en cada sentencia + criterio de diferenciación + referencias a cada providencia.]

---

### Tipo 10 · Pregunta de ordenamiento

**Qué verifica:** que el sistema ordene elementos del corpus según un criterio explícito y verificable.

**Cómo redactarla:** pida una lista ordenada de elementos presentes en el corpus. El criterio puede ser temporal (sentencias por fecha de fallo), jerárquico (normas citadas por rango), por destinatario (entidades a quienes van dirigidas las órdenes del resuelve), por relevancia u otro que sea verificable con los documentos.

**Qué debe contener su respuesta:** la lista en el orden correcto, el criterio de ordenamiento utilizado y una justificación breve con base en los documentos.

> **Ejemplo:**
> *Pregunta:* Ordene de más antigua a más reciente, según la fecha del fallo, las sentencias del Tribunal Administrativo del Magdalena disponibles en el corpus.
>
> *Respuesta de referencia:* [Lista ordenada cronológicamente + fecha de cada sentencia + referencia a la fuente de cada dato.]

---

## 6. Procedimiento paso a paso

Siga esta secuencia para cada documento:

**Paso 1. Lea el documento completo antes de redactar nada.**
Descárguelo del OneDrive y léalo en su totalidad. No intente formular preguntas mientras lee; primero conózcalo. Anote mentalmente (o en un borrador) los datos, definiciones, procedimientos y decisiones que puedan servir para las distintas categorías.

**Paso 2. Identifique los elementos clave.**
Antes de escribir la primera pregunta, haga un inventario rápido: ¿qué partes tiene el documento?, ¿qué entidades intervienen?, ¿qué fechas y plazos aparecen?, ¿qué normas se citan?, ¿qué decisiones o mandatos contiene?, ¿hay definiciones formales?

**Paso 3. Recorra los 10 tipos en orden.**
Tome los tipos del 1 al 10 y para cada uno redacte la pregunta y su respuesta de referencia antes de pasar al siguiente. No escriba primero todas las preguntas para luego responderlas: pregunta y respuesta se redactan juntas.

**Paso 4. No deje ningún tipo sin cubrir.**
Si un tipo de pregunta no encaja bien con el documento en cuestión (por ejemplo, una norma que no describe pasos procedimentales), formule la pregunta más cercana posible y añada una nota breve explicando por qué el tipo no se acomoda del todo. No omita el tipo.

**Paso 5. Cierre el documento y márquelo en su lista.**
Solo cuando tenga las 10 preguntas respondidas, marque el documento como terminado y pase al siguiente.

---

## 7. Criterios de una buena respuesta de referencia

Una respuesta de referencia es útil para el proyecto cuando cumple estas condiciones:

- **Es verificable:** quien lea el documento fuente puede confirmar que la respuesta es correcta y completa.
- **Cita la fuente:** indica el artículo, numeral, sección o considerando donde se encuentra la información.
- **No incorpora fuentes externas:** se basa exclusivamente en lo que dice el documento del corpus, no en lo que usted conoce de otras normas o sentencias ajenas a la lista.
- **Tiene la extensión justa:** responde exactamente lo que se pregunta, sin extenderse ni quedarse corta.
- **Usa terminología técnico-jurídica precisa:** emplee el lenguaje que corresponde al área (dominio público marítimo-terrestre, zona de bajamar, acción popular, parte resolutiva, etc.).

---

## 8. Cómo entregar el material

Entregue todo el trabajo en **un único documento** (Word, PDF o texto plano) con la siguiente organización mínima para cada documento trabajado:

```
DOCUMENTO: [Nombre tal como aparece en el OneDrive]
TIPO: jurisprudencia / normativa

Tipo 1: Literal
  Pregunta: ...
  Respuesta: ...
  Nota (opcional): ...

Tipo 2: Parafraseada
  Pregunta: ...
  Respuesta: ...
  ...
```

No necesita usar ningún formato especial ni llenar hojas de cálculo. El equipo del proyecto se encargará de convertir su entrega al formato que requiere el sistema.
