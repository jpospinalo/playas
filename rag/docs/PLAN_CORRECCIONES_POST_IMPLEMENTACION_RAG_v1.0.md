# Plan de correcciones posteriores a la implementación del módulo RAG — v1.0

**Rama obligatoria:** `v2`  
**Alcance:** correcciones técnicas confirmadas mediante revisión del código local  
**Ejecutor:** IA implementadora  
**Objetivo:** corregir defectos residuales de configuración, concurrencia, pruebas, eficiencia y modularidad sin alterar el comportamiento jurídico o funcional que ya está aprobado.

---

## 1. Resultado esperado

Al terminar este plan, el repositorio debe conservar el mismo comportamiento funcional del RAG, pero con estas mejoras:

1. La configuración cargada desde `.env` o `RAG_ENV_FILE` debe estar disponible antes de que la base de datos y la autenticación fijen sus constantes.
2. Las pruebas deben pasar tanto en un checkout limpio como en un entorno de desarrollo que tenga un `.env` real.
3. Los locks por conversación no deben acumular claves históricas indefinidamente.
4. Una solicitud que espera el lock de su conversación no debe ocupar todavía un slot global de backpressure.
5. El endpoint SSE debe quedar cubierto frente a concurrencia, errores, cancelación y liberación de recursos.
6. Un batch de vectorización exitoso debe ejecutarse una sola vez, no tres.
7. El adaptador de evaluación no debe invertir la dependencia entre `core` y `api`.
8. El código y la documentación no deben presentar como operativas funciones o evaluaciones que siguen pendientes.

Este plan no pretende recalibrar la clasificación jurídica, cambiar la recuperación ni mejorar el corpus.

---

## 2. Restricciones obligatorias

La IA implementadora debe respetar todas estas restricciones:

- Trabajar exclusivamente en la rama `v2`.
- No hacer `push`. El usuario realizará el push manualmente.
- No modificar HTTP por HTTPS ni exigir certificados.
- No acceder a AWS, Chroma u Ollama reales.
- No ejecutar scripts contra hosts remotos.
- No escribir, borrar ni recrear colecciones de Chroma.
- No reindexar documentos.
- No cambiar modelos, dimensiones de embeddings ni formatos vectoriales.
- No modificar `rag/core/prompts.py`.
- No modificar las reglas, expresiones regulares, señales o precedencias del clasificador de alcance en `query_enricher.py`.
- No modificar el banco jurídico de 21 preguntas ni debilitar sus expectativas.
- No cambiar pesos BM25/vector, RRF, `k`, `k_candidates`, filtros por `doc_type`, reglas de citas o respuestas de abstención.
- No cambiar nodos, aristas o rutas del grafo LangGraph.
- No cambiar campos, tipos, nombres, códigos HTTP o estructura pública de `/api/query` y `/api/query/stream`.
- Mantener `RAG_BACKPRESSURE_MODE=off` como valor predeterminado.
- Mantener `OllamaReranker`; su retiro no forma parte de este plan.
- No actualizar dependencias de LangChain, RAGAS, Chroma u Ollama dentro de este plan.
- No corregir `ingesta/`; este plan se limita a `rag/` y al workflow que lo valida.

No se deben modificar pruebas para ocultar un defecto. Todo cambio de expectativa debe estar justificado por una corrección explícita del contrato; si eso fuera necesario, detener la tarea y consultar al usuario.

---

## 3. Estado base que debe registrar la IA

Antes de modificar archivos:

1. Confirmar que la rama activa es `v2`.
2. Registrar `git status --short --branch`.
3. Confirmar que no existen cambios locales ajenos. Si existen, no sobrescribirlos y detenerse si se superponen con este plan.
4. Registrar el commit inicial.
5. Ejecutar, sin cobertura y sin tocar servicios reales:

   ```bash
   cd rag
   uv run pytest tests/unit/ -p no:cacheprovider
   uv run ruff check backend/rag/ tests/ evaluation/
   uv run ruff format --check backend/rag/ tests/ evaluation/
   uv run mypy backend/rag/
   ```

