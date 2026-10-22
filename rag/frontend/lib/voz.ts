/**
 * Lectura en voz alta de ATLAS.
 *
 * 1. Si el texto es uno de los textos fijos de la interfaz y existe un audio
 *    grabado (public/audio/manifest.json, generado en local con un TTS libre),
 *    se reproduce ese audio: suena natural.
 * 2. Si no (respuestas del RAG, que cambian siempre), se usa la voz del
 *    dispositivo (speechSynthesis), eligiendo la mejor voz en español
 *    disponible, un poco más lenta y frase por frase, con una pausa corta.
 *
 * Una voz natural para las respuestas dinámicas necesitaría un servicio de
 * voz en el backend; queda fuera del alcance del front.
 */

export const VELOCIDAD = 0.9;
/** Pausa entre frases, en milisegundos. */
export const PAUSA_MS = 350;

// Orden de preferencia de idioma: español de Colombia y de la región primero.
const IDIOMAS = ["es-co", "es-mx", "es-us", "es-419", "es-ar", "es-cl", "es-pe", "es-ve", "es-es"];

// Pistas en el nombre de las voces de mejor calidad según el sistema:
// Edge/Windows ("Online (Natural)"), Chrome ("Google español"), Apple
// ("Premium"/"Mejorada"/"Enhanced", "Siri") y Android ("Neural", "network").
const PISTAS_CALIDAD: Array<[RegExp, number]> = [
	[/natural/i, 60],
	[/neural/i, 55],
	[/premium/i, 50],
	[/(enhanced|mejorad)/i, 45],
	[/siri/i, 40],
	[/online/i, 30],
	[/google/i, 25],
	[/network|red/i, 20],
	[/(paulina|m[oó]nica|sabina|marisol|juan|jorge|diego|francisca|carlos|isabela)/i, 10],
];

// Voces de Apple que suenan deliberadamente raras o de juguete.
const VOCES_RARAS = /(eddy|flo|grandma|grandpa|reed|rocko|sandy|shelley|bad news|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|albert|fred|junior|kathy|ralph)/i;

export interface VozInfo {
	name: string;
	lang: string;
	localService: boolean;
	default?: boolean;
}

/** Puntaje de una voz: más alto = mejor. Negativo = no es español. */
export function puntajeVoz(voz: VozInfo): number {
	const lang = voz.lang.toLowerCase().replace("_", "-");
	if (!lang.startsWith("es")) return -1;
	if (VOCES_RARAS.test(voz.name)) return 0;
	let puntos = 1;
	const i = IDIOMAS.findIndex((l) => lang.startsWith(l));
	// Hasta 18 puntos por idioma: es-CO vale más que es-ES.
	puntos += i === -1 ? 2 : (IDIOMAS.length - i) * 2;
	for (const [re, valor] of PISTAS_CALIDAD) {
		if (re.test(voz.name)) {
			puntos += valor;
			break;
		}
	}
	return puntos;
}

export function elegirVoz<T extends VozInfo>(voces: readonly T[]): T | null {
	let mejor: T | null = null;
	let mejorPuntaje = 0;
	for (const v of voces) {
		const p = puntajeVoz(v);
		if (p > mejorPuntaje) {
			mejor = v;
			mejorPuntaje = p;
		}
	}
	return mejor;
}

/** Corta un texto en frases para leerlas con una pausa entre una y otra. */
export function dividirEnFrases(texto: string): string[] {
	return texto
		.split(/\n+/)
		.flatMap((linea) => linea.match(/[^.!?¿¡]*[¿¡]?[^.!?]*[.!?]+|[^.!?]+$/g) ?? [])
		.map((f) => f.trim())
		.filter((f) => f.length > 0);
}

/** Normaliza un texto para buscarlo en el manifiesto de audios. */
export function claveAudio(texto: string): string {
	return texto
		.normalize("NFC")
		.replace(/\s+/g, " ")
		.trim()
		.toLowerCase();
}

let manifiesto: Promise<Record<string, string>> | null = null;
let manifiestoListo: Record<string, string> | null = null;

function cargarManifiesto(): Promise<Record<string, string>> {
	if (!manifiesto) {
		manifiesto = fetch("/audio/manifest.json")
			.then((r) => (r.ok ? (r.json() as Promise<Record<string, string>>) : ({} as Record<string, string>)))
			.then((datos) => {
				const porClave: Record<string, string> = {};
				for (const [texto, archivo] of Object.entries(datos)) porClave[claveAudio(texto)] = archivo;
				manifiestoListo = porClave;
				return porClave;
			})
			.catch(() => {
				manifiestoListo = {};
				return {};
			});
	}
	return manifiesto;
}

function vocesDisponibles(): Promise<SpeechSynthesisVoice[]> {
	const s = window.speechSynthesis;
	const ya = s.getVoices();
	if (ya.length > 0) return Promise.resolve(ya);
	// En Chrome las voces llegan después de la primera llamada.
	return new Promise((resolve) => {
		const listo = () => resolve(s.getVoices());
		s.addEventListener("voiceschanged", listo, { once: true });
		setTimeout(listo, 800);
	});
}

/**
 * Carga por adelantado el manifiesto y las voces. iOS y Chrome solo dejan
 * sonar audio cerca del toque de la persona: con todo cargado, `hablar()`
 * empieza sin esperas.
 */
export function prepararVoz(): void {
	void cargarManifiesto();
	if (puedeHablar()) void vocesDisponibles();
}

export function puedeHablar(): boolean {
	return typeof window !== "undefined" && "speechSynthesis" in window;
}

let audioActual: HTMLAudioElement | null = null;
let turno = 0;

/** Detiene cualquier lectura en curso (audio grabado o voz del dispositivo). */
export function detenerVoz(): void {
	turno += 1;
	if (audioActual) {
		audioActual.pause();
		audioActual = null;
	}
	if (puedeHablar()) window.speechSynthesis.cancel();
}

/**
 * Lee `texto` en voz alta. Resuelve cuando termina o se detiene; rechaza si
 * el dispositivo no puede leer en voz alta.
 */
export async function hablar(texto: string): Promise<void> {
	detenerVoz();
	const miTurno = turno;

	const archivos = manifiestoListo ?? (await cargarManifiesto());
	if (miTurno !== turno) return;
	const archivo = archivos[claveAudio(texto)];
	if (archivo) {
		const ok = await reproducir(`/audio/${archivo}`, () => miTurno !== turno);
		if (ok) return;
	}

	if (!puedeHablar()) throw new Error("sin-voz");
	const ya = window.speechSynthesis.getVoices();
	const voz = elegirVoz(ya.length > 0 ? ya : await vocesDisponibles());
	if (miTurno !== turno) return;
	const s = window.speechSynthesis;
	for (const frase of dividirEnFrases(texto)) {
		if (miTurno !== turno) return;
		await new Promise<void>((resolve) => {
			const u = new SpeechSynthesisUtterance(frase);
			u.lang = voz?.lang ?? "es-CO";
			if (voz) u.voice = voz;
			u.rate = VELOCIDAD;
			u.onend = () => resolve();
			u.onerror = () => resolve();
			s.speak(u);
		});
		if (miTurno !== turno) return;
		await new Promise((r) => setTimeout(r, PAUSA_MS));
	}
}

function reproducir(src: string, cancelado: () => boolean): Promise<boolean> {
	return new Promise((resolve) => {
		const audio = new Audio(src);
		audioActual = audio;
		audio.onended = () => resolve(true);
		audio.onpause = () => resolve(true);
		audio.onerror = () => resolve(false);
		audio.play().catch(() => resolve(cancelado()));
	});
}
