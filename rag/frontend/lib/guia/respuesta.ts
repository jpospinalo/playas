/**
 * Ordena la respuesta del RAG (Markdown con citas `[docN]`) en las partes
 * del diseño v3, SIN inventar contenido: solo se reconocen las secciones que
 * el backend ya trae y se les da el estilo que corresponde. Lo que no se
 * reconoce se muestra tal cual, como Markdown limpio.
 */

export type ClaseSeccion = "normal" | "ojo" | "acudir";

export interface SeccionRespuesta {
	/** Título tal como lo escribió el backend (sin asteriscos ni dos puntos). */
	titulo: string;
	/** Markdown del contenido de la sección. */
	cuerpo: string;
	clase: ClaseSeccion;
}

export type TipoRespuesta =
	| "normal"
	| "sin-evidencia"
	| "fuera-de-tema"
	| "aclaracion"
	| "conversacion";

export interface RespuestaOrdenada {
	tipo: TipoRespuesta;
	/** Título grande de la pantalla. Puede traer citas `[docN]`. */
	titulo: string;
	/** Markdown que acompaña al título dentro del bloque azul (puede ser vacío). */
	resumen: string;
	secciones: SeccionRespuesta[];
}

/** Títulos fijos (de la interfaz, no del backend) para cada caso. */
export const TITULO_GENERICO = "Esto es lo que encontramos";
export const TITULO_SIN_EVIDENCIA = "No encontramos una respuesta segura";
export const TITULO_FUERA_DE_TEMA = "Esa pregunta no es sobre las playas";
export const TITULO_ACLARACION = "Necesitamos un poco más de información";
export const TITULO_CONVERSACION = "ATLAS responde preguntas sobre las playas";

/** Una frase cabe como título grande si no pasa de este largo. */
const MAX_TITULO = 90;

// Inicios fijos de las respuestas sin recuperación del backend
// (rag/backend/rag/core/agent.py: _OUT_OF_SCOPE_RESPONSE, _CLARIFICATION_RESPONSE,
// _CONVERSATION_RESPONSE). Si cambian allá, aquí solo se pierde el título
// especial: la respuesta igual se muestra completa.
const INICIO_FUERA_DE_TEMA = "La consulta está fuera del ámbito";
const INICIO_ACLARACION = "La consulta podría estar dentro del ámbito";
const INICIO_CONVERSACION = "Puedo responder consultas";

const RE_OJO = /^(tenga en cuenta|ten en cuenta|importante|límites de evidencia|limites de evidencia|advertencia|ojo)\b/i;
const RE_ACUDIR = /(a quién acudir|a quien acudir|autoridad(es)? competente|ante quién|dónde acudir)/i;
const RE_RESUMEN = /^(respuesta corta|respuesta|en resumen|resumen|criterio principal|conclusión|conclusion)$/i;

/** Quita las citas `[docN]` (para leer en voz alta o medir una frase). */
export function quitarCitas(texto: string): string {
	return texto
		.replace(/\s*\[doc\d+\]/gi, "")
		.replace(/[ \t]+([.,;:])/g, "$1");
}

/** Texto plano a partir de Markdown sencillo (para la voz). */
export function markdownATexto(md: string): string {
	return quitarCitas(md)
		.replace(/^\s*\|?\s*:?-{3,}.*$/gm, "")
		.replace(/\|/g, ", ")
		.replace(/^\s*#+\s*/gm, "")
		.replace(/\*\*([^*]+)\*\*/g, "$1")
		.replace(/\*([^*]+)\*/g, "$1")
		.replace(/^\s*[-*+]\s+/gm, "")
		.replace(/^\s*(\d+)\.\s+/gm, "$1. ")
		.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
		.replace(/[ \t]+/g, " ")
		.replace(/\n{2,}/g, "\n")
		.trim();
}

/**
 * Reconoce una línea que abre sección:
 *  - `**Título**` sola en la línea (opcionalmente con texto en itálica después),
 *  - `**Título:** texto…` (el texto queda como primera línea del cuerpo),
 *  - `## Título`.
 */
function abreSeccion(linea: string): { titulo: string; resto: string } | null {
	const h = /^#{1,4}\s+(.+?)\s*$/.exec(linea);
	if (h) return { titulo: limpiarTitulo(h[1]), resto: "" };
	const conDosPuntos = /^\*\*([^*\n]{1,80}?):\*\*\s*(.*)$/.exec(linea);
	if (conDosPuntos) return { titulo: limpiarTitulo(conDosPuntos[1]), resto: conDosPuntos[2] };
	const sola = /^\*\*([^*\n]{1,80})\*\*\s*(\*\([^)]*\)\*)?\s*:?\s*$/.exec(linea);
	if (sola) return { titulo: limpiarTitulo(sola[1]), resto: "" };
	return null;
}