6. Si el `.venv` local contiene enlaces rotos o fue creado en otro sistema operativo, recrearlo localmente con `uv`; no versionar `.venv` ni modificar el lockfile por esta acción.
7. Registrar por separado si la suite pasa en un entorno limpio pero falla con el `.env` real. La línea base conocida es:
   - checkout limpio: 455 pruebas pasan;
   - copia local con `.env`: tres pruebas de alias/configuración pueden fallar por falta de aislamiento.

No usar el número 455 como una meta rígida después de retirar pruebas de código muerto; la condición final es que todas las pruebas vigentes pasen y que el banco jurídico permanezca intacto.

---

## 4. Estrategia de implementación

Ejecutar una entrega por vez. Cada entrega debe seguir este ciclo:

1. Añadir primero una prueba que reproduzca el defecto cuando corresponda.
2. Verificar que esa prueba falla por el motivo esperado.
3. Implementar el cambio mínimo.
4. Ejecutar las pruebas dirigidas.
5. Ejecutar la suite completa, Ruff y mypy.
6. Revisar el diff para confirmar que no hay cambios fuera del alcance.
7. Crear un commit independiente únicamente si todo está en verde.

No agrupar todas las correcciones en un único commit.

---

## 5. Entregas inmediatas

### C1 — Corregir el orden y la autoridad de configuración

**Problema confirmado**

`rag.api.rate_limit` importa `rag.api.auth` antes de importar `rag.config`; `auth` importa `database`, y ambos fijan algunas variables mediante `os.getenv()` antes de que `rag.config` cargue el `.env`.

Con un `RAG_ENV_FILE` controlado se comprobó que actualmente no se aplican a tiempo:

- `DATABASE_URL`;
- `JWT_ALGORITHM`;
- `JWT_EXPIRE_MINUTES`.

**Archivos esperados**

- `rag/backend/rag/config.py`
- `rag/backend/rag/api/database.py`
- `rag/backend/rag/api/auth.py`
- `rag/backend/rag/api/routes/auth.py`, solo si se centraliza `REGISTER_ENABLED`
- pruebas de configuración
- `.env.example`, únicamente para documentar variables ya existentes o nuevas de este plan

**Implementación requerida**

1. Definir en `rag.config` las constantes tipadas necesarias para base de datos y JWT.
2. Hacer que `database.py` importe `DATABASE_URL` desde `rag.config`.
3. Hacer que `auth.py` importe `JWT_ALGORITHM` y `JWT_EXPIRE_MINUTES` desde `rag.config`.
4. Mantener la validación de `JWT_SECRET_KEY` y el mismo mensaje de error actual.
5. No registrar ni imprimir claves o URLs con credenciales.
6. Centralizar `REGISTER_ENABLED` solo si puede demostrarse equivalencia exacta.
7. No resolver el problema agregando llamadas adicionales y dispersas a `load_dotenv()`.

**Pruebas obligatorias**

- Importar `rag.api.main` en un subproceso limpio con un `RAG_ENV_FILE` temporal y comprobar que los valores no predeterminados de DB/JWT fueron aplicados.
- Comprobar que las variables reales del proceso siguen teniendo precedencia sobre `.env`.
- Comprobar que un `RAG_ENV_FILE` inexistente continúa fallando explícitamente.
- Mantener las pruebas de autenticación actuales.

**Criterio de aceptación**

No debe depender del orden accidental de imports para cargar configuración.

---

### C2 — Hacer herméticas las pruebas de configuración

**Problema confirmado**

`test_config_env_resolution.py::_minimal_env()` elimina `RAG_ENV_FILE`. Los subprocesos vuelven a descubrir el `.env` real del proyecto y contaminan los casos que intentan simular un entorno vacío o usar solo un alias.

**Implementación requerida**

1. Crear en las pruebas un archivo `.env` temporal vacío.
2. Pasarlo explícitamente como `RAG_ENV_FILE` a los subprocesos que necesiten un entorno sin configuración.
3. Permitir que cada prueba lo sustituya por su archivo temporal cuando quiera validar carga real.
4. No renombrar, borrar ni modificar el `.env` real del desarrollador.
5. No debilitar las aserciones sobre precedencia de alias.

