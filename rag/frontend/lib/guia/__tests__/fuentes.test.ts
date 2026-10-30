import { describe, expect, it } from "vitest";
import { agruparRepetidas } from "@/lib/guia/fuentes";
import type { SourceGroup } from "@/lib/types";

const PARRAFO =
	"Las playas, los terrenos de bajamar y las aguas marítimas son bienes de uso público, por tanto intransferibles a cualquier título a los particulares, quienes solo podrán obtener concesiones, permisos o licencias para su uso y goce de acuerdo con la ley.";

function fuente(n: number, titulo: string, contenido: string) {
	const grupo: SourceGroup = {
		source: `${titulo}.md`,
		title: titulo,
		doc_type: "jurisprudencia",
		metadata: {},
		fragments: [{ index: n, content: contenido, metadata: {} }],
	};
	return { grupo, fragmento: grupo.fragments[0] };
}

const nombre = (g: SourceGroup) => g.title ?? g.source;

describe("agruparRepetidas: fuentes con el mismo párrafo", () => {
	it("muestra una y anota las demás; la cita a la repetida va a la que quedó", () => {
		const { unicas, canonica } = agruparRepetidas(
			[
				fuente(1, "Consulta 2010", PARRAFO),
				// Mismo párrafo con otro espaciado, mayúsculas y puntuación.
				fuente(2, "Sentencia 2016", `  ${PARRAFO.toUpperCase().replace(/,/g, " ,")}  `),
				fuente(3, "Decreto 2324", "Artículo 166. Otra cosa distinta."),
			],
			nombre,
		);
		expect(unicas.map((u) => u.fragmento.index)).toEqual([1, 3]);
		expect(unicas[0].tambien).toEqual([{ indice: 2, nombre: "Sentencia 2016" }]);
		expect(canonica.get(2)).toBe(1);
		expect(canonica.get(3)).toBe(3);
	});

	it("un párrafo largo que empieza igual que otro más largo cuenta como el mismo", () => {
		const { unicas } = agruparRepetidas(
			[fuente(1, "A", PARRAFO), fuente(2, "B", `${PARRAFO} Y además sigue con otra frase.`)],
			nombre,
		);
		expect(unicas).toHaveLength(1);
	});

	it("textos cortos parecidos no se juntan", () => {
		const { unicas } = agruparRepetidas([fuente(1, "A", "Artículo 1."), fuente(2, "B", "Artículo 1. Además…")], nombre);
		expect(unicas).toHaveLength(2);
	});
});
