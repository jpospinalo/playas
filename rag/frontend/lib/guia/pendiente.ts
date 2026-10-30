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
	/** Si era un seguimiento: la conversación a la que pertenece (QA-F03). */
	conversationId?: string | null;
	threadId?: string | null;
}

/**
 * La pregunta se guarda con el id de quien la hizo y solo se ofrece de nuevo a
 * esa misma persona: en un celular compartido, si entra otra, se borra (E2-19).
 */
interface Guardada extends PreguntaPendiente {
	usuario: string;
}

const CLAVE = "atlas:pregunta-pendiente";

export function guardarPendiente(p: PreguntaPendiente, usuario: string): void {
	try {
		const g: Guardada = { ...p, usuario };
		window.sessionStorage.setItem(CLAVE, JSON.stringify(g));
	} catch {
		// Sin almacenamiento: solo se pierde esta comodidad.
	}
}

/** Pregunta pendiente de `usuario`. Si era de otra persona, la borra y devuelve null. */
export function leerPendiente(usuario: string): PreguntaPendiente | null {
	try {
		const crudo = window.sessionStorage.getItem(CLAVE);
		if (!crudo) return null;
		const p = JSON.parse(crudo) as Partial<Guardada>;
		if (p.usuario !== usuario) {
			window.sessionStorage.removeItem(CLAVE);
			return null;
		}
		return typeof p.texto === "string" && typeof p.envio === "string"
			? {
					texto: p.texto,
					envio: p.envio,
					playa: typeof p.playa === "string" ? p.playa : null,
					conversationId: typeof p.conversationId === "string" ? p.conversationId : null,
					threadId: typeof p.threadId === "string" ? p.threadId : null,
				}
			: null;
	} catch {
		return null;
	}
}

/** Hay una pregunta pendiente (de cualquier persona), sin revelar cuál. */
export function hayPendiente(): boolean {
	try {
		return window.sessionStorage.getItem(CLAVE) !== null;
	} catch {
		return false;
	}
}

export function borrarPendiente(): void {
	try {
		window.sessionStorage.removeItem(CLAVE);
	} catch {
		// nada que borrar
	}
}