**Pruebas obligatorias**

Ejecutar `test_config_env_resolution.py`:

- en el repositorio real con `.env` presente;
- en un checkout/copia limpia sin `.env`.

Ambos casos deben pasar.

---

### C3 — Administrar correctamente el ciclo de vida de locks

**Problema confirmado**

`ConversationLockRegistry` usa un `defaultdict` que conserva cada `thread_id` para siempre. Su docstring afirma incorrectamente que el tamaño está limitado a las conversaciones en vuelo.

**Implementación requerida**

1. Sustituir la entrega de locks crudos por un context manager asíncrono administrado, por ejemplo `hold(thread_id)`.
2. Mantener una entrada por conversación con:
   - `asyncio.Lock`;
   - contador de usuarios que incluya al titular y a quienes esperan.
3. Incrementar el contador antes de esperar el lock.
4. Ante éxito, excepción o cancelación:
   - liberar el lock solo si fue adquirido;
   - decrementar el contador;
   - eliminar la entrada únicamente cuando el contador llegue a cero y siga siendo la misma entrada registrada.
5. Proteger la creación/eliminación de entradas frente a carreras sin introducir un lock global que cubra el procesamiento de consultas.
6. El lock global de registro, si existe, solo puede proteger operaciones breves de diccionario/contador; nunca debe mantenerse durante un `await` de red, DB, Chroma o LLM.

**Pruebas obligatorias**

- Dos turnos del mismo `thread_id` continúan serializados y no pierden mensajes.
- Conversaciones diferentes continúan en paralelo.
- Después de procesar muchas claves únicas secuencialmente, el registro queda vacío.
- Cancelar una tarea mientras espera un lock no deja referencias ni un lock bloqueado.
- Una excepción dentro del context manager limpia correctamente la entrada.

**Criterio de parada**

Si para limpiar entradas fuera necesario debilitar la serialización demostrada en T3.5, detener la entrega y documentar el caso.

---

### C4 — Corregir el orden entre lock y backpressure

**Problema confirmado**

Los endpoints adquieren primero un slot global de backpressure y luego esperan el lock de conversación. Varias solicitudes de una misma conversación pueden ocupar la capacidad global sin estar ejecutando trabajo costoso.

**Implementación requerida**

1. Adquirir primero el lock administrado de conversación.
2. Adquirir después el slot de backpressure, inmediatamente antes del trabajo que consume recursos.
3. Mantener el mismo orden en `/api/query` y `/api/query/stream` para evitar diferencias y futuros deadlocks.
4. Si backpressure rechaza con 503, liberar inmediatamente el lock de conversación.
5. Conservar:
   - 503 para saturación;
   - `Retry-After` actual;
   - `off` como predeterminado;
   - los errores 404/422 de hidratación previos al `StreamingResponse`.

**Prueba de equidad obligatoria**

Con capacidad global 2:

- una consulta de la conversación A ocupa un slot;
- una segunda consulta de A espera su lock sin ocupar el segundo slot;
- una consulta de la conversación B puede usar el segundo slot y avanzar.

La prueba debe fallar con el orden anterior y pasar con el nuevo.

---

### C5 — Cubrir el endpoint SSE y la liberación de recursos

**Problema confirmado**

Las pruebas actuales de wiring de backpressure solo llaman a `/api/query`, aunque el archivo afirma cubrir también `/api/query/stream`. El SSE es la ruta utilizada por el frontend y contiene manejo manual de recursos.

**Implementación requerida**

Añadir pruebas reales del handler SSE, sin servicios externos, que cubran:

1. Modo `enforce`: devuelve 503 antes de construir el stream cuando no hay capacidad.
2. Modo `off`: conserva el comportamiento previo.
3. Dos turnos concurrentes del mismo hilo no se intercalan.
4. Hilos diferentes pueden avanzar en paralelo.
5. Excepción de `graph.astream`: se emite el evento SSE de error actual y se liberan lock, slot y contador activo.
6. Cancelación/cierre anticipado después de iniciar el iterador: se liberan todos los recursos.
7. Finalización normal: `[DONE]`, fuentes y metadatos mantienen su estructura actual.
8. Los eventos de estado y respuesta no cambian de nombre ni formato.

