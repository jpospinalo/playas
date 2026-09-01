/**
 * Límite de tiempo conservador para operaciones REST finitas. Su único
 * trabajo es combinar, cuando existe, una señal de cancelación externa con
 * un timeout, y no dejar ningún recurso propio colgando — no es un cliente
 * HTTP general ni el lugar para mover autenticación, parseo o lógica de
 * negocio.
 *
 * Usa las APIs nativas `AbortSignal.timeout()` / `AbortSignal.any()`
 * (verificadas disponibles tanto en el runtime de pruebas — Vitest sobre
 * Node — como en la matriz de navegadores del proyecto, que no declara
 * soporte para navegadores antiguos vía `browserslist`) en vez de un
 * `AbortController` manual con temporizador y listeners propios: no hay
 * nada que limpiar explícitamente, la propia plataforma libera esos
 * recursos cuando la señal combinada deja de ser referenciada.
 *
 * Deliberadamente NO se usa en:
 *  - `queryRagStream` (`/api/query/stream`): conserva únicamente la señal
 *    de cancelación que ya recibe hoy; el streaming no tiene un contrato de
 *    duración finita razonable para un límite común.
 *  - `generateConversationTitle` (`/api/conversations/generate-title`):
 *    llamada al LLM con su propio fallback silencioso y un presupuesto de
 *    tiempo distinto al de este límite REST común; la UI actual no la
 *    invoca desde ningún flujo.
 */

/**
 * 60s: límite conservador para las operaciones REST normales del producto
 * (autenticación, listar/cargar/crear/renombrar/borrar conversaciones,
 * persistencia de mensajes, feedback, pantallas de administración).
 * Ninguna de ellas tiene hoy un contrato legítimo que se acerque a este
 * límite — lo que antes podía quedar esperando indefinidamente ahora falla
 * de forma explícita en vez de nunca resolver.
 */
export const REST_TIMEOUT_MS = 60_000;

/**
 * Retorna una señal que se aborta cuando transcurren `REST_TIMEOUT_MS`, o
 * cuando `signal` (si se pasa) se aborta — lo que ocurra primero. No
 * reemplaza `signal`: si el llamador ya cancela la operación por su cuenta
 * (p. ej. una selección posterior de conversación), esa cancelación sigue
 * funcionando exactamente igual que antes.
 */
export function withRestTimeout(signal?: AbortSignal): AbortSignal {
	const timeoutSignal = AbortSignal.timeout(REST_TIMEOUT_MS);
	return signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
}

/**
 * `true` si `error` es exactamente el timeout que produce
 * `withRestTimeout` — y no una cancelación deliberada por otra señal, ni
 * cualquier otro error. Se basa en el `DOMException("TimeoutError")` que
 * `AbortSignal.timeout()` usa como razón de aborto, no en heurísticas de
 * mensaje.
 */
export function isRestTimeoutError(error: unknown): boolean {
	return error instanceof DOMException && error.name === "TimeoutError";
}

/**
 * Mensaje controlado en español para un `error` de una operación REST
 * finita, pensado para los límites de presentación (formularios, listas,
 * pantallas de administración). Un timeout local (el que produce
 * `withRestTimeout`) se traduce SIEMPRE al mismo mensaje breve, en vez de
 * propagar el texto del `DOMException` nativo (en inglés, pensado para
 * consola, no para mostrarse a un usuario). Cualquier otro error conserva
 * su propio mensaje (p. ej. el que ya arma `readErrorDetail`, o el de un
 * `Error` local) — o `fallback` si no es una instancia de `Error`.
 *
 * No decide nada sobre una cancelación deliberada (`AbortError`, distinta
 * de un timeout): cada flujo cancelable sigue comprobando eso por su
 * cuenta ANTES de llamar a esta función y retornando en silencio si
 * aplica, exactamente como ya hacía.
 */
export function restErrorMessage(error: unknown, fallback: string): string {
	if (isRestTimeoutError(error)) {
		return "La solicitud tardó demasiado. Intenta nuevamente.";
	}
	return error instanceof Error ? error.message : fallback;
}
