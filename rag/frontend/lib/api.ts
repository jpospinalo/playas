import { API_URL } from "@/lib/config";
import { expireAuthSession, getToken, SESSION_EXPIRED_MESSAGE } from "@/lib/auth";
import { parseStreamEvent, SSE_DONE, SseEventAccumulator } from "@/lib/sseParser";
import { withRestTimeout } from "@/lib/httpTimeout";
import type {
	FeedbackRequest,
	MessageFeedbackRequest,
	QueryRequest,
	StreamEvent,
} from "@/lib/types";

function authHeaders(token: string | null): Record<string, string> {
	return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Comprueba si `response` es un 401 y, de serlo, invalida la sesión asociada
 * a `requestToken` (solo si ese token sigue coincidiendo con el activo — ver
 * `expireAuthSession`; `requestToken` puede ser `null` si la solicitud ya se
 * hizo sin token) y lanza un error legible para el usuario.
 *
 * Para cualquier otro estado no hace nada: un 403 (sin permiso), 404, 409,
 * 422, 429 o 5xx no significa que el token dejó de ser válido, así que no
 * debe cerrar la sesión. No debe usarse con el 401 de `/api/auth/login`,
 * donde un 401 significa credenciales incorrectas, no sesión expirada.
 */
export async function throwIfSessionExpired(
	response: Response,
	requestToken: string | null,
): Promise<void> {
	if (response.status !== 401) return;
	expireAuthSession(requestToken);
	throw new Error(SESSION_EXPIRED_MESSAGE);
}

/**
 * Llama al backend para generar un título con IA y actualizarlo en la BD.
 * Retorna el título generado, o un fragmento del mensaje si falla.
 *
 * Un 401 aquí también expira la sesión (mismo mecanismo que el resto de
 * llamadas autenticadas), pero el fallback silencioso a los primeros 50
 * caracteres del mensaje se conserva: esta función nunca debe bloquear el
 * envío de un mensaje por un problema al generar el título.
 */
export async function generateConversationTitle(
	firstMessage: string,
	conversationId: string,
): Promise<string> {
	const token = getToken();
	try {
		const res = await fetch(`${API_URL}/api/conversations/generate-title`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				...authHeaders(token),
			},
			body: JSON.stringify({
				first_message: firstMessage,
				conversation_id: conversationId,
			}),
		});
		await throwIfSessionExpired(res, token);
		if (!res.ok) return firstMessage.slice(0, 50);
		const data = (await res.json()) as { title?: string };
		return data.title ?? firstMessage.slice(0, 50);
	} catch {
		return firstMessage.slice(0, 50);
	}
}

/** Longitud máxima de un detalle de error mostrado al usuario. Un cuerpo
 * más largo se recorta — nunca se muestra tal cual — para no exponer
 * volcados internos ni desbordar la UI. */
const MAX_ERROR_DETAIL_LENGTH = 500;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

/**
 * `true` si el cuerpo no debe mostrarse como texto plano: un content-type
 * que no sea `text/plain`/`application/json` (p. ej. `text/html` de un
 * proxy o balanceador, o algo binario), o un cuerpo que empieza como HTML
 * aunque el content-type mienta.
 */
function looksLikeUntrustedBody(
	trimmedText: string,
	contentType: string | null,
): boolean {
	if (contentType && !/^(text\/plain|application\/json)\b/i.test(contentType)) {
		return true;
	}
	const start = trimmedText.slice(0, 15).toLowerCase();
	return start.startsWith("<!doctype") || start.startsWith("<html");
}

/**
 * Lector único y seguro del detalle de un error HTTP, usado en toda la app
 * (feedback, administración, login, streaming, carga/edición/borrado de
 * conversaciones). Intenta, en orden: 1) `{"detail": "..."}` de un cuerpo
 * JSON; 2) texto plano corto y de confianza; 3) `fallback` (por defecto,
 * el mensaje genérico por código) cuando el cuerpo está vacío, es JSON sin
 * `detail` utilizable, o no parece texto plano de confianza (HTML de un
 * proxy, binario, demasiado largo).
 *
 * Nunca muestra JSON serializado como mensaje (antes, un cuerpo JSON válido
 * pero sin `detail` terminaba mostrándose como si fuera texto plano —
 * ver `api.test.ts` para el contrato que este cambio preserva en los casos
 * que sí funcionaban). Este saneamiento solo decide qué TEXTO se muestra;
 * nunca decide si la solicitud fue exitosa (eso ya lo resolvió `res.ok`
 * antes de llamar a esta función).
 */
export async function readErrorDetail(
	res: Response,
	fallback: string = `Error del servidor (${res.status})`,
): Promise<string> {
	// `res.headers` se lee de forma defensiva: algunas pruebas simulan la
	// `Response` con un objeto plano que no incluye `headers`. Con una
	// `Response` real esto es exactamente `res.headers.get(...)`.
	const contentType = res.headers?.get?.("content-type") ?? null;
	const declaresJson = contentType != null && /^application\/json\b/i.test(contentType);

	try {
		const data: unknown = await res.clone().json();
		if (isRecord(data) && typeof data.detail === "string" && data.detail.trim()) {
			return data.detail.trim().slice(0, MAX_ERROR_DETAIL_LENGTH);
		}
		// JSON válido pero sin `detail` usable: nunca se reintenta como texto
		// plano (eso mostraría el JSON serializado tal cual).
		return fallback;
	} catch {
		// El cuerpo no es JSON válido. Si el `Content-Type` declaraba
		// `application/json`, ese cuerpo NUNCA se muestra como texto plano —
		// podría ser JSON truncado o corrupto, no un mensaje pensado para
		// leerse tal cual — así que se usa el fallback directamente sin
		// releerlo como texto.
		if (declaresJson) return fallback;
	}

	const text = await res.text().catch(() => "");
	const trimmed = text.trim();
	if (!trimmed || looksLikeUntrustedBody(trimmed, contentType)) return fallback;
	return trimmed.slice(0, MAX_ERROR_DETAIL_LENGTH);
}

