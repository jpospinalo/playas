import { describe, expect, it } from "vitest";
import { datosFuente, nombreFuente, referenciaTexto } from "@/lib/referencia";
import type { SourceGroup } from "@/lib/types";

const norma: SourceGroup = {
	source: "decreto-2324.md",
	title: "Decreto 2324 de 1984 — por el cual se reorganiza la Dirección General Marítima",
	doc_type: "normativa",
	metadata: { doc_type: "normativa", norma: "Decreto 2324 de 1984", titulo: "TÍTULO VI", articulo: "166" },
	fragments: [{ index: 2, content: "Artículo 166…", metadata: { articulo: "Artículo 166" } }],
};

const sentencia: SourceGroup = {
	source: "AP-enciso.md",
	title: "Acción popular — Miguel Ángel Enciso vs. Distrito y otros",
	doc_type: "jurisprudencia",
	metadata: {
		doc_type: "jurisprudencia",
		"Corporación": "Consejo de Estado",
		Radicado: "47001-23-31-000-2005-00123-01(AP)",
		"Magistrado ponente": "María Claudia Rojas Lasso",
		"Tema principal": "Espacio público en playas",
	},
	fragments: [{ index: 4, content: "La Sala advierte…", metadata: {} }],
};

describe("referencia de una fuente (UX-01 con los datos actuales)", () => {
	it("normativa: nombre de la norma y artículo del fragmento", () => {
		expect(nombreFuente(norma)).toBe("Decreto 2324 de 1984");
		expect(referenciaTexto(norma, norma.fragments[0])).toBe("Decreto 2324 de 1984, artículo 166");
		expect(datosFuente(norma, norma.fragments[0]).map((d) => d.etiqueta)).toEqual(["Título", "Artículo"]);
	});

	it("jurisprudencia: corporación, radicado completo y ponente, sin cortar", () => {
		const ref = referenciaTexto(sentencia);
		expect(ref).toContain("Consejo de Estado");
		expect(ref).toContain("radicado 47001-23-31-000-2005-00123-01(AP)");
		expect(ref).toContain("M. P. María Claudia Rojas Lasso");
	});

	it("si faltan datos no inventa nada: queda solo el nombre", () => {
		const sinDatos: SourceGroup = { source: "x.md", title: "Sentencia sin metadatos", metadata: {}, fragments: [] };
		expect(referenciaTexto(sinDatos)).toBe("Sentencia sin metadatos");
		expect(datosFuente(sinDatos)).toEqual([]);
	});
});
