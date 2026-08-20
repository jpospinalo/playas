import { API_URL } from "@/lib/config";
import { expireAuthSession, getToken } from "@/lib/auth";
import type {
	FeedbackRequest,
	MessageFeedbackRequest,
	QueryRequest,
	QueryResponse,
	StreamEvent,
} from "@/lib/types";

const SESSION_EXPIRED_MESSAGE = "Tu sesión expiró. Inicia sesión nuevamente.";

function authHeaders(token: string | null): Record<string, string> {
	return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Comprueba si `response` es un 401 y, de serlo, invalida la sesión asociada
 * a `requestToken` (solo si ese token sigue siendo el activo — ver
 * `expireAuthSession`) y lanza un error legible para el usuario.
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
	if (requestToken) expireAuthSession(requestToken, SESSION_EXPIRED_MESSAGE);
	throw new Error(SESSION_EXPIRED_MESSAGE);
}

export async function queryRag(request: QueryRequest): Promise<QueryResponse> {
	const token = getToken();
	const res = await fetch(`${API_URL}/api/query`, {
		method: "POST",
		headers: { "Content-Type": "application/json", ...authHeaders(token) },
		body: JSON.stringify(request),
	});

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		throw new Error(await readErrorDetail(res));
	}

	return res.json() as Promise<QueryResponse>;
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

async function readErrorDetail(res: Response): Promise<string> {
	try {
		const data = (await res.clone().json()) as { detail?: string };
		if (data?.detail) return data.detail;
	} catch {
		// no es JSON
	}
	const text = await res.text().catch(() => "");
	return text.trim() || `Error del servidor (${res.status})`;
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
	});

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		const detail = await res.text().catch(() => "");
		throw new Error(detail.trim() || `Error del servidor (${res.status})`);
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
	});

	if (res.status === 409) {
		throw new Error("Ya existe feedback para este mensaje.");
	}

	await throwIfSessionExpired(res, token);
	if (!res.ok) {
		const detail = await res.text().catch(() => "");
		throw new Error(detail.trim() || `Error del servidor (${res.status})`);
	}

	return res.json() as Promise<{ id: string }>;
}

/** @deprecated Use submitConversationFeedback instead. */
export async function submitFeedback(
	request: FeedbackRequest,
): Promise<{ id: string }> {
	return submitConversationFeedback(request);
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
	if (!token) throw new Error("La sesión no es válida. Inicia sesión nuevamente.");
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
	let buffer = "";

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) {
				throw new Error("El flujo de respuesta terminó de forma inesperada.");
			}

			buffer += decoder.decode(value, { stream: true });

			const parts = buffer.split("\n\n");
			buffer = parts.pop() ?? "";

			for (const part of parts) {
				const line = part.trim();
				if (!line.startsWith("data: ")) continue;

				const data = line.slice(6);
				if (data === "[DONE]") return;

				yield JSON.parse(data) as StreamEvent;
			}
		}
	} finally {
		reader.releaseLock();
	}
}
