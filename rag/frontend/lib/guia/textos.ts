/**
 * Textos fijos de las pantallas del flujo guiado que se pueden escuchar.
 * Son la fuente única para los botones "Escuchar" y para el script que
 * genera los audios grabados (scripts/generar-audios.mjs): si un texto
 * cambia aquí, hay que volver a generar su audio; mientras tanto el botón
 * usa la voz del dispositivo.
 */
import { PLAYAS, TEMAS, type Tema } from "@/lib/guia/temas";

export const TXT = {
	inicioTitulo: "¿Sobre qué es su pregunta?",
	inicioPista: "Toque la opción que más se parezca a su caso.",
	otraCaso: "¿Su caso no está aquí?",
	escribirBoton: "Escribir mi pregunta",
	pie: "ATLAS le explica, con palabras sencillas, lo que dicen las normas y los jueces de Colombia sobre las playas. No reemplaza a un abogado.",
	otraCosa: "Otra cosa: escribir mi pregunta",
	playaTitulo: "¿En qué playa?",
	playaPista: "Las reglas para vender cambian de una playa a otra.",
	otraPlaya: "Otra playa o no sé",
	escribirTitulo: "Escriba su pregunta",
	escribirPista: "Escríbala como se la contaría a un vecino. No importa la ortografía.",
	escribirEjemplo: "Vendo cocadas en El Rodadero y me quieren quitar el puesto. ¿Pueden hacerlo?",
	escribirVacio: "Escriba su pregunta antes de tocar «Preguntar».",
	esperaTitulo: "Buscando la respuesta",
	esperaTexto: "Estamos leyendo las normas y las sentencias. Puede tardar hasta un minuto.",
	sinSenal:
		"No hay señal de internet. Cuando tenga señal, toque «Intentar otra vez».",
	errorTitulo: "No pudimos traer la respuesta",
	errorRed:
		"No hay señal o el servidor no responde. Revise su internet y toque «Intentar otra vez».",
	errorOtro:
		"Hubo un problema al buscar la respuesta. Toque «Intentar otra vez». Si sigue pasando, avise a la persona que le ayuda con ATLAS.",
	entrarTitulo: "Entrar a ATLAS",
	entrarPista: "Escriba el correo y la contraseña que le dieron.",
} as const;

/** Mensajes según la etapa que informa el backend mientras se espera. */
export const ETAPAS: Record<string, string> = {
	enriching: "Leyendo su pregunta…",
	retrieving: "Buscando en las normas y las sentencias…",
	generating: "Escribiendo la respuesta…",
};

export function lecturaInicio(): string {
	return [TXT.inicioTitulo, TXT.inicioPista, ...TEMAS.map((t) => `${t.titulo}.`), TXT.otraCaso, `${TXT.escribirBoton}.`].join(
		"\n",
	);
}

export function lecturaTema(t: Tema): string {
	return [t.pantalla, ...t.opciones.map((o) => `${o.texto}.`), `${TXT.otraCosa}.`].join("\n");
}

export function lecturaPlaya(): string {
	return [TXT.playaTitulo, TXT.playaPista, ...PLAYAS.map((p) => `${p}.`), `${TXT.otraPlaya}.`].join("\n");
}

export function lecturaEscribir(): string {
	return [TXT.escribirTitulo, TXT.escribirPista].join("\n");
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
		lecturaEscribir(),
		lecturaEspera(),
		lecturaError("sin-senal"),
		lecturaError("red"),
		lecturaError("otro"),
	];
}
