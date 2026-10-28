/**
 * Panel de administración: tipos, llamadas al backend (solo lectura) y
 * formato de cifras en español de Colombia.
 *
 * Las rutas viven en `rag/backend/rag/api/routes/panel.py`; las
 * clasificaciones (tema, playa, resultado) se hacen allá, sin IA.
 */

import { API_URL } from "@/lib/config";
import { isNetworkError, isRestTimeoutError, withRestTimeout } from "@/lib/httpTimeout";
import { throwIfSessionExpired } from "@/lib/api";
import { expireAuthSession, getToken } from "@/lib/auth";

export type Agrupacion = "dia" | "semana";

export interface Cifras {
	preguntas: number;
	personas: number;
	personas_nuevas: number;
	respuestas: number;
	con_fuente: number;
	sin_respuesta_segura: number;
	fuera_de_tema: number;
	pide_aclarar: number;
	saludos: number;
	sin_respuesta_guardada: number;
	calificaciones: number;
	le_sirvio: number;
	no_le_sirvio: number;
}

export interface Punto {
	fecha: string;
	desde: string;
	hasta: string;
	parcial: boolean;
	preguntas: number;
	sin_respuesta_segura: number;
}

export interface TemaResumen {
	id: string;
	titulo: string;
	preguntas: number;
	calificaciones: number;
	le_sirvio: number;
	brechas: number;
}

export interface Norma {
	nombre: string;
	doc_type: string | null;
	respuestas: number;
}

export interface Brecha {
	pregunta: string;
	veces: number;
	tema: string;
	tema_titulo: string;
	motivo: "sin_respuesta_segura" | "no_le_sirvio";
	esperaba: string | null;
	ultima: string;
	conversation_id: string;
}

export interface Resumen {
	demo: boolean;
	periodo: { dias: number; desde: string | null; hasta: string; agrupacion: Agrupacion };
	cifras: Cifras;
	anterior: Cifras | null;
	serie: Punto[];
	temas: TemaResumen[];
	normas: Norma[];
	playas: { nombre: string; preguntas: number }[];
	sin_playa: number;
	personas: { activas: number; nuevas: number; recurrentes: number; preguntas_por_persona: number };
	brechas_total: number;
	brechas: Brecha[];
}

export type Resultado =
	| "con_fuente"
	| "sin_evidencia"
	| "sin_cita_valida"
	| "sin_fuente_otro"
	| "fuera_de_tema"
	| "pide_aclarar"
	| "saludo"
	| "sin_respuesta";

export type Calificacion = "util" | "no_util" | "neutra";

export interface PreguntaItem {
	id: string;
	fecha: string;
	pregunta: string;
	tema: string;
	tema_titulo: string;
	playa: string | null;
	resultado: Resultado;
	fuentes: number;
	/** Cuántas de las fuentes son sentencias (el resto, normas). */
	fuentes_sentencias: number;
	calificacion: Calificacion | null;
	esperaba: string | null;
	persona: string;
	/** Número de participante y tipo de usuario de playa (ejercicio de validación). */
	participante?: string | null;
	tipo_playa?: number | null;
	conversation_id: string;
}

export interface Preguntas {
	items: PreguntaItem[];
	total: number;
	page: number;
	page_size: number;
}

export interface Conversacion {
	id: string;
	titulo: string | null;
	persona: string;
	creada: string;
	mensajes: {
		id: string;
		role: string;
		text: string;
		fecha: string;
		resultado: Resultado | null;
		fuentes: { nombre: string; doc_type: string | null }[];
		calificacion: Calificacion | null;
		esperaba: string | null;
	}[];
}

export type FiltroResultado =
	| ""
	| "con_fuente"
	| "sin_respuesta_segura"
	| "no_le_sirvio"
	| "fuera_de_tema"
	| "pide_aclarar"
	| "calificadas"
	| "le_sirvio"
	| "con_esperaba";

export interface Encuesta {
	id: string;
	fecha: string;
	persona: string;
	titulo: string | null;
	conversation_id: string | null;
	general: number;
	/** Claridad de las respuestas: solo en las encuestas nuevas. */
	claridad: number | null;
	tono: number | null;
	/** 1 muy corta, 3 adecuada, 5 muy larga (no es una escala de calidad). */
	largo: number | null;
	facilidad: number;
	comentario: string | null;
}

