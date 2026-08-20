# Contexto y alcance para la revisión del proyecto

## Propósito de esta revisión

Realiza una revisión técnica detallada del estado actual del proyecto, trabajando sobre la
rama `v2` y considerando el contenido actual del directorio de trabajo, incluidos los cambios
locales que todavía no se hayan confirmado en Git.

El objetivo es encontrar problemas reales y corregibles relacionados con:

- coherencia y consistencia entre módulos;
- errores funcionales o flujos no controlados;
- seguridad de la aplicación;
- validación de entradas, autenticación y autorización;
- manejo de errores, concurrencia y persistencia;
- calidad de las respuestas del RAG;
- clasificación y enriquecimiento de consultas;
- uso de contexto, fuentes y citas;
- eficiencia del backend, API y frontend;
- modularidad, mantenibilidad y buenas prácticas;
- código duplicado, innecesario o sobreingenierizado;
- cobertura y calidad de las pruebas.

La revisión inicial es **solo diagnóstica**. No modifiques archivos, no hagas commits y no
hagas `push`, salvo que se solicite expresamente después de revisar los hallazgos.

## Contexto funcional

Este proyecto es un RAG jurídico en español especializado en Colombia. Debe responder
consultas relacionadas con:

- normatividad y jurisprudencia sobre playas y zonas costeras;
- uso, acceso y aprovechamiento de playas;
- derechos, competencias y obligaciones de ciudadanos, autoridades y operadores;
- pesca, turismo y actividades económicas vinculadas con playas;
- permisos, prohibiciones, procedimientos y autoridades competentes;
- preguntas sobre qué se puede o no se puede hacer y quién tiene determinado derecho.

No debe responder como si tuviera conocimiento respaldado sobre temas completamente ajenos a
ese dominio. Los saludos, agradecimientos y preguntas sobre la función del sistema sí pueden
recibir una respuesta breve, pero sin inventar información jurídica.

El sistema se encuentra desplegado en AWS y actualmente funciona. Usa FastAPI, LangGraph,
un frontend Next.js, ChromaDB remoto y servicios Ollama remotos. El índice contiene documentos
de tipo `normativa` y `jurisprudencia`.

## Restricciones obligatorias

Los siguientes puntos **no son problemas que deban resolverse en esta revisión**:

1. **El sistema debe continuar usando HTTP.** Actualmente no hay acceso a HTTPS. No reportes la
   ausencia de HTTPS como un hallazgo accionable ni propongas redirecciones obligatorias,
   certificados, cookies que requieran HTTPS o cambios que impidan operar por HTTP.
2. **No modificar las máquinas de Ollama ni ChromaDB.** Están en AWS Academy, dentro de un
   entorno de desarrollo, y por ahora no se tiene control operativo sobre ellas.
3. **No reindexar documentos.** La reindexación corresponde a otro integrante del equipo.
4. **No proponer cambios que necesiten reindexación para funcionar correctamente.** Se pueden
   identificar como trabajo futuro, pero no deben mezclarse con los hallazgos accionables ahora.
5. **No modificar el pipeline de ingesta, los documentos almacenados, embeddings, colecciones o
   datos de ChromaDB** dentro de esta revisión.
6. **No realizar cambios de infraestructura**, red, puertos, DNS, certificados, IAM, instancias,
   contenedores desplegados o configuración de AWS Academy.
7. **No ejecutar acciones destructivas o persistentes** contra los servicios desplegados. No
   borrar conversaciones, usuarios, documentos, colecciones ni índices.
8. **No exponer secretos ni incluir valores de archivos `.env`** en el diagnóstico.

Si detectas un riesgo que solo puede corregirse violando estas restricciones, no lo presentes
como una tarea inmediata. Como máximo, inclúyelo brevemente en una sección separada llamada
`Trabajo futuro bloqueado por restricciones`, indicando por qué no puede atenderse ahora.

## Áreas que sí se pueden revisar y mejorar

Concentra el análisis en cambios que podamos realizar dentro del repositorio y desplegar sin
modificar las máquinas externas ni regenerar el índice:

### RAG y consultas

- clasificación de consultas dentro y fuera del dominio;
- conservación de la pregunta original y del contexto conversacional;
- generación de una pregunta autónoma para conversaciones con referencias ambiguas;
- enriquecimiento de la consulta usada para recuperar documentos;
- separación entre la consulta de recuperación y la pregunta que se responde;
- selección, combinación y límite de resultados ya existentes en ChromaDB/BM25;
- prevención de respuestas sin respaldo documental;
- correspondencia entre citas como `[docN]` y las fuentes realmente recuperadas;
- comportamiento ante ausencia de resultados, timeouts o respuestas inválidas del LLM;
- prompts, instrucciones contradictorias y alcance temático;
- pruebas deterministas del flujo sin depender de reindexación.

### API y backend

