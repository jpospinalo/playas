/**
 * Pregunta enviada que todavía no tiene respuesta. Se guarda en la pestaña
 * (sessionStorage) para no perderla si la sesión se cierra a mitad de la
 * espera (401) o si la persona recarga la página: al volver, ATLAS ofrece
 * seguir con ella. Se borra al llegar la respuesta o al cancelar.
 */
export interface PreguntaPendiente {
	texto: string;
	envio: string;
	playa: string | null;
}

const CLAVE = "atlas:pregunta-pendiente";

export function guardarPendiente(p: PreguntaPendiente): void {
	try {
		window.sessionStorage.setItem(CLAVE, JSON.stringify(p));
	} catch {
		// Sin almacenamiento: solo se pierde esta comodidad.
	}
}

export function leerPendiente(): PreguntaPendiente | null {
	try {
		const crudo = window.sessionStorage.getItem(CLAVE);
		if (!crudo) return null;
		const p = JSON.parse(crudo) as Partial<PreguntaPendiente>;
		return typeof p.texto === "string" && typeof p.envio === "string"
			? { texto: p.texto, envio: p.envio, playa: typeof p.playa === "string" ? p.playa : null }
			: null;
	} catch {
		return null;
	}
}

export function borrarPendiente(): void {
	try {
		window.sessionStorage.removeItem(CLAVE);
	} catch {
		// nada que borrar
	}
}