export interface Encuestas {
	items: Encuesta[];
	total: number;
	page: number;
	page_size: number;
	promedios: { general: number; claridad: number; tono: number; largo: number; facilidad: number };
}

export type FiltroEncuesta = "" | "buenas" | "malas" | "con_comentario";

export const PERIODOS = [
	{ dias: 7, texto: "7 días" },
	{ dias: 30, texto: "30 días" },
	{ dias: 90, texto: "90 días" },
	{ dias: 0, texto: "Todo" },
] as const;

/** Temas del flujo guiado + "otros" (mismos ids que el backend). */
export const TEMAS_PANEL = [
	{ id: "entrar", titulo: "Entrar o caminar por la playa" },
	{ id: "pescar", titulo: "Pescar" },
	{ id: "vender", titulo: "Vender en la playa" },
	{ id: "hoteles", titulo: "Hoteles y negocios frente al mar" },
	{ id: "lanchas", titulo: "Lanchas, motos de agua y bañistas" },
	{ id: "obras", titulo: "Construcciones cerca del mar" },
	{ id: "otros", titulo: "Otros temas" },
] as const;

export const SIN_RESPUESTA_SEGURA: Resultado[] = ["sin_evidencia", "sin_cita_valida", "sin_fuente_otro"];

/** PQ-129: por debajo de este número de casos un % engaña (con 9 casos el
 * margen va de 12 a 65 %): se muestra el conteo y "pocos datos". Único para
 * todas las tasas del panel. */
export const MINIMO_PARA_PORCENTAJE = 20;

// ── Llamadas ───────────────────────────────────────────────────────────────

async function token(): Promise<string> {
	const t = getToken();
	if (!t) {
		expireAuthSession(null);
		throw new Error("Su sesión se cerró. Vuelva a entrar.");
	}
	return t;
}

function consulta(params: Record<string, string | number | null | undefined>): string {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
	}
	return q.toString();
}

