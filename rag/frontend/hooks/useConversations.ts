"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { expireAuthSession, getToken } from "@/lib/auth";
import { throwIfSessionExpired } from "@/lib/api";
import { useAuth } from "@/components/providers/AuthProvider";
import { API_URL } from "@/lib/config";

export interface Conversation {
	id: string;
	title: string | null;
	threadId: string;
	createdAt: Date;
	updatedAt: Date;
	messageCount: number;
}

export function useConversations(): {
	conversations: Conversation[];
	loading: boolean;
	/**
	 * A4 — mensaje del último intento de refresco fallido, o `null` si el
	 * intento más reciente tuvo éxito (o todavía no se ha intentado ninguno).
	 * Un fallo transitorio (red caída, 500 del backend) NUNCA vacía
	 * `conversations`: la última lista válida conocida se conserva en
	 * pantalla, y este campo es lo único que le permite a la UI mostrar un
	 * aviso con opción de reintentar (`refresh`).
	 */
	error: string | null;
	refresh: () => Promise<void>;
} {
	const { user } = useAuth();
	const [conversations, setConversations] = useState<Conversation[]>([]);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// A4 — evita que una respuesta obsoleta (superada por un `refresh()` más
	// reciente) pise el resultado — válido o de error — de la solicitud
	// vigente.
	const abortRef = useRef<AbortController | null>(null);

	const refresh = useCallback(async () => {
		const token = getToken();
		if (!token) {
			// Si el hook todavía cree que hay un usuario autenticado pero el
			// token ya no está (p. ej. otra pestaña cerró sesión), notifica para
			// que la UI se actualice. No se emite cuando `user` ya es null: eso
			// es el estado inicial normal antes de iniciar sesión, no una
			// expiración. Este es un vaciado deliberado (sesión perdida), no un
			// fallo transitorio: `error` se limpia, no se fija.
			abortRef.current?.abort();
			if (user) expireAuthSession(null);
			setConversations([]);
			setError(null);
			return;
		}
		if (!user) {
			abortRef.current?.abort();
			setConversations([]);
			setError(null);
			return;
		}

		abortRef.current?.abort();
		const controller = new AbortController();
		abortRef.current = controller;

		setLoading(true);
		try {
			const res = await fetch(`${API_URL}/api/conversations`, {
				headers: { Authorization: `Bearer ${token}` },
				signal: controller.signal,
			});
			await throwIfSessionExpired(res, token);
			if (!res.ok) throw new Error(`Error ${res.status}`);
			const data = (await res.json()) as Array<{
				id: string;
				title: string | null;
				thread_id: string;
				created_at: string;
				updated_at: string;
				message_count: number;
			}>;
			if (abortRef.current !== controller) return;
			setConversations(
				data.map((c) => ({
					id: c.id,
					title: c.title,
					threadId: c.thread_id,
					createdAt: new Date(c.created_at),
					updatedAt: new Date(c.updated_at),
					messageCount: c.message_count,
				})),
			);
			setError(null);
		} catch (e) {
			// Una cancelación deliberada (superada por una solicitud más
			// reciente) no es un error visible para el usuario.
			if (e instanceof DOMException && e.name === "AbortError") return;
			if (abortRef.current !== controller) return;
			// A4 — a diferencia del comportamiento anterior, un fallo aquí ya NO
			// hace `setConversations([])`: la última lista válida se conserva,
			// y el aviso de error convive con ella en la UI (ver
			// ConversationList).
			setError(
				e instanceof Error
					? e.message
					: "No fue posible cargar las conversaciones.",
			);
		} finally {
			if (abortRef.current === controller) setLoading(false);
		}
	}, [user]);

	useEffect(() => {
		void refresh();
	}, [refresh]);

	useEffect(() => {
		return () => {
			abortRef.current?.abort();
		};
	}, []);

	return { conversations, loading, error, refresh };
}
