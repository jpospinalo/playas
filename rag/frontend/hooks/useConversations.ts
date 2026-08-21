"use client";

import { useCallback, useEffect, useState } from "react";
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
	refresh: () => Promise<void>;
} {
	const { user } = useAuth();
	const [conversations, setConversations] = useState<Conversation[]>([]);
	const [loading, setLoading] = useState(false);

	const refresh = useCallback(async () => {
		const token = getToken();
		if (!token) {
			// Si el hook todavía cree que hay un usuario autenticado pero el
			// token ya no está (p. ej. otra pestaña cerró sesión), notifica para
			// que la UI se actualice. No se emite cuando `user` ya es null: eso
			// es el estado inicial normal antes de iniciar sesión, no una
			// expiración.
			if (user) expireAuthSession(null);
			setConversations([]);
			return;
		}
		if (!user) {
			setConversations([]);
			return;
		}
		setLoading(true);
		try {
			const res = await fetch(`${API_URL}/api/conversations`, {
				headers: { Authorization: `Bearer ${token}` },
			});
			await throwIfSessionExpired(res, token);
			if (!res.ok) {
				setConversations([]);
				return;
			}
			const data = (await res.json()) as Array<{
				id: string;
				title: string | null;
				thread_id: string;
				created_at: string;
				updated_at: string;
				message_count: number;
			}>;
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
		} catch {
			setConversations([]);
		} finally {
			setLoading(false);
		}
	}, [user]);

	useEffect(() => {
		void refresh();
	}, [refresh]);

	return { conversations, loading, refresh };
}
