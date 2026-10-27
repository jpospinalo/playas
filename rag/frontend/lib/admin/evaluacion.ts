/**
 * Evaluación de las preguntas del ejercicio de validación (planilla del
 * profe). Backend: `rag/backend/rag/api/routes/evaluacion.py`.
 * Evaluadores (semilleristas) califican; el comité resuelve diferencias,
 * fija la final, elige ganadoras empatadas y exporta.
 */

import { API_URL } from "@/lib/config";
import { withRestTimeout } from "@/lib/httpTimeout";
import { throwIfSessionExpired } from "@/lib/api";
import { expireAuthSession, getToken } from "@/lib/auth";

export type Ct = "S" | "I" | "A";
export type EstadoPregunta =
	| "sin_evaluar"
	| "una_evaluacion"
	| "concordante"
	| "validada"
	| "con_diferencias"
	| "final";
export type FiltroBandeja = "pendientes" | "mias" | "con_diferencias" | "por_validar" | "finalizadas" | "todas";

export const NIVELES: Record<Ct, string> = { S: "Sencillo", I: "Intermedio", A: "Avanzado" };
export const RANGOS: Record<Ct, [number, number]> = { S: [3, 6], I: [7, 9], A: [10, 12] };

export const TEXTO_ESTADO: Record<EstadoPregunta, string> = {
	sin_evaluar: "Sin calificar",
	una_evaluacion: "Falta una calificación",
	concordante: "Concordantes: falta la validación jurídica",
	validada: "Validada (promedio de las dos)",
	con_diferencias: "Con diferencias: va al comité",
	final: "Revisada por el comité",
};

export function rolEvalua(rol: string | null | undefined): boolean {
	return rol === "evaluador" || rol === "comite" || rol === "admin" || rol === "super-admin";
}

export function rolComite(rol: string | null | undefined): boolean {
	return rol === "comite" || rol === "admin" || rol === "super-admin";
}

export interface Oficial {
	estado: EstadoPregunta;
	f1: number | null;
	f2: number | null;
	f3: number | null;
	ct: Ct | null;
	cv: number | null;
	total: number | null;
	valida: boolean | null;
}

export interface ItemBandeja {
	message_id: string;
	numero: number;
	codigo: string;
	tipo_playa: number | null;
	tipo_playa_nombre: string | null;
	fecha: string;
	hora: string;
	pregunta: string;
	evaluaciones: number;
	evaluada_por_mi: boolean;
	/** T7: de una cuenta de práctica (no cuenta para nada). */
	practica?: boolean;
	estado: EstadoPregunta;
	oficial: Oficial;
}

export interface Bandeja {
	items: ItemBandeja[];
	total: number;
	page: number;
	page_size: number;
	conteos: Record<FiltroBandeja, number>;
}

export interface CalificacionOut {
	/** Id de la evaluación (para abrir su conversación de validación). */
	id?: string;
	evaluador: string;
	sede: string | null;
	f1: number;
	f2: number;
	f3: number;
	forma: number;
	ct: Ct;
	cv: number;
	total: number;
	valida: boolean;
	observaciones: string | null;
	es_final: boolean;
}

export interface Ficha {
	practica?: boolean;
	message_id: string;
	numero: number;
	codigo: string;
	tipo_playa: number | null;
	tipo_playa_nombre: string | null;
	fecha: string;
	hora: string;
	pregunta: string;
	respuesta: string | null;
	estado: EstadoPregunta;
	mia: CalificacionOut | null;
	otras: CalificacionOut[] | null;
	final: CalificacionOut | null;
	oficial: Oficial;
	puede_evaluar: boolean;
	motivo_no_puede: string | null;
	es_comite: boolean;
	anterior: string | null;
	siguiente: string | null;
}

export interface CalificacionIn {
	f1: number;
	f2: number;
	f3: number;
	ct: Ct;
	cv: number;
	valida: boolean;
	observaciones: string | null;
}

export interface Rubrica {
	forma: Record<"f1" | "f2" | "f3", { nombre: string; pregunta: string; niveles: Record<string, string> }>;
	fondo: Record<Ct, { nivel: string; como: string; guia: Record<string, string> }>;
	rangos: Record<Ct, [number, number]>;
	umbral_diferencia: number;
}

export interface ResumenEjercicio {
	preguntas_registradas: number;
	evaluadas: number;
	estados: Record<EstadoPregunta, number>;
	no_validas: number;
	por_nivel: Record<Ct, number>;
	promedio_total: number;
	por_tipo_playa: { tipo: number; nombre: string; preguntas: number }[];
	avance_evaluadores: { evaluador: string; sede: string | null; evaluadas: number }[];
	umbral_diferencia: number;
	/** Decisión 9: solo cuentan las validadas por el comité. */
	solo_revisadas: boolean;
}

