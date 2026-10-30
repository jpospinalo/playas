import { createRef, useState } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Respuesta } from "@/components/guia/Respuesta";
import { TXT } from "@/lib/guia/textos";
import { YA_CALIFICADO } from "@/lib/api";
import type { SourceGroup } from "@/lib/types";

const FUENTES: SourceGroup[] = [
	{
		source: "decreto-2324.md",
		title: "Decreto 2324 de 1984",
		doc_type: "normativa",
		metadata: { doc_type: "normativa" },
		fragments: [{ index: 1, content: "Artículo 166. Bienes de uso público.", metadata: {} }],
	},
];

type Props = React.ComponentProps<typeof Respuesta>;

/** La caja de seguimiento guarda lo escrito afuera, como en GuiaApp. */
function ConSeguimiento(props: Props) {
	const [texto, setTexto] = useState(props.seguimiento);
	return <Respuesta {...props} seguimiento={texto} onCambioSeguimiento={setTexto} />;
}

function pintar(texto: string, extra: Partial<Props> = {}) {
	const props = {
		pregunta: "Un hotel no me deja pasar",
		playa: null,
		texto,
		fuentes: FUENTES,
		puedeCalificar: true,
		onCalificar: vi.fn().mockResolvedValue(undefined),
		onVolver: vi.fn(),
		onOtraPregunta: vi.fn(),
		onEscribirDeNuevo: vi.fn(),
		seguimiento: "",
		onCambioSeguimiento: vi.fn(),
		onSeguir: vi.fn(),
		muchasSeguidas: false,
		tituloRef: createRef<HTMLHeadingElement>(),
		...extra,
	};
	render(<ConSeguimiento {...props} />);
	return props;
}

