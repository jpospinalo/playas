/**
 * Calendario del ejercicio (reunión del 20-oct, T5). Backend:
 * `rag/backend/rag/api/calendario.py`.
 */

import { API_URL } from "@/lib/config";
import { withRestTimeout } from "@/lib/httpTimeout";
import { readErrorDetail, throwIfSessionExpired } from "@/lib/api";
import { getToken } from "@/lib/auth";

export interface FechaCalendario {
	clave: string;
	texto: string;
	fecha: string;
}

export interface Calendario {
	fechas: FechaCalendario[];
	dias_participante: number;
	hoy: string;
	mi_limite: string | null;
	mi_limite_texto: string | null;
	dias_restantes: number | null;
}

export interface Ventana {
	primer_dia: string | null;
	ultimo_dia: string;
	dias_restantes: number;
}

async function llamar<T>(ruta: string, init: RequestInit = {}): Promise<T> {
	const t = getToken();
	const res = await fetch(`${API_URL}${ruta}`, {
		...init,
		headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(await readErrorDetail(res));
	return (await res.json()) as T;
}

export function pedirCalendario(): Promise<Calendario> {
	return llamar("/api/evaluacion/calendario");
}

export function guardarCalendario(fechas: Record<string, string>, diasParticipante: number): Promise<Calendario> {
	return llamar("/api/evaluacion/calendario", {
		method: "PUT",
		body: JSON.stringify({ fechas, dias_participante: diasParticipante }),
	});
}

export function pedirVentana(): Promise<Ventana> {
	return llamar("/api/ejercicio/ventana");
}

const fmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", timeZone: "UTC" });

/** "27 de noviembre" a partir de "2026-11-27". */
export function diaLargo(iso: string): string {
	return fmt.format(new Date(`${iso}T12:00:00Z`));
}

/** "Quedan 3 días", "Hoy es el último día", "El plazo terminó". */
export function textoRestante(dias: number): string {
	if (dias < 0) return "El plazo terminó";
	if (dias === 0) return "Hoy es el último día";
	return dias === 1 ? "Queda 1 día" : `Quedan ${dias} días`;
}
