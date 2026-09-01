# Pruebas de humo de la API

Estas pruebas validan el despliegue real sin crear conversaciones, modificar
Chroma ni reindexar documentos. Usan consultas independientes contra
`/api/query` y lecturas de `/api/health`.

Variables requeridas:

```bash
export RAG_SMOKE_API_URL="http://direccion-del-api"
export RAG_SMOKE_TOKEN="token-de-un-usuario-de-pruebas"
```

Ejecución:

```bash
uv run pytest tests/integration/test_api_smoke.py -m integration
```

El conjunto verifica rechazo de preguntas ajenas, aceptación de pesca y
turismo relacionados con playas, recuperación de fuentes y citas válidas.

## Guion manual del frontend

Guion breve y reutilizable para validar manualmente, en un entorno real
(staging o producción), los flujos que las pruebas automatizadas del
frontend (`rag/frontend/lib/__tests__/`, `rag/frontend/hooks/__tests__/`)
ya cubren con mocks, pero que solo un navegador real puede confirmar de
punta a punta. No incluye credenciales: usa una cuenta de pruebas ya
existente en el entorno donde se ejecute.

Antes de empezar, identifica el entorno (`http://...`) y ten a mano las
credenciales de una cuenta de pruebas (nunca las escribas en este
documento ni en un reporte).

1. **Login correcto e incorrecto.** Intenta iniciar sesión con una
   contraseña incorrecta: debe rechazarse con un mensaje visible, sin
   iniciar sesión. Luego inicia sesión con las credenciales correctas de la
   cuenta de pruebas: debe entrar al chat.
2. **Crear una conversación.** Envía una primera pregunta legal legítima,
   en lenguaje natural (p. ej. sobre uso de playas) — el título de la
   conversación se toma literalmente de los primeros 120 caracteres de esta
   pregunta, así que una etiqueta técnica aquí contaminaría el título.
   Inmediatamente después de que se cree, renómbrala desde la UI para
   anteponerle el prefijo `SMOKE-` (p. ej. `SMOKE- <pregunta original>`)
   antes de continuar con el resto del guion — así queda identificable para
   borrarla al final sin afectar el título con el que se creó.
3. **Consulta legal legítima.** Mientras se procesa, el indicador de etapa
   (`Entendiendo tu pregunta…` / `Buscando evidencia…` / `Construyendo una
   respuesta…`) sí se actualiza en vivo. La respuesta en sí, en cambio, NO
   se genera token a token desde el LLM: el backend espera el resultado
   completo, lo valida (citas, fuentes) y solo entonces lo entrega en
   fragmentos de hasta 120 caracteres. Lo que hay que confirmar es que el
   indicador de etapa avanza durante la espera y que la respuesta aparece
   completa y validada al terminar — no que haya un efecto de escritura en
   vivo proveniente del modelo.
4. **Verificar respuesta y fuentes.** Al terminar, la respuesta debe
   incluir citas `[docN]` y una sección de fuentes agrupadas y
   expandibles, coherentes con el contenido de la respuesta.
5. **Recargar y recuperar la conversación.** Recarga la página (F5). La
   sesión debe seguir activa y la conversación recién creada debe
   reaparecer en el historial, con el título `SMOKE-...` y sus mensajes
   intactos al seleccionarla.
6. **Enviar un segundo turno.** En la misma conversación, envía una
   pregunta de seguimiento que dependa del contexto anterior (p. ej. "¿y
   si es una playa privada?"). La respuesta debe reflejar ese contexto.
7. **Detener una generación.** Envía una nueva pregunta y, mientras
   genera, pulsa "Detener". El streaming debe cortarse de inmediato, sin
   mostrar la respuesta parcial como si fuera la final, con un aviso breve
   de "Generación detenida".
8. **Cambiar de conversación durante una generación.** Envía una pregunta,
   y ANTES de que termine, selecciona otra conversación del historial (o
   crea una nueva). La generación en curso debe cancelarse sin mostrar
   ningún error ni el aviso de "Generación detenida" (ese aviso es
   exclusivo del botón "Detener"), y la conversación recién seleccionada
   debe cargar con normalidad.
9. **Guardado de una respuesta no persistida (cubierto por prueba
   automatizada).** El reintento manual tras un fallo de guardado
   (`POST .../messages` para la respuesta del asistente) ya está cubierto
   por pruebas automatizadas (`hooks/__tests__/useChat.persistence.test.ts`)
   que simulan el fallo de forma determinista; no se incluye aquí como paso
   obligatorio porque forzarlo a mano requiere interceptar en el instante
   exacto entre el fin de la generación y su guardado, algo que no es
   reproducible de forma confiable por una persona. **Opcional/avanzado:**
   si el entorno donde se ejecuta este guion cuenta con una forma de
   inyectar fallos controlada (p. ej. una regla de proxy) capaz de rechazar
   específicamente el `POST .../messages` cuyo cuerpo tiene
   `role: "assistant"` sin afectar el resto del tráfico, puede usarse para
   confirmar visualmente que la respuesta permanece en pantalla con un
   aviso de que no se guardó y un botón de reintentar, y que el aviso
   desaparece al reintentar con la red restaurada. No introducir
   herramientas, proxies ni código de producción solo para este paso.
10. **Logout y verificación.** Cierra sesión. Debe volver a la pantalla de
    login. Verifica que no quede ninguna acción autenticada activa:
    recargar la página no debe restaurar la sesión ni el chat, y no debe
    ser posible navegar de vuelta al chat sin iniciar sesión de nuevo.

Al terminar, borra desde la propia UI cualquier conversación con prefijo
`SMOKE-` que hayas creado (llama a `DELETE /api/conversations/{id}` a
través del botón "Eliminar" — nunca manipules la base de datos
directamente). No se modifican datos reales de usuarios ni documentos
indexados en ningún paso de este guion.