**Condición adicional**

No convertir esta corrección en una abstracción general de streaming. Usar el mínimo helper compartido necesario para evitar duplicar el protocolo de adquisición/liberación.

---

### C6 — Corregir el ciclo de reintentos de vectorización sin reindexar

**Problema confirmado**

`core/vectorstore.py` no sale del ciclo `for attempt in range(MAX_RETRIES)` después de un `collection.add()` exitoso. Un batch correcto vuelve a calcular embeddings y vuelve a enviarse hasta completar las tres iteraciones.

**Implementación requerida**

1. Añadir una salida explícita del ciclo después del éxito.
2. Mantener `MAX_RETRIES`, backoff y mensajes actuales para fallos.
3. No ejecutar `build_or_load_vectorstore()` contra infraestructura real.
4. No cambiar endpoint, modelo, dimensión o formato de embeddings.
5. No implementar todavía `/api/embed` por lotes. La versión de Ollama en AWS debe comprobarse y la reindexación debe coordinarse antes de ese cambio.

**Pruebas obligatorias con dobles locales**

- Éxito en el primer intento: embeddings y `collection.add` se invocan exactamente una vez.
- Dos fallos transitorios y un éxito: exactamente tres intentos y ningún cuarto intento.
- Tres fallos: se conserva el `RuntimeError` final.
- Parchear `time.sleep` para que las pruebas no esperen realmente.

Esta corrección modifica código relacionado con indexación, pero no requiere ni autoriza ejecutar una reindexación.

---

### C7 — Corregir la dependencia arquitectónica del adaptador de evaluación

**Problema confirmado**

`rag.core.generator` importa `_extract_answer_from_state` desde `rag.api.main`. Esto hace que una herramienta offline de `core` cargue FastAPI, routers, autenticación y base de datos.

**Implementación requerida**

1. Mover la extracción de la última respuesta a una función pública y tipada en una ubicación de `core` que ya conozca el estado del agente; preferiblemente `rag.core.agent`.
2. Hacer que `api.main` y `core.generator` importen esa función desde `core`.
3. Eliminar la función privada duplicada de `api.main`.
4. Conservar exactamente el resultado actual para estados vacíos, mensajes no IA y último `AIMessage` válido.
5. No crear un nuevo módulo para una sola función si puede residir coherentemente en `agent.py`.

**Pruebas obligatorias**

- Estado vacío devuelve cadena vacía.
- Se devuelve el último `AIMessage` con contenido.
- Mensajes humanos posteriores no sustituyen la respuesta.
- Importar `rag.core.generator` no debe requerir importar `rag.api.main`.

**Estado de RAGAS**

No intentar resolver en esta entrega la incompatibilidad entre `ragas` y `langchain-community`, ni sustituir las preguntas de Poe por respuestas jurídicas inventadas. Actualizar el informe para que T4.2 figure como **parcial/pendiente**, no completa.

---

### C8 — Hacer precisa la observabilidad sin cambiar la API

**Problema confirmado**

`log_full_context_size` se presenta como tamaño real del prompt, pero el cálculo actual suma instrucciones, contexto y pregunta sin contar las etiquetas y recordatorios del template.

**Implementación requerida**

1. Calcular el tamaño sobre los mensajes ya formateados por el `ChatPromptTemplate`, o renombrar/documentar inequívocamente la métrica como aproximación.
2. Preferir el cálculo sobre mensajes formateados si puede hacerse sin cambiar la invocación del LLM.
3. No registrar texto del usuario, documentos, prompts, identificadores ni credenciales; solo conteos.
4. No cambiar `context_tokens`, `context_limit` ni ningún campo público.
5. No hacer una segunda llamada al LLM.

**Pruebas obligatorias**

