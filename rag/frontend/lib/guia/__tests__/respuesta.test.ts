import { describe, expect, it } from "vitest";
import {
	TITULO_ACLARACION,
	TITULO_FUERA_DE_TEMA,
	TITULO_GENERICO,
	TITULO_SIN_EVIDENCIA,
	markdownATexto,
	ordenarRespuesta,
	quitarCitas,
} from "@/lib/guia/respuesta";

// Textos con el formato real del backend (rag/backend/rag/core/prompts.py y agent.py).
const JURIDICA = `**Criterio principal**

El cerramiento de una franja de playa por particulares vulnera el derecho colectivo al goce del espacio público, porque las playas son bienes de uso público [doc2][doc4]. La autoridad puede otorgar permisos [doc2].

**Desarrollo jurídico**

- El artículo 166 del Decreto 2324 de 1984 califica las playas como bienes de uso público [doc2].

**Límites de evidencia**

El contexto no incluye el texto de la concesión.`;

const SIN_EVIDENCIA =
	"**Situación:** evidencia insuficiente.\n\n**Motivo:** no se recuperaron fragmentos del corpus.\n\n**Cómo reformular:** precisa la actividad.";

describe("ordenarRespuesta", () => {
	it("toma la primera frase corta como título y deja el resto como resumen", () => {
		const r = ordenarRespuesta("**Respuesta corta**\n\nSí. Las playas son de todos [doc1].\n\n**Tenga en cuenta**\n\nEs general.");
		expect(r.tipo).toBe("normal");
		expect(r.titulo).toBe("Sí.");
		expect(r.resumen).toBe("Las playas son de todos [doc1].");
		expect(r.secciones).toEqual([{ titulo: "Tenga en cuenta", cuerpo: "Es general.", clase: "ojo" }]);
	});

	it("con 'Criterio principal' largo usa el título genérico y no recorta el texto", () => {
		const r = ordenarRespuesta(JURIDICA);
		expect(r.titulo).toBe(TITULO_GENERICO);
		expect(r.resumen).toContain("vulnera el derecho colectivo");
		expect(r.resumen).toContain("[doc2][doc4]");
		expect(r.secciones.map((s) => [s.titulo, s.clase])).toEqual([
			["Desarrollo jurídico", "normal"],
			["Límites de evidencia", "ojo"],
		]);
	});

	it("reconoce la respuesta fija de evidencia insuficiente", () => {
		const r = ordenarRespuesta(SIN_EVIDENCIA);
		expect(r.tipo).toBe("sin-evidencia");
		expect(r.titulo).toBe(TITULO_SIN_EVIDENCIA);
		expect(r.resumen).toBe("evidencia insuficiente.");
		expect(r.secciones.map((s) => s.titulo)).toEqual(["Motivo", "Cómo reformular"]);
		expect(r.secciones[0].cuerpo).toBe("no se recuperaron fragmentos del corpus.");
	});

	it("reconoce las respuestas fijas sin recuperación y no las reescribe", () => {
		const fuera =
			"La consulta está fuera del ámbito jurídico y normativo relacionado con playas. Puedo responder sobre pesca.";
		const r = ordenarRespuesta(fuera);
		expect(r).toEqual({ tipo: "fuera-de-tema", titulo: TITULO_FUERA_DE_TEMA, resumen: fuera, secciones: [] });
		expect(ordenarRespuesta("La consulta podría estar dentro del ámbito, pero…").titulo).toBe(TITULO_ACLARACION);
	});

	it("muestra un texto corrido sin secciones completo", () => {
		const texto =
			"Según el artículo 166 del Decreto 2324 de 1984, las playas son bienes de uso público, por tanto intransferibles a cualquier título [doc2]. Un hotel puede tener permiso [doc3].";
		const r = ordenarRespuesta(texto);
		expect(r.titulo).toBe(TITULO_GENERICO);
		expect(r.resumen).toBe(texto);
		expect(r.secciones).toEqual([]);
	});

	it("reconoce la sección de autoridades como 'acudir' y títulos con ##", () => {
		const r = ordenarRespuesta("No. Nadie puede cerrarla.\n\n## Autoridad competente\n\nCapitanía de Puerto.");
		expect(r.titulo).toBe("No.");
		expect(r.secciones[0]).toEqual({ titulo: "Autoridad competente", cuerpo: "Capitanía de Puerto.", clase: "acudir" });
	});

	it("no toma como título una lista ni una tabla", () => {
		expect(ordenarRespuesta("- uno\n- dos").titulo).toBe(TITULO_GENERICO);
		expect(ordenarRespuesta("| a | b |\n|---|---|\n| 1 | 2 |").titulo).toBe(TITULO_GENERICO);
	});
});

describe("texto para la voz", () => {
	it("quita citas y marcas de Markdown", () => {
		expect(quitarCitas("Sí [doc1]. Las playas [doc2][doc3], son")).toBe("Sí. Las playas, son");
		expect(markdownATexto("**Hola** mundo [doc1].\n\n- uno\n1. dos")).toBe("Hola mundo.\nuno\n1. dos");
	});
});
