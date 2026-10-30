/**
 * Referencia legible de una fuente (UX-01, parte que se puede hacer sin
 * cambiar el backend). Solo usa los campos que el backend ya manda en la
 * metadata del grupo/fragmento; si falta alguno, se omite, nunca se inventa.
 */
import type { DocType, SourceFragment, SourceGroup, SourceMetadata } from "@/lib/types";

export interface DatoFuente {
	etiqueta: string;
	valor: string;
}

function texto(meta: Record<string, unknown> | undefined, clave: string): string {
	const v = meta?.[clave];
	return typeof v === "string" ? v.trim() : "";
}

export function tipoDe(grupo: SourceGroup): DocType {
	const t = grupo.doc_type ?? (grupo.metadata as SourceMetadata | undefined)?.doc_type;
	return t === "normativa" ? "normativa" : "jurisprudencia";
}

/** Nombre del documento: la norma (normativa) o el título del grupo. */
export function nombreFuente(grupo: SourceGroup): string {
	if (tipoDe(grupo) === "normativa") return texto(grupo.metadata, "norma") || grupo.title || grupo.source;
	return grupo.title || grupo.source;
}

/**
 * Datos de identificación, en el orden en que se citan. Para un fragmento de
 * normativa, el artículo del fragmento tiene prioridad sobre el del grupo.
 */
export function datosFuente(grupo: SourceGroup, fragmento?: SourceFragment): DatoFuente[] {
	const g = grupo.metadata;
	const f = fragmento?.metadata;
	const pares: Array<[string, string]> =
		tipoDe(grupo) === "normativa"
			? [
					["Título", texto(f, "titulo") || texto(g, "titulo")],
					["Capítulo", texto(f, "capitulo") || texto(g, "capitulo")],
					["Artículo", texto(f, "articulo") || texto(g, "articulo")],
				]
			: [
					["Corporación", texto(g, "Corporación")],
					["Radicado", texto(g, "Radicado")],
					["Magistrado ponente", texto(g, "Magistrado ponente")],
					["Tema", texto(g, "Tema principal")],
				];
	return pares.filter(([, v]) => v).map(([etiqueta, valor]) => ({ etiqueta, valor }));
}

/** Referencia en una línea, para copiar y pegar (p. ej. en un escrito). */
export function referenciaTexto(grupo: SourceGroup, fragmento?: SourceFragment): string {
	const nombre = nombreFuente(grupo);
	const datos = datosFuente(grupo, fragmento).filter((d) => d.etiqueta !== "Tema");
	if (tipoDe(grupo) === "normativa") {
		const articulo = datos.find((d) => d.etiqueta === "Artículo");
		return articulo ? `${nombre}, artículo ${articulo.valor.replace(/^art[íi]culo\s*/i, "")}` : nombre;
	}
	const partes = [nombre, ...datos.filter((d) => !nombre.includes(d.valor)).map((d) =>
		d.etiqueta === "Radicado" ? `radicado ${d.valor}` : d.etiqueta === "Magistrado ponente" ? `M. P. ${d.valor}` : d.valor,
	)];
	return partes.join(", ");
}

/**
 * Copia texto al portapapeles. Usa la API moderna y, si no está (http sin
 * TLS, navegadores viejos), el método clásico con un textarea temporal.
 */
export async function copiarTexto(valor: string): Promise<boolean> {
	try {
		if (navigator.clipboard && window.isSecureContext) {
			await navigator.clipboard.writeText(valor);
			return true;
		}
	} catch {
		// cae al método clásico
	}
	try {
		const area = document.createElement("textarea");
		area.value = valor;
		area.setAttribute("readonly", "");
		area.style.position = "fixed";
		area.style.opacity = "0";
		document.body.appendChild(area);
		area.select();
		const ok = document.execCommand("copy");
		document.body.removeChild(area);
		return ok;
	} catch {
		return false;
	}
}