describe("Respuesta (diseño v3)", () => {
	it("muestra el veredicto, convierte [docN] en 'fuente N' y abre esa fuente al tocarla", async () => {
		pintar("**Respuesta corta**\n\nSí. Las playas son de uso público [doc1].");
		expect(screen.getByRole("heading", { level: 1, name: "Sí." })).toBeInTheDocument();
		expect(screen.queryByText(/\[doc1\]/)).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("link", { name: "(fuente 1)" }));
		const detalles = screen.getByText("Ver de dónde sale esta respuesta").closest("details")!;
		expect(detalles.open).toBe(true);
		expect(within(detalles).getByText(/Artículo 166/)).toBeInTheDocument();
	});

	it("no muestra como enlace una cita a una fuente que no llegó", () => {
		pintar("Sí. Dato [doc9].");
		expect(screen.queryByRole("link", { name: "(fuente 9)" })).not.toBeInTheDocument();
	});

	it("no agrega secciones que el backend no trajo (ni 'A quién acudir' ni pasos)", () => {
		pintar("Según el artículo 166 del Decreto 2324 de 1984, las playas son bienes de uso público y nadie puede apropiarse de ellas [doc1].");
		expect(screen.getByRole("heading", { level: 1, name: "Esto es lo que encontramos" })).toBeInTheDocument();
		expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([TXT.seguirTitulo]);
		expect(screen.queryByText(/A quién acudir/)).not.toBeInTheDocument();
	});

	it("'Límites de evidencia' va en el recuadro de atención, con título sencillo", () => {
		pintar("**Criterio principal**\n\nTexto largo del criterio principal que no cabe como título grande de la pantalla en ningún caso [doc1].\n\n**Límites de evidencia**\n\nFalta la concesión.");
		const h2 = screen.getByRole("heading", { level: 2, name: "Tenga en cuenta" });
		expect(h2.closest(".guia-ojo")).not.toBeNull();
	});

	it("'Sí' guarda la calificación y agradece", async () => {
		const props = pintar("Sí. Texto [doc1].");
		await userEvent.click(screen.getByRole("button", { name: "Sí" }));
		expect(props.onCalificar).toHaveBeenCalledWith({ util: true });
		const gracias = await screen.findByText(/Gracias\. Su respuesta/);
		expect(gracias).toHaveAttribute("role", "status");
	});

	it("'No' pregunta qué le faltó y lo envía", async () => {
		const props = pintar("Sí. Texto [doc1].");
		await userEvent.click(screen.getByRole("button", { name: "No" }));
		await userEvent.type(screen.getByLabelText(/Qué le faltó/), "Saber el horario");
		await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
		expect(props.onCalificar).toHaveBeenCalledWith({ util: false, comentario: "Saber el horario" });
	});

	it("sin evidencia: título claro y opción de escribir la pregunta de otra forma, sin calificar", async () => {
		const props = pintar("**Situación:** evidencia insuficiente.\n\n**Motivo:** no hubo fragmentos.", { fuentes: [] });
		expect(screen.getByRole("heading", { level: 1, name: "No encontramos una respuesta segura" })).toBeInTheDocument();
		// Sin palabras técnicas ni tuteo del texto fijo del backend.
		expect(screen.queryByText(/corpus|fragmentos|consulta|precisa/i)).not.toBeInTheDocument();
		expect(screen.queryByText("¿Esta respuesta le sirvió?")).not.toBeInTheDocument();
		// QA-F02: precisar la pregunta sigue en el mismo tema: la pregunta va a
		// la caja de esta pantalla, no al inicio (que empezaría de cero).
		await userEvent.click(screen.getByRole("button", { name: "Escribir la pregunta de otra forma" }));
		expect(props.onEscribirDeNuevo).not.toHaveBeenCalled();
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toHaveValue("Un hotel no me deja pasar");
	});

	it("fuera de tema en la 1.ª pregunta: sin caja y el botón dice que empieza de cero", async () => {
		const props = pintar("La consulta está fuera del ámbito de ATLAS.", { fuentes: [] });
		expect(screen.queryByRole("textbox", { name: TXT.seguirTitulo })).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Escribir la pregunta de otra forma (empieza de cero)" }));
		expect(props.onEscribirDeNuevo).toHaveBeenCalled();
	});

	it("tras enviar '¿Qué le faltó?' el recuadro no se encoge (un doble toque no cae en 'Empezar de nuevo')", async () => {
		pintar("Sí. Texto [doc1].");
		await userEvent.click(screen.getByRole("button", { name: "No" }));
		const caja = screen.getByLabelText(/Qué le faltó/).closest(".guia-sirvio") as HTMLElement;
		Object.defineProperty(caja, "offsetHeight", { configurable: true, value: 260 });
		await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
		await screen.findByText(/Gracias\. Su respuesta/);
		expect(caja.style.minHeight).toBe("260px");
	});

	it("'Volver' vuelve a la pantalla anterior, no al inicio", async () => {
		const props = pintar("Sí. Texto.");
		await userEvent.click(screen.getByRole("button", { name: "Volver" }));
		expect(props.onVolver).toHaveBeenCalled();
		expect(props.onOtraPregunta).not.toHaveBeenCalled();
	});

	it("no muestra HTML del backend ni enlaces que no sean web (QA-21)", () => {
		pintar(
			"Sí. Texto <script>window.x=1</script> normal <iframe src=x></iframe> [Toque aquí](javascript:alert(1)) y [ley](https://www.suin-juriscol.gov.co).",
		);
		expect(document.querySelector("script, iframe")).toBeNull();
		expect(screen.queryByText(/<script>|<iframe/)).not.toBeInTheDocument();
		// Tampoco queda a la vista el texto que había dentro de <script> (QA-32).
		expect(screen.queryByText(/window\.x/)).not.toBeInTheDocument();
		expect(screen.queryByRole("link", { name: "Toque aquí" })).not.toBeInTheDocument();
		expect(screen.getByText(/Toque aquí/)).toBeInTheDocument();
		const ley = screen.getByRole("link", { name: "ley" });
		expect(ley).toHaveAttribute("href", "https://www.suin-juriscol.gov.co");
		expect(ley).not.toHaveAttribute("target");
	});

	it("no ofrece calificar mientras la respuesta no está guardada", () => {
		pintar("Sí. Texto.", { puedeCalificar: false });
		expect(screen.queryByText("¿Esta respuesta le sirvió?")).not.toBeInTheDocument();
	});

	it("al final ofrece preguntar algo más sobre esto y lo envía como seguimiento", async () => {
		const props = pintar("Sí. Texto [doc1].");
		expect(screen.getByRole("heading", { level: 2, name: TXT.seguirTitulo })).toBeInTheDocument();
		const caja = screen.getByRole("textbox", { name: TXT.seguirTitulo });
		await userEvent.type(caja, "pez");
		await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));
		expect(screen.getByRole("alert")).toHaveTextContent(TXT.escribirCorta);
		await userEvent.clear(caja);
		await userEvent.type(caja, "¿Y si es de noche?");
		await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));
		expect(props.onSeguir).toHaveBeenCalledWith("¿Y si es de noche?");
		expect(props.onOtraPregunta).not.toHaveBeenCalled();
	});

	it("'Empezar de nuevo con otro tema' deja la conversación", async () => {
		const props = pintar("Sí. Texto.");
		await userEvent.click(screen.getByRole("button", { name: TXT.empezarDeNuevo }));
		expect(props.onOtraPregunta).toHaveBeenCalled();
		expect(props.onSeguir).not.toHaveBeenCalled();
	});

	it("sin respuesta segura sí hay caja para precisar en el mismo tema (QA-F02)", () => {
		pintar("**Situación:** evidencia insuficiente.\n\n**Motivo:** no hubo fragmentos.", { fuentes: [] });
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: TXT.empezarDeNuevo })).toBeInTheDocument();
	});

	it("respuesta guardada tras recargar: sin caja de seguimiento, solo empezar de nuevo", () => {
		pintar("Sí. Texto.", { puedeSeguir: false });
		expect(screen.queryByText(TXT.seguirTitulo)).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: TXT.empezarDeNuevo })).toHaveClass("guia-btn");
	});

	it("tras varias respuestas seguidas avisa qué recuerda ATLAS, sin tope (decisión 30-oct)", () => {
		pintar("Sí. Texto.", { muchasSeguidas: true });
		expect(screen.getByText(TXT.seguirTope)).toBeInTheDocument();
		// La caja sigue ahí y "otro tema" no se vuelve la acción principal.
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: TXT.empezarDeNuevo })).toHaveClass("guia-btn-sec");
	});

	it("la caja de seguimiento dice que ATLAS recuerda lo conversado", () => {
		pintar("Sí. Texto.");
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toHaveAccessibleDescription(
			TXT.seguirRecuerda,
		);
		expect(screen.getByRole("button", { name: TXT.empezarDeNuevo })).toHaveTextContent(
			"Nueva pregunta sobre otro tema (empieza de cero)",
		);
	});
});

