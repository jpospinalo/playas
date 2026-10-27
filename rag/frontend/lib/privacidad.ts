/**
 * Aviso de privacidad y autorización de tratamiento de datos (Ley 1581 de
 * 2012, Decreto 1377 de 2013). Backend: `rag/backend/rag/api/routes/privacidad.py`.
 */

import { API_URL } from "@/lib/config";
import { withRestTimeout } from "@/lib/httpTimeout";
import { readErrorDetail, throwIfSessionExpired } from "@/lib/api";
import { getToken } from "@/lib/auth";

export interface Privacidad {
	version: string;
	parrafos: string[];
	/** PQ-110: correo para revocar la autorización (null si no está configurado). */
	correo?: string | null;
	aceptada: boolean;
	fecha: string | null;
}

async function llamar(init: RequestInit = {}): Promise<Privacidad> {
	const t = getToken();
	const res = await fetch(`${API_URL}/api/privacidad`, {
		...init,
		headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(await readErrorDetail(res));
	return (await res.json()) as Privacidad;
}

export function pedirPrivacidad(): Promise<Privacidad> {
	return llamar();
}

export function autorizarPrivacidad(): Promise<Privacidad> {
	return llamar({ method: "POST", body: JSON.stringify({ acepto: true }) });
}
