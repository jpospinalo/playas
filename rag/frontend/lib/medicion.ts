/**
 * Medición del tiempo hasta la primera respuesta útil (UX-02).
 *
 * El backend no envía la respuesta poco a poco: la valida completa y luego la
 * manda en trozos seguidos. Por eso "primera respuesta útil" = el momento en
 * que la persona ve la respuesta en pantalla. Se registran también los
 * tiempos de cada etapa que informa el backend (enriching, retrieving,
 * generating) y del primer trozo de texto.
 *
 * Solo se guardan tiempos y el resultado (ok/error/cancelada), nunca el texto
 * de la pregunta ni datos de la persona. Se guardan en este navegador
 * (localStorage, últimas 100) y se pueden ver o exportar desde la consola:
 *   atlasMediciones.resumen()   -> p50/p95 en milisegundos
 *   atlasMediciones.exportar()  -> JSON para pegar en una hoja
 *   atlasMediciones.borrar()
 */

export type Resultado = "ok" | "error" | "cancelada";

export interface Medicion {
	/** Fecha y hora de envío (ISO). */
	inicio: string;
	/** Milisegundos desde el envío hasta cada evento. */
	etapas: Record<string, number>;
	primerTexto?: number;
	respuesta?: number;
	resultado: Resultado;
}

const CLAVE = "atlas:mediciones";
const MAXIMO = 100;

let actual: { t0: number; inicio: string; etapas: Record<string, number>; primerTexto?: number } | null = null;

function ahora(): number {
	return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function marcarRendimiento(nombre: string): void {
	try {
		performance.mark(`atlas:${nombre}`);
	} catch {
		// Sin Performance API: solo se pierde la marca para las herramientas del navegador.
	}
}

export function iniciarMedicion(): void {
	actual = { t0: ahora(), inicio: new Date().toISOString(), etapas: {} };
	marcarRendimiento("envio");
}

export function marcarEtapa(etapa: string): void {
	if (!actual || etapa in actual.etapas) return;
	actual.etapas[etapa] = Math.round(ahora() - actual.t0);
	marcarRendimiento(`etapa-${etapa}`);
}

export function marcarPrimerTexto(): void {
	if (!actual || actual.primerTexto !== undefined) return;
	actual.primerTexto = Math.round(ahora() - actual.t0);
	marcarRendimiento("primer-texto");
}

export function terminarMedicion(resultado: Resultado): Medicion | null {
	if (!actual) return null;
	const m: Medicion = {
		inicio: actual.inicio,
		etapas: actual.etapas,
		primerTexto: actual.primerTexto,
		respuesta: resultado === "ok" ? Math.round(ahora() - actual.t0) : undefined,
		resultado,
	};
	actual = null;
	marcarRendimiento(`fin-${resultado}`);
	guardar(m);
	return m;
}

/** Milisegundos desde el envío de la pregunta en curso (o null si no hay). */
export function transcurrido(): number | null {
	return actual ? ahora() - actual.t0 : null;
}

export function leerMediciones(): Medicion[] {
	try {
		const crudo = window.localStorage.getItem(CLAVE);
		return crudo ? (JSON.parse(crudo) as Medicion[]) : [];
	} catch {
		return [];
	}
}

function guardar(m: Medicion): void {
	try {
		const lista = [...leerMediciones(), m].slice(-MAXIMO);
		window.localStorage.setItem(CLAVE, JSON.stringify(lista));
	} catch {
		// Sin almacenamiento: la medición de esta pregunta se pierde.
	}
}

/** Percentil por el método del rango más cercano (sin interpolar). */
export function percentil(valores: number[], p: number): number | null {
	if (valores.length === 0) return null;
	const orden = [...valores].sort((a, b) => a - b);
	const i = Math.min(orden.length - 1, Math.max(0, Math.ceil((p / 100) * orden.length) - 1));
	return orden[i];
}

export function resumen(lista: Medicion[] = leerMediciones()) {
	const ok = lista.filter((m) => m.resultado === "ok");
	const respuestas = ok.map((m) => m.respuesta).filter((v): v is number => typeof v === "number");
	const primeros = ok.map((m) => m.primerTexto).filter((v): v is number => typeof v === "number");
	return {
		preguntas: lista.length,
		ok: ok.length,
		errores: lista.filter((m) => m.resultado === "error").length,
		canceladas: lista.filter((m) => m.resultado === "cancelada").length,
		respuestaUtil_p50_ms: percentil(respuestas, 50),
		respuestaUtil_p95_ms: percentil(respuestas, 95),
		primerTexto_p50_ms: percentil(primeros, 50),
		primerTexto_p95_ms: percentil(primeros, 95),
	};
}

/** Expone las funciones en la consola del navegador (para el equipo). */
export function exponerEnConsola(): void {
	if (typeof window === "undefined") return;
	(window as unknown as { atlasMediciones?: unknown }).atlasMediciones = {
		resumen: () => resumen(),
		exportar: () => JSON.stringify(leerMediciones(), null, 2),
		borrar: () => {
			try {
				window.localStorage.removeItem(CLAVE);
			} catch {
				// nada que borrar
			}
		},
	};
}