- El conteo incluye etiquetas y recordatorio de citas.
- Funciona con proveedor con y sin rol system.
- El contenido sensible no aparece en logs.
- `context_tokens` conserva exactamente su comportamiento actual.

---

### C9 — Alinear readiness, configuración, documentación y CI

Esta entrega es de coherencia; no debe ampliar el comportamiento operativo de manera riesgosa.

**Readiness**

- Documentar que `/api/ready` comprueba:
  - grafo compilado;
  - snapshot BM25 inicializado/no vacío;
  - conexión actual a la base de datos.
- Declarar que no garantiza conectividad actual con Chroma u Ollama después del arranque.
- No añadir llamadas periódicas reales a Chroma/Ollama en este plan.
- No cambiar el JSON ni los códigos HTTP del endpoint.

**`.env.example`**

Añadir, con valores seguros y `off` predeterminado:

```dotenv
RAG_BACKPRESSURE_MODE=off
RAG_BACKPRESSURE_MAX_CONCURRENT=20
```

Documentar `RAG_ENV_FILE` sin incluir rutas reales. Revisar la sección del reranker, pero no inventar una URL ni habilitarlo implícitamente.

**`SCRIPTS.md`**

Corregir los ejemplos para que coincidan con la CLI real:

- `chroma_clear` debe mostrar `--collection <nombre>` y explicar que `--execute` es obligatorio para borrar.
- El resumen de `load_test.py` debe incluir `--url`.
- Mantener ejemplos HTTP.

**CI**

- Añadir `v2` a los triggers de `push` del workflow si esta sigue siendo la rama activa de integración.
- No duplicar workflows.
- No cambiar el conjunto de pruebas, lint o mypy para `ingesta/`.

**Informe final anterior**

Corregir o anotar:

- estado actual: 21 commits por delante de `origin/v2` antes de los nuevos commits, no 20;
- el commit adicional corresponde al propio informe;
- el conteo “16 entregas / 14 completas” no coincide con las etiquetas enumeradas;
- T4.2 está parcial por incompatibilidad de dependencias y dataset no pertinente.

---

### C10 — Retirar únicamente código/configuración muerta demostrable

Ejecutar esta entrega después de todas las anteriores y en un commit independiente.

**Candidatos confirmados localmente**

- `balance_by_doc_type()` solo tiene consumidores en pruebas.
- `QUERY_ENRICHMENT_HYDE` no tiene consumidores.
- `DEFAULT_K` y `DEFAULT_K_CANDIDATES` no controlan los defaults de la API ni tienen consumidores.

**Procedimiento obligatorio**

1. Confirmar nuevamente con búsqueda global que no existen consumidores de runtime, scripts mantenidos ni documentación operativa que dependa de cada símbolo.
2. Eliminar cada candidato y sus pruebas exclusivas solo si la ausencia está demostrada.
3. No conectar una variable muerta al flujo para “justificarla”: si no se usa, retirarla es más simple que crear comportamiento nuevo.
4. No retirar en esta entrega:
   - `OllamaReranker`;
   - `enrich_query()` síncrono, por posible compatibilidad externa;
   - adaptadores de embeddings;
   - funciones de indexación.
5. No tocar las reglas del clasificador al retirar constantes de configuración no usadas.

**Criterio de parada**

Si aparece un consumidor externo documentado o un contrato mantenido, conservar el símbolo y registrar la evidencia en el informe.

---

## 6. Trabajo expresamente diferido

No ejecutar dentro de este plan:

1. T3.3: acotamiento del historial SQL.
2. T3.4: cambio de autoridad o reemplazo de `MemorySaver`.
3. Cambio de definición de `context_tokens`.
4. Actualización de versiones RAGAS/LangChain.
5. Creación de ground truths jurídicas para evaluación.
6. Migración de `/api/embeddings` a `/api/embed` con lotes.
7. Reindexación de documentos.
8. Modificación de máquinas, contenedores o modelos en AWS Academy.
9. Pruebas de carga contra hosts remotos.
10. Cambio de HTTP a HTTPS.
11. Recalibración de prompts, clasificador, retrieval o citas.