export interface AdminUserRow {
	uid: string;
	email: string;
	displayName: string | null;
	role: string;
	createdAt: string;
}

export async function listAdminUsers(): Promise<AdminUserRow[]> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/admin/users`, {
		headers: { ...authHeaders(token) },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, token);
	if (!res.ok) throw new Error(await readErrorDetail(res));
	const data = (await res.json()) as { items: AdminUserRow[]; total: number };
	return data.items;
}

export async function createAdminUser(input: {
	email: string;
	password: string;
	displayName?: string | null;
}): Promise<AdminUserRow> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/admin/users`, {
		method: "POST",
		headers: { "Content-Type": "application/json", ...authHeaders(token) },
		body: JSON.stringify({
			email: input.email,
			password: input.password,
			displayName: input.displayName ?? null,
		}),
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, token);
	if (!res.ok) throw new Error(await readErrorDetail(res));
	return res.json() as Promise<AdminUserRow>;
}

export async function updateAdminUserPassword(
	uid: string,
	password: string,
): Promise<void> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/admin/users/${uid}/password`, {
		method: "PATCH",
		headers: { "Content-Type": "application/json", ...authHeaders(token) },
		body: JSON.stringify({ password }),
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, token);
	if (!res.ok) throw new Error(await readErrorDetail(res));
}

export async function submitConversationFeedback(
	request: FeedbackRequest,
): Promise<{ id: string }> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/feedback`, {
		method: "POST",
		headers: { "Content-Type": "application/json", ...authHeaders(token) },
		body: JSON.stringify(request),
		signal: withRestTimeout(),
	});

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		throw new Error(await readErrorDetail(res));
	}

	return res.json() as Promise<{ id: string }>;
}

export async function submitMessageFeedback(
	request: MessageFeedbackRequest,
): Promise<{ id: string }> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/feedback/message`, {
		method: "POST",
		headers: { "Content-Type": "application/json", ...authHeaders(token) },
		body: JSON.stringify(request),
		signal: withRestTimeout(),
	});

	if (res.status === 409) {
		throw new Error("Ya existe feedback para este mensaje.");
	}

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		throw new Error(await readErrorDetail(res));
	}

	return res.json() as Promise<{ id: string }>;
}

/**
 * Async generator que conecta al endpoint SSE de streaming y emite eventos
 * tipados a medida que llegan.
 */
export async function* queryRagStream(
	request: QueryRequest,
	signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
	const token = getToken();
	if (!token) {
		// El flujo que llega hasta aquí (submit() en useChat) solo es alcanzable
		// estando autenticado, así que un token ausente significa que se perdió
		// en otro lado (p. ej. otra pestaña cerró sesión) mientras el estado
		// React seguía creyendo que había sesión. Notifica para que la UI se
		// actualice, en vez de solo lanzar un error que deja el chat montado.
		expireAuthSession(null);
		throw new Error("La sesión no es válida. Inicia sesión nuevamente.");
	}
	const res = await fetch(`${API_URL}/api/query/stream`, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Authorization: `Bearer ${token}`,
		},
		body: JSON.stringify(request),
		signal,
	});

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		throw new Error(await readErrorDetail(res));
	}

	if (!res.body) throw new Error("El servidor no devolvió un flujo de respuesta.");
	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	const accumulator = new SseEventAccumulator();
	// Solo se vuelve `true` justo antes del `return` normal al ver `[DONE]`.
	// En cualquier otro camino de salida (error de lectura/parseo, abort
	// externo, o el consumidor abandona el generador antes de tiempo) el
	// stream se dio por terminado sin que el servidor lo cerrara con
	// `[DONE]`, así que corresponde cancelar la lectura subyacente en vez
	// de solo soltar el lock.
	let finishedByDone = false;

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) {
				throw new Error("El flujo de respuesta terminó de forma inesperada.");
			}

			const rawEvents = accumulator.push(decoder.decode(value, { stream: true }));
			for (const raw of rawEvents) {
				const parsed = parseStreamEvent(raw);
				if (parsed === null) continue; // tipo desconocido: se ignora, no rompe el stream
				if (parsed === SSE_DONE) {
					finishedByDone = true;
					return;
				}
				yield parsed;
			}
		}
	} finally {
		if (!finishedByDone) {
			try {
				await reader.cancel();
			} catch {
				// Best-effort: un fallo al cancelar nunca debe reemplazar (ni
				// sumarse a) el error real que ya determina cómo termina el
				// generador, ni producir una excepción cuando el consumidor
				// simplemente dejó de iterar sin que hubiera ningún error.
			}
		}
		reader.releaseLock();
	}
}