async function pedir<T>(ruta: string): Promise<T> {
	const t = await token();
	const res = await fetch(`${API_URL}/api/admin/panel${ruta}`, {
		headers: { Authorization: `Bearer ${t}` },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (res.status === 403) throw new Error("Su cuenta no tiene permiso para ver el panel.");
	if (!res.ok) throw new Error(`El servidor respondió con un error (${res.status}).`);
	return (await res.json()) as T;
}

/** PQ-133: si la base es la de demostración (para avisarlo en todo /admin). */
export async function pedirDemo(): Promise<boolean> {
	return (await pedir<{ demo: boolean }>("/demo")).demo;
}

/** Filtro por persona del ejercicio: número de participante y tipo de playa. */
export interface FiltroPersona {
	participante?: string;
	tipo?: number;
}

function paramsPersona(p?: FiltroPersona): Record<string, string | number | undefined> {
	return { participante: p?.participante || undefined, tipo_playa: p?.tipo || undefined };
}

export function pedirResumen(dias: number, tema: string, persona?: FiltroPersona): Promise<Resumen> {
	return pedir(`/resumen?${consulta({ dias, tema, ...paramsPersona(persona) })}`);
}

export function pedirPreguntas(
	dias: number,
	tema: string,
	resultado: FiltroResultado,
	page: number,
	pageSize = 20,
	persona?: FiltroPersona,
): Promise<Preguntas> {
	return pedir(
		`/preguntas?${consulta({ dias, tema, resultado, page, page_size: pageSize, ...paramsPersona(persona) })}`,
	);
}

export function pedirConversacion(id: string): Promise<Conversacion> {
	return pedir(`/conversaciones/${encodeURIComponent(id)}`);
}

export function pedirEncuestas(
	dias: number,
	filtro: FiltroEncuesta,
	page: number,
	pageSize = 20,
): Promise<Encuestas> {
	return pedir(`/encuestas?${consulta({ dias, filtro, page, page_size: pageSize })}`);
}

/** Descarga el CSV con la sesión actual (el enlace directo no lleva el token). */
export async function descargarCsv(
	dias: number,
	tema: string,
	resultado: FiltroResultado,
	persona?: FiltroPersona,
): Promise<void> {
	const t = await token();
	const q = consulta({ dias, tema, resultado, ...paramsPersona(persona) });
	const res = await fetch(`${API_URL}/api/admin/panel/preguntas.csv?${q}`, {
		headers: { Authorization: `Bearer ${t}` },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(`No se pudo descargar (${res.status}).`);
	const blob = await res.blob();
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = `atlas-preguntas-${dias === 0 ? "todo" : `${dias}-dias`}.csv`;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** CSV de encuestas con sus comentarios (evidencia del informe final, PDF p. 9). */
export async function descargarEncuestasCsv(dias: number): Promise<void> {
	const t = await token();
	const res = await fetch(`${API_URL}/api/admin/panel/encuestas.csv?${consulta({ dias })}`, {
		headers: { Authorization: `Bearer ${t}` },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(`No se pudo descargar (${res.status}).`);
	const url = URL.createObjectURL(await res.blob());
	const a = document.createElement("a");
	a.href = url;
	a.download = `atlas-encuestas-${dias === 0 ? "todo" : `${dias}-dias`}.csv`;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Formato ─────────────────────────────────────────────────────────────────

const ZONA = "America/Bogota";
const fmtNumero = new Intl.NumberFormat("es-CO");
const fmtDecimal = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const fmtDiaMes = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", timeZone: ZONA });
const fmtDiaMesUTC = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", timeZone: "UTC" });
const fmtLargo = new Intl.DateTimeFormat("es-CO", {
	day: "numeric",
	month: "long",
	year: "numeric",
	timeZone: ZONA,
});
const fmtHora = new Intl.DateTimeFormat("es-CO", {
	hour: "numeric",
	minute: "2-digit",
	hour12: false,
	timeZone: ZONA,
});

/** `1234` → `1.234`. */
export function numero(n: number): string {
	return fmtNumero.format(n);
}

/** `7.46` → `7,5`. */
export function decimal(n: number): string {
	return fmtDecimal.format(n);
}

/** "1 pregunta" / "3 preguntas": singular y plural correctos (J5-2). */
export function cuantas(n: number, uno: string, varios: string): string {
	return `${numero(n)} ${n === 1 ? uno : varios}`;
}

/** Promedio con su sustantivo: "1 pregunta", "1,5 preguntas" (PQ-96). */
export function cuantasDecimal(n: number, uno: string, varios: string): string {
	return `${decimal(n)} ${n === 1 ? uno : varios}`;
}

/** Porcentaje entero, o `null` si no hay base. */
export function porcentaje(parte: number, total: number): number | null {
	if (!total) return null;
	return Math.round((parte / total) * 100);
}

/** `"81 %"` con espacio duro, o `"—"` sin base. */
export function textoPorcentaje(parte: number, total: number): string {
	const p = porcentaje(parte, total);
	return p === null ? "—" : `${p} %`;
}

/** PQ-129: el % solo con base suficiente; si no, "pocos datos". */
export function tasaConBase(parte: number, total: number): number | null {
	return total >= MINIMO_PARA_PORCENTAJE ? porcentaje(parte, total) : null;
}

/** `"54 %"` con base suficiente; `"pocos datos"` si no (PQ-129). */
export function textoTasa(parte: number, total: number): string {
	const p = tasaConBase(parte, total);
	return p === null ? (total ? "pocos datos" : "—") : `${p} %`;
}

/** "25 de oct." → "25 oct": día y mes abreviado, sin "de" ni punto. */
function sinPunto(s: string): string {
	return s.replace(/\./g, "").replace(/ de /, " ");
}

/** Fecha ISO (instante) → "26 oct" en hora de Colombia. */
export function diaMes(iso: string): string {
	return sinPunto(fmtDiaMes.format(new Date(iso)));
}

/** Fecha calendario "2026-10-26" (ya en hora de Colombia) → "26 oct". */
export function diaMesCalendario(fecha: string): string {
	return sinPunto(fmtDiaMesUTC.format(new Date(`${fecha}T00:00:00Z`)));
}

/** Fecha "2026-10-14" y hora "08:49" ya en hora de Colombia → "14 oct, 8:49" (PQ-74). */
export function diaHoraCalendario(fecha: string, hora: string): string {
	const [h, m] = hora.split(":");
	return `${diaMesCalendario(fecha)}, ${Number(h)}:${m}`;
}

/** Fecha ISO → "26 de octubre de 2026" en hora de Colombia. */
export function fechaLarga(iso: string): string {
	return fmtLargo.format(new Date(iso));
}

/** Fecha ISO → "26 oct, 9:41". */
export function fechaHora(iso: string): string {
	const d = new Date(iso);
	return `${sinPunto(fmtDiaMes.format(d))}, ${fmtHora.format(d)}`;
}

export interface Cambio {
	/** "incierto": la diferencia cabe en el margen de error (PQ-128). */
	direccion: "sube" | "baja" | "igual" | "incierto";
	texto: string;
}

/** PQ-128: base mínima de cada periodo para afirmar un cambio. */
export const MINIMO_PARA_COMPARAR = 30;
/** |z| de una prueba bilateral al 95 %. */
const Z_95 = 1.96;

/**
 * Cambio en un conteo frente al periodo anterior, comparando **promedio por
 * día** (el periodo actual puede ir a medias: 6,4 días contra 7). Solo hay
 * flecha si los dos conteos llegan a 30 y la diferencia supera el margen
 * (prueba de razón de Poisson al 95 %); si no, "sin cambio claro".
 */
export function cambioConteo(
	actual: number,
	anterior: number | null | undefined,
	diasActual = 1,
	diasAnterior = 1,
): Cambio | null {
	if (anterior === null || anterior === undefined || anterior === 0 || diasActual <= 0 || diasAnterior <= 0)
		return null;
	const ra = actual / diasActual;
	const rb = anterior / diasAnterior;
	const p = Math.round(((ra - rb) / rb) * 100);
	if (p === 0) return { direccion: "igual", texto: "igual" };
	const ee = Math.sqrt(actual / diasActual ** 2 + anterior / diasAnterior ** 2);
	if (actual < MINIMO_PARA_COMPARAR || anterior < MINIMO_PARA_COMPARAR || Math.abs(ra - rb) <= Z_95 * ee)
		return { direccion: "incierto", texto: "sin cambio claro" };
	return { direccion: p > 0 ? "sube" : "baja", texto: `${Math.abs(p)} % por día` };
}

/**
 * Cambio en una tasa (x de n) frente al periodo anterior, en puntos. Flecha
 * solo si las dos bases llegan a 30 y la prueba de dos proporciones da
 * p < 0,05; si no, "sin cambio claro" (PQ-128).
 */
export function cambioTasa(xa: number, na: number, xb: number | null, nb: number | null): Cambio | null {
	if (!na || xb === null || !nb) return null;
	const pa = xa / na;
	const pb = xb / nb;
	const d = Math.round(pa * 100) - Math.round(pb * 100);
	if (d === 0) return { direccion: "igual", texto: "igual" };
	const pp = (xa + xb) / (na + nb);
	const ee = Math.sqrt(pp * (1 - pp) * (1 / na + 1 / nb));
	if (na < MINIMO_PARA_COMPARAR || nb < MINIMO_PARA_COMPARAR || !ee || Math.abs(pa - pb) <= Z_95 * ee)
		return { direccion: "incierto", texto: "sin cambio claro" };
	const n = Math.abs(d);
	return { direccion: d > 0 ? "sube" : "baja", texto: `${n} ${n === 1 ? "punto" : "puntos"}` };
}

/** Días transcurridos de un periodo que puede ir a medias (hasta = ahora). */
export function diasTranscurridos(desde: string | null, hasta: string): number | null {
	if (!desde) return null;
	const d = (new Date(hasta).getTime() - new Date(desde).getTime()) / 86_400_000;
	return Number.isFinite(d) && d > 0 ? d : null;
}

/**
 * Mensaje de error para el panel, de usted (PQ-20). `restErrorMessage` de
 * lib/httpTimeout habla de tú porque lo comparte el chat del equipo.
 */
export function mensajeError(error: unknown, otro: string): string {
	if (isRestTimeoutError(error)) return "El servidor tardó demasiado en responder. Intente de nuevo.";
	if (isNetworkError(error)) {
		return "No hay conexión con ATLAS. Revise su conexión a internet e intente de nuevo.";
	}
	return error instanceof Error && error.message ? error.message : otro;
}

export const ETIQUETA_RESULTADO: Record<Resultado, string> = {
	con_fuente: "Respondió citando fuentes",
	// Un solo nombre para el grupo ("Sin respuesta segura") y el motivo como
	// subtipo, igual que en las cifras y el filtro (PQ-19).
	sin_evidencia: "Sin respuesta segura: no encontró fuente",
	sin_cita_valida: "Sin respuesta segura: cita no válida",
	sin_fuente_otro: "Sin respuesta segura: no citó fuentes",
	fuera_de_tema: "Fuera del tema de playas",
	pide_aclarar: "Pidió aclarar la pregunta",
	saludo: "Saludo, no era una pregunta",
	sin_respuesta: "No quedó respuesta guardada",
};

export const ETIQUETA_CALIFICACION: Record<Calificacion, string> = {
	util: "Le sirvió",
	no_util: "No le sirvió",
	neutra: "Le sirvió a medias",
};

function contar(n: number, uno: string, varios: string): string {
	return `${n} ${n === 1 ? uno : varios}`;
}

/**
 * Texto del resultado con sus fuentes: "Respondió citando 2 fuentes: 1 norma
 * y 1 sentencia". Una sentencia no es una norma (PQ-32).
 */
export function textoResultado(resultado: Resultado, fuentes?: number, sentencias = 0): string {
	if (resultado === "con_fuente" && fuentes) {
		const normas = fuentes - sentencias;
		const base = `Respondió citando ${contar(fuentes, "fuente", "fuentes")}`;
		if (!sentencias) return `${base}: ${contar(normas, "norma", "normas")}`;
		if (!normas) return `${base}: ${contar(sentencias, "sentencia", "sentencias")}`;
		return `${base}: ${contar(normas, "norma", "normas")} y ${contar(sentencias, "sentencia", "sentencias")}`;
	}
	return ETIQUETA_RESULTADO[resultado];
}

/** Quita las marcas internas de cita ("[doc1]") de una respuesta (PQ-33). */
export function sinMarcasDeCita(texto: string): string {
	return texto.replace(/\s?\[doc\d+\]/g, "");
}

const LARGOS: Record<number, string> = {
	1: "Muy corta",
	2: "Corta",
	3: "Adecuada",
	4: "Larga",
	5: "Muy larga",
};

/** Nota de largo (1 muy corta, 3 adecuada, 5 muy larga) en palabras. */
export function textoLargo(n: number): string {
	if (!n) return "—";
	if (Number.isInteger(n)) return LARGOS[n] ?? "—";
	if (n < 2.5) return "Tirando a corta";
	if (n <= 3.5) return "Adecuada";
	return "Tirando a larga";
}

/** "3.4" → "3,4 de 5" (PQ-37). */
export function deCinco(n: number): string {
	return `${decimal(n)} de 5`;
}

/** Enlace al detalle que recuerda los filtros para volver igual (PQ-22). */
export function enlaceConversacion(id: string, volver: string): string {
	const q = new URLSearchParams({ id });
	if (volver) q.set("volver", volver);
	return `/admin/conversacion?${q}`;
}

/** Corta un texto largo en la última palabra completa y agrega "…". */
export function recortar(texto: string, max = 280): string {
	if (texto.length <= max) return texto;
	const corte = texto.slice(0, max);
	const espacio = corte.lastIndexOf(" ");
	return `${(espacio > max * 0.6 ? corte.slice(0, espacio) : corte).trimEnd()}…`;
}

/** Tipo de documento citado → etiqueta corta. */
export function tipoDocumento(docType: string | null): string {
	return docType === "jurisprudencia" ? "Sentencia" : "Norma";
}