El informe final debe conservar esta lista para que los pendientes no se interpreten como olvidos.

---

## 7. Verificación final obligatoria

Al terminar todas las entregas:

### 7.1 Calidad estática

```bash
cd rag
uv run ruff check backend/rag/ tests/ evaluation/
uv run ruff format --check backend/rag/ tests/ evaluation/
uv run mypy backend/rag/
```

### 7.2 Pruebas

```bash
uv run pytest tests/unit/ -p no:cacheprovider
uv run pytest tests/unit/ --cov=rag --cov-report=term-missing
```

La suite debe pasar:

- en la copia de desarrollo con `.env` presente;
- en una copia limpia sin `.env`;
- sin conexiones reales a Chroma, Ollama, AWS o proveedores LLM.

### 7.3 Regresiones funcionales protegidas

Verificar explícitamente:

- banco jurídico de 21 preguntas intacto y en verde;
- prompts sin cambios;
- topología LangGraph sin cambios;
- mismo formato de respuestas JSON y SSE;
- mismas fuentes, índices `[docN]` y agrupación;
- mismos límites `k` y `k_candidates`;
- mismos valores predeterminados de rate limit y backpressure;
- ningún acceso a infraestructura real;
- ninguna reindexación.

### 7.4 Git

```bash
git status --short --branch
git diff --check <commit-inicial>..HEAD
git log --oneline <commit-inicial>..HEAD
```

Confirmar que:

- solo se modificaron archivos autorizados;
- cada entrega tiene su commit independiente;
- no se hizo push;
- no se versionaron `.env`, `.venv`, caches, tokens, resultados temporales o credenciales.

---

## 8. Condiciones generales de parada

La IA implementadora debe detener la entrega afectada y solicitar decisión si ocurre cualquiera de estos casos:

- una corrección exige cambiar prompts o clasificación jurídica;
- cambia el banco de 21 preguntas o alguna deja de ser `in_scope`;
- cambia el contrato público de API/SSE;
- cambia el valor o significado de `context_tokens`;
- es necesario acceder a infraestructura real;
- es necesario reindexar;
- es necesario actualizar dependencias compartidas;
- una prueba solo puede pasar debilitando una expectativa funcional;
- el cambio requiere modificar la topología del grafo;
- se detectan cambios locales del usuario en archivos que este plan necesita tocar.

Detener una entrega no impide continuar con otras que sean independientes, siempre que el informe final deje clara la dependencia y el motivo.

---

## 9. Formato del informe que debe entregar la IA implementadora

El informe final debe incluir:

1. Rama, commit inicial y commit final.
2. Tabla C1–C10 con estado: completada, detenida o diferida.
3. Archivos modificados por entrega.
4. Prueba roja que reprodujo cada defecto y prueba verde posterior.
5. Resultado exacto de pytest, cobertura, Ruff, formato y mypy.
6. Confirmación de pruebas con y sin `.env`.
7. Confirmación específica de limpieza de locks/slots tras cancelación SSE.
8. Confirmación de que un batch exitoso se ejecuta una sola vez.
9. Confirmación de que prompts, clasificador, banco jurídico, retrieval y API no cambiaron.
10. Pendientes diferidos, especialmente T3.3/T3.4, RAGAS y modernización de embeddings.
11. Lista de commits creados.
12. Confirmación explícita: **no se hizo push**.

---

## 10. Definición de terminado

El plan solo se considera terminado cuando:

- C1–C9 están completas o detenidas con evidencia suficiente;
- C10 se ejecutó únicamente sobre símbolos demostrablemente muertos;
- todas las pruebas vigentes pasan con y sin `.env`;
- SSE tiene cobertura de éxito, error y cancelación;
- no quedan locks o slots retenidos después de las pruebas;
- configuración no depende del orden de imports;
- un batch exitoso no se repite;
- Ruff, formato y mypy están en verde;
- no se alteró ningún comportamiento jurídico aprobado;
- no hubo acceso a infraestructura, reindexación ni push.
