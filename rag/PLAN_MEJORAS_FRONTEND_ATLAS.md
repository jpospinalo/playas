# Plan de mejoras — Interfaz y mecanismos de calificación de ATLAS

Fecha: 2026-08-26 (revisado el mismo día: hallazgos contrastados contra el
código fuente del frontend)
Origen: hallazgos de la sesión de pruebas manuales y automatizadas (Claude in
Chrome) sobre el despliegue de producción
(`http://rag-playas-prod-alb-750843360.us-east-1.elb.amazonaws.com/`), rama
`v2`.

## 1. Alcance y principio guía

Este plan cubre únicamente el **frontend** de ATLAS: la aplicación web y sus
formularios de calificación. No incluye cambios al clasificador de alcance
(`query_enricher.py`), a retrieval, a prompts de generación, a datos, a
infraestructura ni a la lógica de citas/fuentes — nada de eso mostró defectos
en las pruebas y no debe tocarse aquí.

Principio para toda la ejecución de este plan: **cada cambio debe ser
mínimo, localizado y verificable de forma aislada**, sin modificar
componentes que ya se probaron y funcionan correctamente (búsqueda de
conversaciones, apariencia claro/oscuro, citas numeradas con popover, panel
de fuentes consultadas, colapso de sidebar en escritorio, landing "Cómo
funciona"). Antes de cada cambio se debe confirmar el comportamiento actual
con una prueba manual o automatizada, y después del cambio repetir esa misma
prueba más una pasada rápida de regresión sobre los flujos ya validados.

Por indicación explícita, **se excluye de este plan** cualquier mecanismo
para marcar fuentes o citas incorrectas: los usuarios de prueba solo
consultarán sobre normativa que el sistema ya contiene, así que esa señal no
es prioritaria por ahora.

## 2. Verificación contra el código (2026-08-26)

La primera versión de este plan se basó solo en pruebas de caja negra desde
el navegador. Esta revisión contrasta cada hallazgo contra el código fuente
real del frontend (`rag/frontend/`, rama `v2`: `components/chat/*.tsx`,
`hooks/useConversations.ts`, `hooks/useChat.ts`, `lib/api.ts`, `lib/types.ts`,
`app/admin/feedback/page.tsx`). Resultado por hallazgo:

- **Confirmados exactamente como se diagnosticaron**: #1 (renombrar) y #4
  (escala de "Longitud"). Ver el detalle de archivo/línea en 4.1 y 4.2.
- **Descartado — no se requiere cambio**: #6 (envío con 0 estrellas). El
  código ya valida esto en ambos formularios. Ver 4.5.
- **Diagnóstico probablemente incorrecto — requiere reprobar antes de
  tocar código**: #3 (sidebar y resize). El código ya maneja esto de forma
  reactiva por CSS. Ver 4.6.
- **Sin causa encontrada en el código — posible artefacto de la prueba
  automatizada**: #2 (`Ctrl+A`). Ver 4.3.
- **Más débil de lo planteado originalmente**: #5 (redundancia entre
  formularios). Los dos formularios no comparten ninguna dimensión de
  calificación en el código. Ver 4.4.

Esto reemplaza la incertidumbre de la versión anterior de este documento,
pero las siguientes precauciones generales se mantienen igual de válidas:

- Implementar sobre la rama `v2` (donde se sigue el desarrollo de nuevas
  funcionalidades según lo acordado), no sobre `scripts` (reservada para
  pruebas/verificaciones) ni sobre `main` (versión estable).
- Si existe un entorno de staging o de desarrollo separado del ALB de
  producción usado en las pruebas, desplegar y verificar ahí primero. Si no
  existe, al menos confirmar con el equipo qué usuarios podrían verse
  afectados por un despliegue directo a producción.
- Tener claro cómo revertir cada cambio (commit individual y acotado por
  punto de este plan) en caso de que la verificación posterior encuentre una
  regresión.
- La revisión de código no reemplaza la prueba en vivo: cada punto de la
  sección 4 conserva su "Verificación posterior" y debe repetirse tal cual
  después de implementar el cambio.

## 3. Resumen de hallazgos que originan este plan

