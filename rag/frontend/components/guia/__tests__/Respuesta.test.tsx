import { createRef } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Respuesta } from "@/components/guia/Respuesta";
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

function pintar(texto: string, extra: Partial<React.ComponentProps<typeof Respuesta>> = {}) {
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
		tituloRef: createRef<HTMLHeadingElement>(),
		...extra,
	};
	render(<Respuesta {...props} />);
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
		expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
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
		expect(await screen.findByRole("status")).toHaveTextContent("Gracias");
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
		await userEvent.click(screen.getByRole("button", { name: "Escribir la pregunta de otra forma" }));
		expect(props.onEscribirDeNuevo).toHaveBeenCalled();
	});

	it("tras enviar '¿Qué le faltó?' el recuadro no se encoge (un doble toque no cae en 'Hacer otra pregunta')", async () => {
		pintar("Sí. Texto [doc1].");
		await userEvent.click(screen.getByRole("button", { name: "No" }));
		const caja = screen.getByLabelText(/Qué le faltó/).closest(".guia-sirvio") as HTMLElement;
		Object.defineProperty(caja, "offsetHeight", { configurable: true, value: 260 });
		await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
		await screen.findByRole("status");
		expect(caja.style.minHeight).toBe("260px");
	});

	it("'Volver' vuelve a la pantalla anterior, no al inicio", async () => {
		const props = pintar("Sí. Texto.");
		await userEvent.click(screen.getByRole("button", { name: "Volver" }));
		expect(props.onVolver).toHaveBeenCalled();
		expect(props.onOtraPregunta).not.toHaveBeenCalled();
	});

	it("no ofrece calificar mientras la respuesta no está guardada", () => {
		pintar("Sí. Texto.", { puedeCalificar: false });
		expect(screen.queryByText("¿Esta respuesta le sirvió?")).not.toBeInTheDocument();
	});
});
