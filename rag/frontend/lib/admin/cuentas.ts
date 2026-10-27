/**
 * Cuentas del ejercicio de validación: participantes (con número y tipo de
 * usuario de playa), evaluadores (con sede), comité y administradores.
 * Backend: `rag/backend/rag/api/routes/participantes.py` (solo admin).
 */

import { API_URL } from "@/lib/config";
import { withRestTimeout } from "@/lib/httpTimeout";
import { throwIfSessionExpired } from "@/lib/api";
import { expireAuthSession, getToken } from "@/lib/auth";

export type Rol = "user" | "evaluador" | "comite" | "admin";
export type Sede = "Santa Marta" | "Barranquilla";

export const TIPOS_PLAYA = [
	{ id: 1, nombre: "Residentes", largo: "Residentes, habitantes y propietarios de predios o viviendas costeras" },
	{ id: 2, nombre: "Pescadores", largo: "Pescadores" },
	{ id: 3, nombre: "Comerciantes", largo: "Comerciantes y trabajadores de playa" },
	{ id: 4, nombre: "Empresarios", largo: "Hoteleros, restauranteros y empresas de servicios vinculados a la playa" },
	{ id: 5, nombre: "Turistas", largo: "Turistas y visitantes" },
] as const;

export const ROLES: { valor: Rol; texto: string }[] = [
	{ valor: "user", texto: "Participante" },
	{ valor: "evaluador", texto: "Evaluador" },
	{ valor: "comite", texto: "Comité" },
	{ valor: "admin", texto: "Administrador" },
];

export const SEDES: Sede[] = ["Santa Marta", "Barranquilla"];

export function textoRol(rol: string): string {
	if (rol === "super-admin") return "Administrador";
	return ROLES.find((r) => r.valor === rol)?.texto ?? rol;
}

export function nombreTipo(id: number | null | undefined): string {
	return TIPOS_PLAYA.find((t) => t.id === id)?.nombre ?? "—";
}

export interface Cuenta {
	uid: string;
	nombre: string | null;
	correo: string;
	rol: string;
	codigo: string | null;
	tipo_playa: number | null;
	tipo_playa_nombre: string | null;
	sede: string | null;
	organizacion?: string | null;
	preguntas: number;
	creada: string;
	/** false = desactivada: no entra, pero su historial se conserva. */
	activa?: boolean;
	/** Comité: "juridico" (valida las evaluaciones de su sede) o "costero". */
	validacion?: "juridico" | "costero" | null;
	/** T7: cuenta de práctica (no cuenta para nada). */
	practica?: boolean;
}

export interface PersonaNueva {
	nombre: string;
	rol: Rol;
	tipo_playa?: number;
	sede?: Sede;
	codigo?: string;
	organizacion?: string;
}

export interface Credencial {
	uid: string;
	nombre: string;
	rol: string;
	codigo: string | null;
	tipo_playa: number | null;
	sede: string | null;
	correo: string;
	clave: string;
}