| # | Hallazgo | Cómo se detectó | Verificado en código |
|---|----------|------------------|------------------------|
| 1 | Al renombrar una conversación, el cambio se guarda correctamente en el backend, pero el sidebar sigue mostrando el título anterior hasta recargar la página. | Renombrado en vivo + verificación de persistencia recargando la página, reproducido dos veces. | ✅ Confirmado — ver 4.1 |
| 2 | `Ctrl+A` no selecciona el texto dentro del campo de edición inline de "Renombrar"; el atajo estándar de "seleccionar todo y reescribir" no funciona. | Reproducido de forma aislada comparando `Ctrl+A` vs. triple clic. | ❓ Sin causa encontrada — ver 4.3 |
| 3 | El sidebar solo calcula si debe colapsarse (modo móvil) en la carga inicial de la página; si el usuario redimensiona la ventana o rota la pantalla sin recargar, el sidebar se queda expandido tapando la conversación. | Pruebas de responsive en 390px (móvil) y 768px (tablet), con y sin recarga. | ⚠️ Diagnóstico probablemente incorrecto — ver 4.6 |
| 4 | La dimensión "Longitud de las respuestas" en el formulario "Calificar la conversación" usa la misma escala 1=Muy malo → 5=Excelente que el resto de dimensiones, pero longitud es una característica bipolar (muy corta / muy larga), no una escala de calidad. Un 1 estrella no dice si el problema es que sobra o falta texto. | Prueba en vivo del formulario, verificando las etiquetas de texto que aparecen al calificar cada estrella. | ✅ Confirmado — ver 4.2 |
| 5 | No se pudo confirmar si "Calificar esta respuesta" y "Calificar la conversación" (con su "Calificación general") capturan información redundante o complementaria — no hay diferenciación clara en la copia de ninguno de los dos formularios. | Revisión funcional de ambos formularios. | ➖ Más débil de lo planteado — ver 4.4 |
| 6 | No se verificó si los formularios de calificación permiten enviarse con 0 estrellas seleccionadas (posible dato vacío/basura en las métricas). | Pendiente de verificar deliberadamente (no se probó para no contaminar datos reales). | ❌ Descartado, ya implementado — ver 4.5 |
| 7 | Los disparadores de calificación (íconos de estrella) son pequeños, sin etiqueta visible, y de uso enteramente opcional — fácil que un usuario de prueba nunca los note. | Observación directa durante las pruebas de interfaz. | — No revisado en código (es una decisión de producto, no un bug) |

## 4. Lista de cambios propuestos, priorizados

### Prioridad alta

