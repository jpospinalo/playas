import type { SourceFragment, SourceGroup } from "@/lib/types";

/** Una fuente para mostrar, con las otras que traen el mismo párrafo. */
export interface FuenteUnica {
	grupo: SourceGroup;
	fragmento: SourceFragment;
	/** Otras fuentes (número y nombre) con el mismo párrafo: no se repiten. */
	tambien: Array<{ indice: number; nombre: string }>;
}

/** Desde este largo, un párrafo que empieza igual que otro se toma como el mismo. */
const MINIMO_PREFIJO = 200;

/** Texto comparable: sin mayúsculas, tildes, puntuación ni espacios repetidos. */
function clave(texto: string): string {
	return texto
		.normalize("NFD")
		.replace(/[̀-ͯ]/g, "")
		.toLowerCase()
		.replace(/[^a-z0-9ñ]+/g, " ")
		.trim();
}

function mismoParrafo(a: string, b: string): boolean {
	if (!a || !b) return false;
	if (a === b) return true;
	const [corto, largo] = a.length <= b.length ? [a, b] : [b, a];
	return corto.length >= MINIMO_PREFIJO && largo.startsWith(corto);
}

/**
 * Agrupa fragmentos que traen el mismo párrafo (pasa cuando la misma norma o
 * sentencia está dos veces en la base): se muestra la primera y las demás
 * quedan como "También aparece como fuente N". `canonica` lleva cada número
 * de fuente a la que sí se muestra, para que una cita a la repetida abra la
 * que quedó. No toca los datos: solo cómo se ven.
 */
export function agruparRepetidas(
	lista: Array<{ grupo: SourceGroup; fragmento: SourceFragment }>,
	nombre: (g: SourceGroup) => string,
): { unicas: FuenteUnica[]; canonica: Map<number, number> } {
	const unicas: Array<FuenteUnica & { _clave: string }> = [];
	const canonica = new Map<number, number>();
	for (const { grupo, fragmento } of lista) {
		const k = clave(fragmento.content);
		const igual = unicas.find((u) => mismoParrafo(u._clave, k));
		if (igual) {
			igual.tambien.push({ indice: fragmento.index, nombre: nombre(grupo) });
			canonica.set(fragmento.index, igual.fragmento.index);
		} else {
			unicas.push({ grupo, fragmento, tambien: [], _clave: k });
			canonica.set(fragmento.index, fragmento.index);
		}
	}
	return { unicas: unicas.map(({ _clave: _, ...u }) => u), canonica };
}