async function llamar<T>(ruta: string, init: RequestInit = {}): Promise<T> {
	const t = getToken();
	if (!t) {
		expireAuthSession(null);
		throw new Error("Su sesión se cerró. Vuelva a entrar.");
	}
	const res = await fetch(`${API_URL}/api/admin/participantes${ruta}`, {
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

export function listarCuentas(): Promise<{ items: Cuenta[]; total: number }> {
	return llamar("");
}

export function crearLote(personas: PersonaNueva[]): Promise<{ creadas: Credencial[] }> {
	return llamar("/lote", { method: "POST", body: JSON.stringify({ personas }) });
}

export function cambiarCuenta(
	uid: string,
	cambios: {
		rol?: Rol;
		tipo_playa?: number;
		sede?: Sede;
		nombre?: string;
		activa?: boolean;
		validacion?: "juridico" | "costero" | "ninguna";
		practica?: boolean;
	},
): Promise<Cuenta> {
	return llamar(`/${encodeURIComponent(uid)}`, { method: "PATCH", body: JSON.stringify(cambios) });
}

export interface EntradaAuditoria {
	fecha: string;
	quien: string;
	accion: string;
	texto: string;
	objetivo: string | null;
	detalle: Record<string, unknown>;
}

/** Historial de acciones de administración y del comité (quién, qué, cuándo). */
export async function pedirAuditoria(limite = 100): Promise<{ items: EntradaAuditoria[]; total: number }> {
	const t = getToken();
	if (!t) {
		expireAuthSession(null);
		throw new Error("Su sesión se cerró. Vuelva a entrar.");
	}
	const res = await fetch(`${API_URL}/api/admin/auditoria?limite=${limite}`, {
		headers: { Authorization: `Bearer ${t}` },
		signal: withRestTimeout(),
	});
	await throwIfSessionExpired(res, t);
	if (!res.ok) throw new Error(`El servidor respondió con un error (${res.status}).`);
	return (await res.json()) as { items: EntradaAuditoria[]; total: number };
}

/** Detalle legible de una entrada: qué cambió o cuántas fueron. */
export function detalleAuditoria(e: EntradaAuditoria): string {
	const d = e.detalle ?? {};
	const partes: string[] = [];
	if (typeof d.cantidad === "number") partes.push(`${d.cantidad} en total`);
	if (typeof d.id_pregunta === "number") partes.push(`pregunta ${d.id_pregunta}`);
	if (typeof d.nivel === "string") partes.push(`nivel ${d.nivel}`);
	const cambios = d.cambios as Record<string, [unknown, unknown]> | undefined;
	if (cambios) {
		for (const [campo, [antes, despues]] of Object.entries(cambios)) {
			partes.push(`${campo.replace("_", " ")}: ${antes ?? "—"} → ${despues ?? "—"}`);
		}
	}
	return partes.join("; ");
}

export function nuevaClave(uid: string): Promise<{ correo: string; clave: string }> {
	return llamar(`/${encodeURIComponent(uid)}/clave`, { method: "POST" });
}

/**
 * Lee la lista pegada para crear cuentas: una persona por renglón,
 * "Nombre; tipo; organización" (tipo = número 1-5 o el nombre, p. ej.
 * "Pescadores"; la organización, institución o asociación es opcional).
 * Acepta tabulador (copiado de Excel). Devuelve las personas y los errores
 * por renglón.
 */
export function leerLista(
	texto: string,
	rol: Rol,
	sede?: Sede,
): { personas: PersonaNueva[]; errores: string[] } {
	const personas: PersonaNueva[] = [];
	const errores: string[] = [];
	texto
		.split(/\r?\n/)
		.map((l) => l.trim())
		.forEach((linea, i) => {
			if (!linea) return;
			const [nombreCrudo, tipoCrudo = "", orgCruda = ""] = linea.split(/[;\t]/).map((x) => x.trim());
			const nombre = nombreCrudo ?? "";
			if (!nombre) {
				errores.push(`Renglón ${i + 1}: falta el nombre.`);
				return;
			}
			if (rol !== "user") {
				personas.push({ nombre, rol, ...(rol === "evaluador" && sede ? { sede } : {}) });
				return;
			}
			const n = Number(tipoCrudo);
			const tipo =
				Number.isInteger(n) && n >= 1 && n <= 5
					? n
					: TIPOS_PLAYA.find((t) =>
							t.nombre.toLowerCase().startsWith(tipoCrudo.toLowerCase().slice(0, 5)) && tipoCrudo.length >= 4,
						)?.id;
			if (!tipo) {
				// PQ-50: no es lo mismo no escribir el tipo que escribir uno que no existe.
				errores.push(
					tipoCrudo
						? `Renglón ${i + 1} (${nombre}): el tipo «${tipoCrudo}» no existe; use 1 a 5 o su nombre (p. ej. Pescadores).`
						: `Renglón ${i + 1} (${nombre}): falta el tipo de usuario de playa (1 a 5).`,
				);
				return;
			}
			personas.push({ nombre, rol, tipo_playa: tipo, ...(orgCruda ? { organizacion: orgCruda } : {}) });
		});
	return { personas, errores };
}