**4.1 — Refrescar el título de la conversación en el sidebar tras renombrar
(hallazgo #1) — CONFIRMADO EN CÓDIGO**
Causa raíz exacta: `ConversationList.tsx` llama
`await onConversationsRefresh?.()` (encadenamiento opcional) al terminar
`saveEdit()`/`confirmDelete()`, pero `onConversationsRefresh` está declarado
opcional en `ConversationListProps` y **`ChatInterface.tsx` nunca lo pasa**
al renderizar `<ConversationSidebar>`, aunque la función `refreshConversations`
(de `useConversations()`) ya está disponible ahí mismo. Como la prop falta,
`?.()` se convierte en un no-op silencioso: el PATCH al backend sí se
guarda, pero nada dispara un refetch del listado.
Cambio: pasar `onConversationsRefresh={refreshConversations}` desde
`ChatInterface.tsx` a `<ConversationSidebar>`, y encadenar esa misma prop
hacia abajo (`ConversationSidebar` → `DesktopSidebar`/`MobileSidebar` →
`ExpandedSidebarContent` → `ConversationList`) hasta que llegue al
componente que ya la usa.
Riesgo: bajo. Es enchufar una prop ya definida en el tipo; no se toca la
lógica de guardado ni el backend. Único cuidado: verificar que la prop se
pase en **todas** las rutas de render de `ConversationList` (escritorio y
móvil), no solo en una.
Verificación posterior: renombrar una conversación y confirmar que el
sidebar se actualiza sin recargar, luego confirmar que persiste tras
recargar (repetir la prueba que ya se hizo).

**4.2 — Corregir la escala de "Longitud de las respuestas" (hallazgo #4) —
CONFIRMADO EN CÓDIGO**
Causa raíz exacta: en `FeedbackModal.tsx`, las 4 dimensiones (`tone`,
`length`, `usability`, `overall`) comparten un único mapa
`RATING_LABELS = {1: "Muy malo", 2: "Malo", 3: "Regular", 4: "Bueno",
5: "Excelente"}`. No hay ninguna rama especial para `length`: recibe
literalmente las mismas etiquetas de calidad que "Tono" o "Usabilidad".
Además, `app/admin/feedback/page.tsx` (dashboard de administración) muestra
"Longitud" con el mismo componente genérico de 5 estrellas (`Stars`) y un
promedio numérico plano (`avgRatings.length.toFixed(1)`), sin ninguna
distinción semántica frente a las demás columnas — confirma que hoy un
promedio de, por ejemplo, "3.0" en Longitud es tan ambiguo como se
sospechaba (no dice si las respuestas fueron cortas o largas).
Cambio: reemplazar la escala malo↔excelente por una escala bipolar con
etiquetas explícitas, por ejemplo "Muy corta" / "Corta" / "Adecuada" /
"Larga" / "Muy larga", de forma que el resultado sea directamente accionable
(saber si hay que acortar o alargar respuestas).
Riesgo: bajo en el frontend **si el cambio se limita a las etiquetas de
texto** (relabeling del mismo eje 1-5 numérico) — no requiere tocar
`ConversationRatings` en `lib/types.ts` (sigue siendo `length: number`) ni
el dashboard de admin, que solo muestra el promedio numérico y no las
etiquetas. El riesgo sube a medio si en vez de esto se decide capturar
"muy corta" y "muy larga" como dos señales separadas (no un solo eje
lineal), porque eso sí exigiría cambiar el tipo, el payload, el backend y
el dashboard de admin — evaluar cuál de las dos versiones se quiere antes
de implementar. Independientemente de la opción elegida, confirmar primero
si ya existen calificaciones reales guardadas con la escala actual: si las
hay, los datos de "Longitud" antes y después del cambio no serán
comparables entre sí, y conviene dejarlo documentado (por ejemplo, con la
fecha del cambio) para quien analice esas métricas en
`app/admin/feedback/page.tsx`.
Verificación posterior: repetir la prueba de calificación en vivo y
confirmar que las etiquetas mostradas coinciden con la nueva escala, y que
el promedio en el dashboard de admin se sigue calculando sin errores.

### Prioridad media

**4.3 — Corregir la selección de texto con `Ctrl+A` en "Renombrar"
(hallazgo #2) — SIN CAUSA CONFIRMADA EN CÓDIGO, REPROBAR ANTES DE
IMPLEMENTAR**
El campo de edición inline en `ConversationList.tsx` es un `<input>` nativo
de React sin ningún manejador de teclado propio más allá de `onKeyDown`
para Enter (guardar) y Escape (cancelar) — no hay `preventDefault`, ni
`stopPropagation`, ni ninguna lógica que intercepte o bloquee `Ctrl+A`. Un
input nativo sin esas interceptions debería seleccionar todo el texto con
`Ctrl+A` por comportamiento estándar del navegador. Esto no descarta que el
problema sea real (podría venir de un listener global en otro componente,
o de un conflicto de foco), pero tampoco se encontró en el código nada que
lo explique, lo que abre la posibilidad de que haya sido un artefacto de
la prueba automatizada con Claude in Chrome (los eventos de teclado
sintéticos de una extensión no siempre disparan la selección nativa del
navegador igual que un teclado físico).
Antes de invertir tiempo de ingeniería aquí: repetir la prueba con
interacción humana real (teclado físico, sin automatización) en al menos
dos navegadores. Si el problema persiste con interacción humana, entonces
sí vale la pena investigar el código con más profundidad (por ejemplo
revisar si hay un `onKeyDown` global en un componente padre que capture el
evento antes de que llegue al input). Si no se reproduce, se puede retirar
este punto del plan.
Riesgo (si se confirma y se implementa): bajo. Cambio acotado al manejo de
teclado de un único campo de texto.
Verificación posterior: abrir "Renombrar", presionar `Ctrl+A`, escribir un
texto nuevo y confirmar que reemplaza limpiamente el título anterior (sin
mezclarse), tanto guardando como cancelando con Escape.

**4.4 — Aclarar la diferencia entre "Calificar esta respuesta" y "Calificar
la conversación" (hallazgo #5) — MÁS DÉBIL DE LO PLANTEADO ORIGINALMENTE**
El código muestra que **no hay redundancia real**: `MessageRatingPopover.tsx`
("Calificar esta respuesta") solo pide `pertinence` y `accuracy`, con
tooltips propios bien explicados por dimensión (p. ej. "¿Qué tan relevante
fue la respuesta para tu pregunta?"). `FeedbackModal.tsx` ("Calificar la
conversación") pide `tone`, `length`, `usability` y `overall`. No hay
ninguna dimensión compartida entre los dos formularios. El único problema
real que queda es que esto no es evidente para el usuario a simple vista,
ya que ninguno de los dos títulos ("esta respuesta" vs. "la conversación")
dejan del todo claro qué aspectos puntuales cubre cada uno.
Cambio (bajado de alcance): en vez de evaluar fusionar o eliminar un
formulario, basta con un ajuste menor de copia — por ejemplo, agregar una
línea corta en cada modal aclarando qué mide ("aspectos de esta respuesta
puntual" vs. "tu experiencia general con la conversación").
Riesgo: bajo. Es solo copy, no toca la lógica de envío ni los datos ya
almacenados de ninguno de los dos formularios.

**4.5 — Mínimo de estrellas antes de enviar (hallazgo #6) — DESCARTADO,
YA IMPLEMENTADO**
Verificado en código: **esta validación ya existe** en ambos formularios.
`FeedbackModal.tsx` calcula `const allRated = Object.values(selected).every(
(v) => v > 0)` y usa `disabled={!allRated || submitState === "loading"}`
en el botón de envío. `MessageRatingPopover.tsx` tiene el mismo patrón
`allRated`/`disabled` para sus dos dimensiones. No es posible enviar
ninguno de los dos formularios con 0 estrellas en alguna dimensión
requerida. No se requiere ningún cambio — se retira este punto de la lista
de trabajo.

**4.6 — Sidebar y redimensionar la ventana (hallazgo #3) — DIAGNÓSTICO
PROBABLEMENTE INCORRECTO, REPROBAR ANTES DE PRIORIZAR**
El código contradice el diagnóstico original de "solo calcula el colapso en
la carga inicial". Lo que hay en `ConversationSidebar.tsx` es:
`DesktopSidebar` (`hidden ... md:flex`) y `MobileSidebar` (`fixed ...
md:hidden`) están controlados por clases de breakpoint de Tailwind
(`md:` = 768px), que son CSS puro y por lo tanto **ya reaccionan solas** a
un resize o rotación de pantalla, sin necesidad de JavaScript ni de
recargar. Además, ya existe un fondo de cierre exclusivo para móvil:
```
{isExpanded && (
  <div className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
       onClick={handleToggleSidebar} aria-hidden="true" />
)}
```
que permite cerrar el sidebar tocando fuera de él en pantallas móviles. El
único estado en React (`sidebarOpen`, vía `localStorage`) controla si el
usuario prefiere el sidebar expandido o colapsado *dentro* del layout de
escritorio — no si se está en modo móvil o no, eso lo decide el CSS en
cada render.
Antes de tocar código: repetir la prueba de responsive, pero esta vez
probando deliberadamente (a) redimensionar la ventana entre escritorio y
móvil sin recargar, y (b) si el sidebar queda visible tapando la
conversación en móvil, tocar fuera de él (el fondo `bg-foreground/20`) para
confirmar si ya se cierra con eso. Es posible que el hallazgo original haya
sido no descubrir ese gesto de cierre, más que un defecto de la aplicación.
Si tras esa reprueba el problema persiste de forma reproducible, sí
amerita revisar con más detalle por qué el CSS responsive no se está
aplicando como se espera.
Riesgo (si se confirma y se implementa algún cambio): bajo-medio, con el
cuidado habitual de no romper el colapso/expansión manual de escritorio ni
el fondo de cierre móvil ya existente.

### Prioridad baja

**4.7 — Mejorar la visibilidad/invitación a calificar (hallazgo #7)**
Cambio: evaluar una invitación más visible a calificar (por ejemplo, al
terminar de leer una respuesta o al cambiar de conversación), sin volverla
intrusiva ni obligatoria. Esto es una decisión de producto más que una
corrección, así que conviene definir primero qué tasa de respuesta se
espera de los usuarios de prueba antes de invertir en esto.
Riesgo: bajo si se implementa como una sugerencia sutil (por ejemplo, un
resaltado breve del ícono existente); medio si se implementa como un modal
o notificación que interrumpe al usuario.

## 5. Explícitamente fuera de alcance de este plan

- Cualquier mecanismo para marcar fuentes, citas o normativa incorrecta en
  las respuestas (excluido por indicación del equipo: los usuarios de
  prueba solo consultarán normativa que el sistema ya contiene).
- El botón "Eliminar" conversación (no se probó por ser una acción
  destructiva e irreversible; no se detectó ningún defecto asociado).
- Todo lo relacionado con el clasificador de alcance, retrieval, prompts,
  infraestructura, datos o dependencias — nada de esto se tocó ni mostró
  defectos en esta ronda de pruebas.

## 6. Orden de ejecución sugerido

1. 4.1 y 4.2 (prioridad alta, confirmadas en código, mayor impacto en la
   calidad de los datos de prueba que se van a recolectar).
2. 4.6 — **reprobar primero** (resize + fondo de cierre móvil) antes de
   decidir si hace falta implementar algo; es posible que se pueda retirar
   del plan igual que 4.5.
3. 4.3 — **reprobar primero** con interacción humana real, sin
   automatización, antes de invertir tiempo de ingeniería; puede terminar
   retirado del plan si no se reproduce.
4. 4.4 (ajuste menor de copia, bajo riesgo, no requiere decisión de
   producto compleja ya que se confirmó que no hay redundancia real).
5. 4.7 (prioridad baja, se puede agendar para después de que el piloto con
   usuarios de prueba esté en marcha).

(4.5 se retira de este orden: ya está implementado, no requiere trabajo.)

Después de cada cambio: `pytest`/lint/build del frontend según corresponda,
más una repetición de las pruebas manuales relevantes descritas en este
documento, antes de continuar con el siguiente punto de la lista.