describe("¿Le sirvió? ya respondido antes (409)", () => {
	it("si el servidor ya tenía la opinión, lo dice sin mostrar error", async () => {
		pintar("Sí. Texto.", { onCalificar: vi.fn().mockRejectedValue(new Error(YA_CALIFICADO)) });
		await userEvent.click(screen.getByRole("button", { name: "Sí" }));
		expect(await screen.findByText(/Ya había respondido sobre esta respuesta/)).toHaveAttribute("role", "status");
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});
});

describe("Fuentes con el mismo párrafo", () => {
	it("se muestran una vez y la cita a la repetida abre la que quedó", async () => {
		const parrafo =
			"Las playas y los terrenos de bajamar son bienes de uso público de la Nación, inalienables, imprescriptibles e inembargables, y su uso por particulares exige concesión, permiso o licencia otorgados conforme a la ley vigente.";
		const fuentes: SourceGroup[] = [
			{ source: "a.md", title: "Consulta 2010", doc_type: "jurisprudencia", metadata: {}, fragments: [{ index: 1, content: parrafo, metadata: {} }] },
			{ source: "b.md", title: "Sentencia 2016", doc_type: "jurisprudencia", metadata: {}, fragments: [{ index: 2, content: parrafo, metadata: {} }] },
		];
		pintar("Sí. Son bienes de uso público [doc2].", { fuentes });
		const lista = screen.getByText("Ver de dónde sale esta respuesta").closest("details")!;
		expect(within(lista).getAllByRole("listitem")).toHaveLength(1);
		expect(within(lista).getByText(/aparece también como/)).toHaveTextContent("fuente 2 (Sentencia 2016)");
		await userEvent.click(screen.getByRole("link", { name: "(fuente 2)" }));
		expect(lista.open).toBe(true);
		expect(document.getElementById("fuente-1")).toHaveClass("marcada");
	});
});