- contratos y validaciones de FastAPI/Pydantic;
- autenticación, autorización y aislamiento de datos entre usuarios;
- propiedad de conversaciones y mensajes;
- idempotencia, reintentos y duplicación de mensajes;
- manejo seguro de errores sin filtrar detalles internos;
- estado de LangGraph y recuperación del historial después de reinicios;
- límites configurables y reversibles para consultas costosas;
- concurrencia, tareas asíncronas y recursos mantenidos en memoria;
- modularidad y eliminación de dependencias obsoletas o innecesarias;
- observabilidad que pueda implementarse en la aplicación sin servicios externos nuevos.

Evita proponer migraciones de base de datos o nuevos componentes de infraestructura como una
corrección inmediata. Si fueran imprescindibles, deben quedar como trabajo futuro y requerir
aprobación separada.

### Frontend

- consistencia con los contratos de la API;
- manejo de autenticación y expiración de sesión;
- abortar solicitudes, reintentos y prevención de duplicados;
- estados de carga, error y streaming;
- limpieza de estado entre usuarios y conversaciones;
- accesibilidad, validación y mensajes comprensibles;
- seguridad al renderizar Markdown o contenido generado;
- rendimiento y eliminación de lógica duplicada.

### Pruebas y calidad

- pruebas unitarias para decisiones críticas del RAG;
- pruebas de autorización y aislamiento entre usuarios;
- pruebas de compatibilidad de recuperación y citas;
- análisis estático de Python y TypeScript;
- pruebas de humo opcionales y no persistentes contra el despliegue;
- casos límite y regresiones probables.

No ejecutes pruebas contra AWS si faltan URL o credenciales explícitas. Las pruebas en vivo no
deben crear conversaciones persistentes, modificar ChromaDB ni provocar cargas masivas sobre
los modelos.

## Estado relevante que debe preservarse

La implementación actual ya incluye o está incorporando las siguientes protecciones. Revisa su
correctitud y coherencia antes de sugerir reemplazarlas:

- control del alcance temático de las consultas;
- separación entre pregunta original, pregunta autónoma y consulta enriquecida;
- validación de respuestas y citas contra las fuentes recuperadas;
- aislamiento del estado conversacional por usuario;
- validación de propiedad de conversaciones y mensajes;
- persistencia idempotente desde el frontend;
- manejo de cancelación y reintentos en el chat;
- limitador local de consultas con modos `off`, `observe` y `enforce`, desactivado por defecto;
- adaptador BM25 interno compatible con el ranking anterior;
- pruebas de humo opcionales en `tests/integration/test_api_smoke.py`.

No asumas que estas medidas son correctas solo porque existen: compruébalas mediante el código y
las pruebas. Sin embargo, no propongas una reescritura si una corrección pequeña y modular es
suficiente.

## Criterios para aceptar una propuesta

Una recomendación inmediata debe cumplir todos estos criterios:

- puede implementarse únicamente mediante cambios en este repositorio;
- no requiere HTTPS;
- no modifica las máquinas de Ollama o ChromaDB;
- no requiere reindexar documentos;
- no cambia infraestructura o datos externos;
- conserva compatibilidad con los contratos actuales o documenta una migración segura;
- incluye una forma concreta de verificar que no rompe lo que ya funciona;
- tiene un beneficio claro y proporcional a su complejidad.

Prefiere cambios pequeños, reversibles, configurables y cubiertos por pruebas. Evita incorporar
dependencias o abstracciones nuevas si el mismo resultado puede lograrse claramente con los
componentes existentes.

## Formato esperado del diagnóstico

Presenta primero los hallazgos accionables, ordenados por severidad:

- `P0`: pérdida de datos, acceso no autorizado o indisponibilidad general inmediata;
- `P1`: error funcional o de seguridad importante con alta probabilidad o impacto;
- `P2`: problema real de consistencia, eficiencia o mantenibilidad con impacto moderado;
- `P3`: mejora menor y concreta.

Para cada hallazgo incluye:

1. prioridad y título;
2. archivo y líneas exactas;
3. evidencia observable en el código;
4. escenario concreto en el que falla;
5. impacto funcional;
6. corrección mínima recomendada;
7. pruebas necesarias para prevenir regresiones;
8. confirmación de que respeta todas las restricciones anteriores.

No incluyas observaciones puramente estéticas, recomendaciones genéricas ni hipótesis sin
evidencia. Si no encuentras hallazgos en una categoría, indícalo en una sola frase. Termina con:

- una lista corta de riesgos residuales realmente accionables;
- el orden recomendado de implementación;
- las validaciones que deberían ejecutarse antes del despliegue;
- una sección separada y breve para trabajo futuro bloqueado por las restricciones.

## Validación local de referencia

Antes de concluir, cuando el entorno lo permita, ejecuta como mínimo:

```bash
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
```

En el frontend:

```bash
cd frontend
npx tsc --noEmit
npx eslint .
npm run build
```

Si algún comando no puede ejecutarse por una limitación del entorno, distingue claramente entre
un error del proyecto y un bloqueo ambiental. No cambies código solo para ocultar un problema
del entorno de revisión.