function limpiarTitulo(t: string): string {
	return t.replace(/[*_]/g, "").replace(/[:\s]+$/, "").trim();
}

function clasificar(titulo: string): ClaseSeccion {
	if (RE_OJO.test(titulo)) return "ojo";
	if (RE_ACUDIR.test(titulo)) return "acudir";
	return "normal";
}

/** Separa la primera frase (para el título grande) del resto del párrafo. */
function primeraFrase(md: string): { frase: string; resto: string } | null {
	const parrafo = md.trim().split(/\n\s*\n/)[0] ?? "";
	// Solo si el primer bloque es un párrafo (no lista ni tabla).
	if (!parrafo || /^\s*([-*+]|\d+\.|\|)/.test(parrafo)) return null;
	const m = /^([\s\S]+?[.!?])(\s+|$)/.exec(parrafo);
	if (!m) return null;
	// La frase conserva sus citas `[docN]` (se muestran como "fuente N").
	const frase = m[1].trim().replace(/\*\*/g, "");
	const plano = quitarCitas(frase);
	if (plano.length > MAX_TITULO || plano.length < 2) return null;
	const resto = md.trim().slice(m[0].length).trim();
	return { frase, resto };
}

export function ordenarRespuesta(texto: string): RespuestaOrdenada {
	const limpio = texto.replace(/\r\n?/g, "\n").trim();

	if (limpio.startsWith(INICIO_FUERA_DE_TEMA)) {
		return { tipo: "fuera-de-tema", titulo: TITULO_FUERA_DE_TEMA, resumen: limpio, secciones: [] };
	}
	if (limpio.startsWith(INICIO_ACLARACION)) {
		return { tipo: "aclaracion", titulo: TITULO_ACLARACION, resumen: limpio, secciones: [] };
	}
	if (limpio.startsWith(INICIO_CONVERSACION)) {
		return { tipo: "conversacion", titulo: TITULO_CONVERSACION, resumen: limpio, secciones: [] };
	}

	// Corta el texto en: preámbulo (antes de la primera sección) + secciones.
	const lineas = limpio.split("\n");
	let preambulo: string[] = [];
	const secciones: SeccionRespuesta[] = [];
	let actual: { titulo: string; lineas: string[] } | null = null;
	for (const linea of lineas) {
		const abre = abreSeccion(linea.trim());
		if (abre) {
			if (actual) secciones.push(cerrar(actual));
			actual = { titulo: abre.titulo, lineas: abre.resto ? [abre.resto] : [] };
			continue;
		}
		if (actual) actual.lineas.push(linea);
		else preambulo.push(linea);
	}
	if (actual) secciones.push(cerrar(actual));

	// Respuesta fija de "evidencia insuficiente" (o la que generó el LLM con
	// el mismo formato): empieza con **Situación:**.
	if (secciones[0] && /^situación$/i.test(secciones[0].titulo) && preambulo.join("").trim() === "") {
		const [situacion, ...resto] = secciones;
		return {
			tipo: "sin-evidencia",
			titulo: TITULO_SIN_EVIDENCIA,
			resumen: situacion.cuerpo,
			secciones: resto,
		};
	}

	// El resumen sale del preámbulo o, si no hay, de una primera sección tipo
	// "Respuesta corta" / "Criterio principal".
	let resumen = preambulo.join("\n").trim();
	if (!resumen && secciones[0] && RE_RESUMEN.test(secciones[0].titulo)) {
		resumen = secciones.shift()!.cuerpo;
	}
	preambulo = [];

	const frase = resumen ? primeraFrase(resumen) : null;
	if (frase) {
		return { tipo: "normal", titulo: frase.frase, resumen: frase.resto, secciones };
	}
	return { tipo: "normal", titulo: TITULO_GENERICO, resumen, secciones };
}

function cerrar(s: { titulo: string; lineas: string[] }): SeccionRespuesta {
	return { titulo: s.titulo, cuerpo: s.lineas.join("\n").trim(), clase: clasificar(s.titulo) };
}