describe("Hilo: lo que ya preguntó sobre este tema", () => {
	const fuente = (n: number, titulo: string): SourceGroup => ({
		source: `${titulo}.md`,
		title: titulo,
		doc_type: "normativa",
		metadata: {},
		fragments: [{ index: n, content: `Contenido ${titulo}`, metadata: {} }],
	});
	const anteriores = [
		{
			id: "r1",
			pregunta: "¿Puedo construir en la playa?",
			playa: "Taganga",
			texto: "No. Hace falta permiso [doc1].",
			fuentes: [fuente(1, "Decreto uno")],
			calificada: true,
			puedeCalificar: true,
		},
		{
			id: "r2",
			pregunta: "¿Y si es algo temporal?",
			playa: null,
			texto: "Tampoco. También pide permiso [doc1].",
			fuentes: [fuente(1, "Decreto dos")],
			puedeCalificar: true,
		},
	];

	it("muestra las anteriores plegadas, numeradas, y la actual completa como pregunta 3", async () => {
		const onCalificarAnterior = vi.fn().mockResolvedValue(undefined);
		pintar("Sí. La Capitanía [doc1].", { anteriores, onCalificarAnterior });
		const hilo = screen.getByRole("region", { name: "Lo que ya preguntó sobre este tema" });
		const items = Array.from(hilo.querySelectorAll<HTMLLIElement>(":scope > ol > li"));
		expect(items).toHaveLength(2);
		const primera = items[0].querySelector("details")!;
		expect(primera.open).toBe(false);
		expect(within(primera).getByText(/Pregunta 1:/)).toBeInTheDocument();
		expect(screen.getByText(/Pregunta 3 de este tema\./)).toBeInTheDocument();
		// La actual sigue siendo el único h1.
		expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
		// Se abre al tocarla y muestra su respuesta y su "Ya respondió".
		await userEvent.click(primera.querySelector("summary")!);
		expect(primera.open).toBe(true);
		expect(within(primera).getByText(/Hace falta permiso/)).toBeInTheDocument();
		expect(within(primera).getByText("Ya respondió: le sirvió.")).toBeInTheDocument();
		// La segunda todavía se puede calificar, con su propio "¿Le sirvió?".
		const segunda = items[1].querySelector("details")!;
		await userEvent.click(segunda.querySelector("summary")!);
		await userEvent.click(within(segunda).getByRole("button", { name: "Sí" }));
		expect(onCalificarAnterior).toHaveBeenCalledWith("r2", { util: true });
	});

	it("las fuentes de cada respuesta del hilo tienen ids propios (no chocan con la actual)", () => {
		pintar("Sí. La Capitanía [doc1].", { anteriores });
		expect(document.getElementById("t1-fuente-1")).toHaveTextContent("Decreto uno");
		expect(document.getElementById("t2-fuente-1")).toHaveTextContent("Decreto dos");
		expect(document.querySelectorAll("#fuente-1")).toHaveLength(1);
	});

	it("si ATLAS pidió más datos, se contestan en el mismo tema", () => {
		pintar("La consulta podría estar dentro del ámbito, pero falta indicar la playa.", { fuentes: [] });
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toBeInTheDocument();
	});

	it("dentro de un hilo, 'fuera de tema' no corta el tema (QA-F01)", () => {
		const fuera = "La consulta está fuera del ámbito de ATLAS.";
		pintar(fuera, { fuentes: [], anteriores });
		expect(screen.getByRole("textbox", { name: TXT.seguirTitulo })).toBeInTheDocument();
		// Sin hilo, fuera de tema: solo empezar de nuevo.
		cleanup();
		pintar(fuera, { fuentes: [] });
		expect(screen.queryByRole("textbox", { name: TXT.seguirTitulo })).not.toBeInTheDocument();
	});

	it("la respuesta actual ya calificada no vuelve a preguntar", () => {
		pintar("Sí. Texto.", { calificada: false });
		expect(screen.queryByText("¿Esta respuesta le sirvió?")).not.toBeInTheDocument();
		expect(screen.getByText("Ya respondió: no le sirvió.")).toBeInTheDocument();
	});
});
