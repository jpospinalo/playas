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
// Saludo fijo de agent.py (_conversation_response).
const SALUDO_BACKEND = "Hola. ¿Cuál es tu consulta?";

/**
 * Versión en palabras sencillas y de usted de los mensajes FIJOS del
 * backend (no son contenido legal: son avisos del sistema, siempre iguales).
 * El backend los escribe con "consulta", "corpus" y de tú; aquí se dicen
 * como en el resto de ATLAS.
 */
export const TEXTO_FUERA_DE_TEMA =
	"ATLAS solo responde preguntas sobre las playas, el mar y la costa de Colombia: entrar, pescar, vender, hoteles, lanchas y construcciones. Si su pregunta sí tiene que ver con la playa, escríbala otra vez diciendo en qué playa pasó.";
export const TEXTO_ACLARACION =
	"Cuéntenos un poco más: en qué playa pasó, qué estaba haciendo y quién se lo impidió o se lo pidió.";
export const TEXTO_CONVERSACION =
	"Puede preguntar sobre entrar a la playa, pescar, vender, hoteles, lanchas y construcciones cerca del mar.";
export const TEXTO_SIN_EVIDENCIA =
	"No encontramos normas o sentencias que respondan su pregunta con seguridad. Preferimos no adivinar.";
export const TITULO_OTRA_FORMA = "Cómo preguntar de otra forma";
export const TEXTO_OTRA_FORMA =
	"Diga qué estaba haciendo, en qué playa pasó y quién se lo impidió o se lo pidió. Por ejemplo: «Vendo cocadas en El Rodadero y la Policía me quiere quitar el puesto».";

/** Respuesta ya ordenada para cada mensaje fijo del backend. */
export function respuestaFija(tipo: Exclude<TipoRespuesta, "normal">): RespuestaOrdenada {
	switch (tipo) {
		case "fuera-de-tema":
			return { tipo, titulo: TITULO_FUERA_DE_TEMA, resumen: TEXTO_FUERA_DE_TEMA, secciones: [] };
		case "aclaracion":
			return { tipo, titulo: TITULO_ACLARACION, resumen: TEXTO_ACLARACION, secciones: [] };
		case "conversacion":
			return { tipo, titulo: TITULO_CONVERSACION, resumen: TEXTO_CONVERSACION, secciones: [] };
		case "sin-evidencia":
			return {
				tipo,
				titulo: TITULO_SIN_EVIDENCIA,
				resumen: TEXTO_SIN_EVIDENCIA,
				secciones: [{ titulo: TITULO_OTRA_FORMA, cuerpo: TEXTO_OTRA_FORMA, clase: "normal" }],
			};
	}
}

/**
 * Títulos técnicos que pone el backend → títulos en palabras sencillas.
 * Solo cambia el título; el contenido de la sección queda igual.
 */
const TITULOS_SENCILLOS: Array<[RegExp, string]> = [
	[/^(desarrollo jurídico|qué dice la norma|que dice la norma|marco normativo|fundamento normativo)$/i, "Lo que dice la ley"],
	[/^(límites de evidencia|limites de evidencia)$/i, "Tenga en cuenta"],
	[/^síntesis jurisprudencial$/i, "Lo que han dicho los jueces"],
	[/^lo que sí puede afirmarse$/i, "Lo que sí se puede decir"],
	[/^(autoridad(es)? competente(s)?)$/i, "A quién acudir"],
];

function tituloSencillo(titulo: string): string {
	for (const [re, nuevo] of TITULOS_SENCILLOS) if (re.test(titulo)) return nuevo;
	return titulo;
}

/** Texto que se lee en voz alta para una respuesta ordenada. */
export function lecturaRespuesta(r: RespuestaOrdenada): string {
	const partes = [r.titulo, r.resumen];
	for (const s of r.secciones) partes.push(s.titulo, s.cuerpo);
	return partes
		.map((p) => markdownATexto(p))
		.filter(Boolean)
		.join("\n");
}

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
		// HTML que mande el backend: no se lee (ni el contenido de <script>).
		.replace(/<(script|style|iframe|object|embed|noscript)\b[\s\S]*?<\/\1\s*>/gi, "")
		.replace(/<[^>]+>/g, "")
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

	if (limpio.startsWith(INICIO_FUERA_DE_TEMA)) return respuestaFija("fuera-de-tema");
	if (limpio.startsWith(INICIO_ACLARACION)) return respuestaFija("aclaracion");
	if (limpio.startsWith(INICIO_CONVERSACION) || limpio === SALUDO_BACKEND) return respuestaFija("conversacion");

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
	// Se reemplazan "Situación", "Motivo" y "Cómo reformular" (avisos del
	// sistema) por el texto sencillo; se conserva lo demás (p. ej. "Lo que sí
	// puede afirmarse", que sí es contenido con citas).
	if (secciones[0] && /^situación$/i.test(secciones[0].titulo) && preambulo.join("").trim() === "") {
		const base = respuestaFija("sin-evidencia");
		const contenido = secciones
			.slice(1)
			.filter((s) => !/^(motivo|cómo reformular|como reformular)$/i.test(s.titulo) && s.cuerpo.trim());
		return { ...base, secciones: [...contenido, ...base.secciones] };
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
	// La clase sale del título original; el título que se ve, del sencillo.
	return { titulo: tituloSencillo(s.titulo), cuerpo: s.lineas.join("\n").trim(), clase: clasificar(s.titulo) };
}