export interface FilaPremio {
	message_id: string;
	codigo: string;
	texto: string;
	cv: number;
	total: number;
}

export interface Premios {
	mejor_pregunta: Record<
		Ct,
		{ ganadora: FilaPremio | null; empatadas: FilaPremio[]; decide_comite: boolean; siguientes: FilaPremio[] }
	>;
	participacion_constante: { codigo: string; dias: number; preguntas_validas: number; puntaje: number }[];
	gratificacion: { codigo: string; dias: number; preguntas_validas: number; puntaje: number }[];
	participacion_por_dia: {
		codigo: string;
		tipo_playa: number | null;
		preguntas: number;
		dias: string[];
		preguntas_validas: number;
		dias_validos: number;
		puntaje: number;
	}[];
	/** Concordantes que aún no cuentan porque el comité no las ha validado. */
	por_validar: number;
	solo_revisadas: boolean;
	nota: string;
}

async function llamar<T>(ruta: string, init: RequestInit = {}): Promise<T> {
	const t = getToken();
	if (!t) {
		expireAuthSession(null);
		throw new Error("Su sesión se cerró. Vuelva a entrar.");
	}
	const res = await fetch(`${API_URL}/api/evaluacion${ruta}`, {
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

export function pedirRubrica(): Promise<Rubrica> {
	return llamar("/catalogo");
}

export function pedirBandeja(
	estado: FiltroBandeja,
	tipo: number,
	ct: Ct | "",
	page: number,
	pageSize = 20,
): Promise<Bandeja> {
	const q = new URLSearchParams({ estado, page: String(page), page_size: String(pageSize) });
	if (tipo) q.set("tipo_playa", String(tipo));
	if (ct) q.set("ct", ct);
	return llamar(`/bandeja?${q}`);
}

export function pedirFicha(id: string): Promise<Ficha> {
	return llamar(`/preguntas/${encodeURIComponent(id)}`);
}

export function guardarCalificacion(id: string, cal: CalificacionIn, final: boolean): Promise<Ficha> {
	return llamar(`/preguntas/${encodeURIComponent(id)}/${final ? "final" : "mia"}`, {
		method: "PUT",
		body: JSON.stringify(cal),
	});
}

export function pedirResumenEjercicio(): Promise<ResumenEjercicio> {
	return llamar("/resumen");
}

export function pedirPremios(): Promise<Premios> {
	return llamar("/premios");
}

export function elegirGanadora(nivel: Ct, messageId: string): Promise<Premios> {
	return llamar(`/premios/${nivel}/ganadora`, { method: "PUT", body: JSON.stringify({ message_id: messageId }) });
}

export interface EstadoPractica {
	cuentas: number;
	preguntas: number;
	archivada: boolean;
}

export function pedirPractica(): Promise<EstadoPractica> {
	return llamar("/practica");
}

/** T7: el admin saca la práctica de todas las vistas antes del 2 nov (no borra nada). */
export function archivarPractica(archivar: boolean): Promise<EstadoPractica> {
	return llamar("/practica/archivar", { method: "POST", body: JSON.stringify({ archivar, confirmar: true }) });
}

/** E1: las asignadas sin evaluar de un semillerista pasan a otro de su sede. */
export function reasignarPendientes(evaluadorId: string): Promise<{ reasignadas: number; sin_destino: number }> {
	return llamar("/reasignar", { method: "POST", body: JSON.stringify({ evaluador_id: evaluadorId, confirmar: true }) });
}

export async function descargarPlanilla(): Promise<void> {
	const t = getToken();
	if (!t) throw new Error("Su sesión se cerró. Vuelva a entrar.");
	const res = await fetch(`${API_URL}/api/evaluacion/exportar.xlsx`, {
		headers: { Authorization: `Bearer ${t}` },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(`No se pudo descargar (${res.status}).`);
	const url = URL.createObjectURL(await res.blob());
	const a = document.createElement("a");
	a.href = url;
	a.download = "planilla-evaluacion-atlas.xlsx";
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Total de la planilla: forma (F1+F2+F3) + Cv. */
export function totalPlanilla(f1: number, f2: number, f3: number, cv: number): number {
	return f1 + f2 + f3 + cv;
}

/** Cv dentro del rango del nivel; si no, el mínimo del rango. */
export function cvEnRango(ct: Ct, cv: number): number {
	const [min, max] = RANGOS[ct];
	return cv >= min && cv <= max ? cv : min;
}
