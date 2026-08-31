/**
 * A7 — límites del contrato HTTP que el frontend debe reflejar (validación
 * visible/temprana) y revalidar (defensa en profundidad en `useChat.submit`),
 * no solo confiar en que el backend los rechace tarde, ya con la pregunta
 * agregada al historial local.
 *
 * Mantener en sincronía con el backend:
 * `rag/backend/rag/api/schemas.py::QueryRequest.question` (`max_length=4000`).
 */
export const MAX_QUESTION_CHARS = 4000;

/**
 * A partir de cuántos caracteres se muestra el contador de longitud en el
 * campo de consulta. No es un límite — solo el umbral de visibilidad del
 * aviso, para no mostrar un contador irrelevante en preguntas cortas.
 */
export const QUESTION_COUNTER_THRESHOLD = 3600;
