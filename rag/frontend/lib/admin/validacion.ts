/**
 * Validación de las evaluaciones (reunión del 20-oct): jurídica por
 * evaluación (de acuerdo / no + conversación), gestión costera por pregunta
 * (pertinente sí/no). Backend: `rag/backend/rag/api/routes/validacion.py`.
 */

import { API_URL } from "@/lib/config";
import { withRestTimeout } from "@/lib/httpTimeout";
import { throwIfSessionExpired } from "@/lib/api";
import { expireAuthSession, getToken } from "@/lib/auth";
import type { Ct } from "@/lib/admin/evaluacion";

export type EstadoValidacion = "por_validar" | "en_conversacion" | "validada";
export type FiltroValidacion = "por_validar" | "en_conversacion" | "validadas" | "todas";

export const TEXTO_VALIDACION: Record<EstadoValidacion, string> = {
	por_validar: "Por validar",
	en_conversacion: "En conversación",
	validada: "Validada",
};

export interface EvaluacionV {
	id: string;
	sede: string | null;
	evaluador: string;
	f1: number;
	f2: number;
	f3: number;
	forma: number;
	ct: Ct;
	cv: number;
	total: number;
	valida: boolean;
	observaciones: string | null;
	estado: EstadoValidacion;
	comentarios: number;
}

export interface ItemValidacion {
	message_id: string;
	numero: number;
	codigo: string;
	tipo_playa_nombre: string | null;
	fecha: string;
	pregunta: string;
	pertinente: boolean | null;
	evaluaciones: EvaluacionV[];
}

export interface BandejaValidacion {
	tipo: "juridico" | "costero" | null;
	sede: string | null;
	items: ItemValidacion[];
	total: number;
	page: number;
	page_size: number;
	conteos: Record<string, number>;
}

export interface EntradaHilo {
	autor: string;
	tipo: "comentario" | "desacuerdo" | "acuerdo" | "correccion";
	texto: string;
	fecha: string;
}

export interface DetalleEvaluacion {
	evaluacion: EvaluacionV;
	hilo: EntradaHilo[];
}

async function llamar<T>(ruta: string, init: RequestInit = {}): Promise<T> {
	const t = getToken();
	if (!t) {
		expireAuthSession(null);
		throw new Error("Su sesión se cerró. Vuelva a entrar.");
	}
	const res = await fetch(`${API_URL}/api/evaluacion/validacion${ruta}`, {
		...init,
		headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json", ...(init.headers ?? {}) },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) {
		let detalle = "";
		try {
			const cuerpo = await res.json();
			detalle = typeof cuerpo.detail === "string" ? cuerpo.detail : "";
		} catch {
			// sin cuerpo
		}
		throw new Error(detalle || `El servidor respondió con un error (${res.status}).`);
	}
	return (await res.json()) as T;
}

export function pedirBandejaValidacion(estado: FiltroValidacion, page: number, pageSize = 20): Promise<BandejaValidacion> {
	const q = new URLSearchParams({ estado, page: String(page), page_size: String(pageSize) });
	return llamar(`/bandeja?${q}`);
}

export function pedirDetalle(id: string): Promise<DetalleEvaluacion> {
	return llamar(`/evaluaciones/${encodeURIComponent(id)}`);
}

export function validarEvaluacion(id: string, deAcuerdo: boolean, comentario?: string): Promise<DetalleEvaluacion> {
	return llamar(`/evaluaciones/${encodeURIComponent(id)}`, {
		method: "PUT",
		body: JSON.stringify({ de_acuerdo: deAcuerdo, comentario: comentario || null }),
	});
}

export function comentar(id: string, texto: string): Promise<DetalleEvaluacion> {
	return llamar(`/evaluaciones/${encodeURIComponent(id)}/comentarios`, {
		method: "POST",
		body: JSON.stringify({ texto }),
	});
}

export function deAcuerdoEnLote(ids: string[]): Promise<{ validadas: number }> {
	return llamar("/lote", { method: "POST", body: JSON.stringify({ evaluaciones: ids, confirmar: true }) });
}

export function marcarPertinencia(
	messageId: string,
	pertinente: boolean,
	comentario?: string,
): Promise<{ pertinente: boolean }> {
	return llamar(`/preguntas/${encodeURIComponent(messageId)}/pertinencia`, {
		method: "PUT",
		body: JSON.stringify({ pertinente, comentario: comentario || null }),
	});
}
