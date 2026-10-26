/**
 * Textos fijos de las pantallas del flujo guiado que se pueden escuchar.
 * Son la fuente única para los botones "Escuchar" y para el script que
 * genera los audios grabados (scripts/generar-audios.mjs): si un texto
 * cambia aquí, hay que volver a generar su audio; mientras tanto el botón
 * usa la voz del dispositivo.
 */
import { PLAYAS, TEMAS, type Tema } from "@/lib/guia/temas";
import { lecturaRespuesta, respuestaFija } from "@/lib/guia/respuesta";

export const TXT = {
	inicioTitulo: "¿Qué quiere saber sobre las playas?",
	cajaPista: "Escriba su pregunta sobre las playas…",
	/** Cómo lee "Escuchar" la caja del inicio (la pista sin los puntos suspensivos). */
	cajaLectura: "Escriba su pregunta sobre las playas y toque «Preguntar».",
	inicioNota: "Escríbala como se la contaría a un vecino. Pruebe con:",
	guiarTitulo: "¿Prefiere que lo guiemos?",
	guiarPista: "Elija el tema que más se parezca a su caso y le vamos preguntando paso a paso.",
	pie: "ATLAS le explica, con palabras sencillas, lo que dicen las normas y los jueces de Colombia sobre las playas. No reemplaza a un abogado.",
	otraCosa: "Otra cosa: escribir mi pregunta",
	playaTitulo: "¿En qué playa?",
	playaPista: "Las reglas para vender cambian de una playa a otra.",
	otraPlaya: "Otra playa o no sé",
	escribirVacio: "Escriba su pregunta antes de tocar «Preguntar».",
	escribirCorta: "Su pregunta es muy corta. Cuéntenos un poco más, por ejemplo qué pasó y en qué playa.",
	esperaTitulo: "Buscando la respuesta",
	esperaTexto: "Estamos leyendo las normas y las sentencias. Puede tardar hasta un minuto.",
	sinSenal:
		"No hay señal de internet. Cuando tenga señal, toque «Intentar otra vez».",
	errorTitulo: "No pudimos traer la respuesta",
	errorRed:
		"No hay señal o el servidor no responde. Revise su internet y toque «Intentar otra vez».",
	errorOtro:
		"Hubo un problema al buscar la respuesta. Toque «Intentar otra vez». Si sigue pasando, vuelva a intentarlo en unos minutos.",
	entrarTitulo: "Entrar a ATLAS",
	entrarPista: "Escriba el correo y la contraseña que le dieron.",
} as const;

/** Mensajes según la etapa que informa el backend mientras se espera. */
export const ETAPAS: Record<string, string> = {
	enriching: "Leyendo su pregunta…",
	retrieving: "Buscando en las normas y las sentencias…",
	generating: "Escribiendo la respuesta…",
};

/** Ejemplos tocables del inicio: llenan la caja, no envían. */
export const EJEMPLOS = ["¿Me pueden cobrar por entrar a la playa?", "¿Puedo vender en El Rodadero?"] as const;

export function lecturaInicio(): string {
	return [
		TXT.inicioTitulo,
		TXT.cajaLectura,
		TXT.guiarTitulo,
		TXT.guiarPista,
		...TEMAS.map((t) => `${t.titulo}.`),
	].join("\n");
}

export function lecturaTema(t: Tema): string {
	return [t.pantalla, ...t.opciones.map((o) => `${o.texto}.`), `${TXT.otraCosa}.`].join("\n");
}

export function lecturaPlaya(): string {
	return [TXT.playaTitulo, TXT.playaPista, ...PLAYAS.map((p) => `${p}.`), `${TXT.otraPlaya}.`].join("\n");
}

export function lecturaEspera(): string {
	return [TXT.esperaTitulo, TXT.esperaTexto].join("\n");
}

export type TipoError = "sin-senal" | "red" | "otro";

export function mensajeError(tipo: TipoError): string {
	return tipo === "sin-senal" ? TXT.sinSenal : tipo === "red" ? TXT.errorRed : TXT.errorOtro;
}

export function lecturaError(tipo: TipoError): string {
	return [TXT.errorTitulo, mensajeError(tipo)].join("\n");
}

/** Todos los textos con audio grabado (para el script que los genera). */
export function textosConAudio(): string[] {
	return [
		lecturaInicio(),
		...TEMAS.map(lecturaTema),
		lecturaPlaya(),
		lecturaEspera(),
		lecturaError("sin-senal"),
		lecturaError("red"),
		lecturaError("otro"),
		// Mensajes fijos del backend, ya en palabras sencillas (ver respuesta.ts).
		...(["fuera-de-tema", "aclaracion", "conversacion", "sin-evidencia"] as const).map((t) =>
			lecturaRespuesta(respuestaFija(t)),
		),
	];
}
