import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssistantBubble } from "@/components/chat/AssistantBubble";
import { SourcesAccordion } from "@/components/chat/SourcesAccordion";
import { normalizeSources, type SourceGroup } from "@/lib/types";

const normativeSources: SourceGroup[] = [
	{
		source: "decreto.pdf",
		title: "Decreto de prueba",
		doc_type: "normativa",
		metadata: { doc_type: "normativa", norma: "Decreto de prueba" },
		fragments: [
			{
				index: 4,
				content: "Cuerpo del artículo siete.\nÚltima línea íntegra del pasaje.",
				metadata: {
					titulo: "Título primero",
					capitulo: "Capítulo dos",
					articulo: "7",
					section_name: "Objeto",
					summary: "Resumen descriptivo separado.",
				},
			},
			{
				index: 9,
				content: "Cuerpo del artículo setenta y dos.",
				metadata: {
					titulo: "Título segundo",
					capitulo: "Capítulo seis",
					articulo: "72",
				},
			},
		],
	},
];

function renderAnswer(sources = normativeSources, text = "Primero [doc4]; segundo [doc9].") {
	return render(
		<AssistantBubble
			text={text}
			sources={sources}
			messageId="answer-1"
			isRated={false}
			onRate={vi.fn().mockResolvedValue(undefined)}
		/>,
	);
}

describe("Atribución de los pasajes citados", () => {
	it.each(["doc", "Doc", "DOC"])(
		"enlaza [%s4] al índice global y mantiene deshabilitada la fuente ausente",
		async (marker) => {
			const user = userEvent.setup();
			renderAnswer(normativeSources, `Respuesta [${marker}4], referencia ausente [${marker}99].`);
			await user.click(screen.getByRole("button", { name: "Ver fuente 4" }));
			expect(screen.getByRole("region", { name: "Fuente 4: Decreto de prueba" })).toHaveTextContent(
				"Última línea íntegra del pasaje.",
			);
			expect(screen.getByRole("button", { name: "Fuente 99 no disponible" })).toBeDisabled();
			expect(screen.queryByRole("button", { name: "Ver fuente 1" })).not.toBeInTheDocument();
		},
	);

	it("cambia artículo, capítulo y título con la cita activa del mismo archivo", async () => {
		const user = userEvent.setup();
		renderAnswer();
		await user.click(screen.getByRole("button", { name: "Ver fuente 9" }));
		const second = within(screen.getByRole("region", { name: "Fuente 9: Decreto de prueba" }));
		expect(second.getByText("72")).toBeInTheDocument();
		expect(second.getByText("Capítulo seis")).toBeInTheDocument();
		expect(second.getByText("Título segundo")).toBeInTheDocument();
		expect(second.queryByText("7")).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "Ver fuente 4" }));
		const first = within(screen.getByRole("region", { name: "Fuente 4: Decreto de prueba" }));
		expect(first.getByText("7")).toBeInTheDocument();
		expect(first.getByText("Capítulo dos")).toBeInTheDocument();
		expect(first.queryByText("72")).not.toBeInTheDocument();
	});

	it("el acordeón atribuye cada artículo a su propio fragmento", async () => {
		const user = userEvent.setup();
		render(<SourcesAccordion sources={normativeSources} />);
		await user.click(screen.getByRole("button", { name: "1 fuente (2 fragmentos)" }));
		const first = screen.getByText(/Cuerpo del artículo siete/).closest("li")!;
		const second = screen.getByText("Cuerpo del artículo setenta y dos.").closest("li")!;
		expect(within(first).getByText("7")).toBeInTheDocument();
		expect(within(first).queryByText("72")).not.toBeInTheDocument();
		expect(within(second).getByText("72")).toBeInTheDocument();
		expect(within(second).queryByText("7")).not.toBeInTheDocument();
	});

	it("conserva el fallback de metadata de grupo en fuentes históricas sin jerarquía de fragmento", async () => {
		const user = userEvent.setup();
		const historical: SourceGroup[] = [{
			...normativeSources[0],
			metadata: { doc_type: "normativa", articulo: "8 histórico", capitulo: "Capítulo histórico" },
			fragments: [{ index: 4, content: "Pasaje histórico.", metadata: {} }],
		}];
		renderAnswer(historical, "Respuesta [doc4].");
		await user.click(screen.getByRole("button", { name: "Ver fuente 4" }));
		expect(within(screen.getByRole("region")).getByText("8 histórico")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "1 fuente consultada" }));
		const fragment = screen.getByText("Pasaje histórico.", { selector: ".line-clamp-3" }).closest("li")!;
		expect(within(fragment).getByText("Capítulo histórico")).toBeInTheDocument();
	});

	it("no presta al fragmento parcialmente descrito un artículo heredado del grupo", async () => {
		const user = userEvent.setup();
		const partial: SourceGroup[] = [{
			...normativeSources[0],
			metadata: { doc_type: "normativa", articulo: "777 ajeno" },
			fragments: [{ index: 4, content: "Pasaje sin artículo identificado.", metadata: { capitulo: "Capítulo propio" } }],
		}];
		renderAnswer(partial, "Respuesta [doc4].");
		await user.click(screen.getByRole("button", { name: "Ver fuente 4" }));
		expect(within(screen.getByRole("region")).getByText("Capítulo propio")).toBeInTheDocument();
		expect(screen.queryByText("777 ajeno")).not.toBeInTheDocument();
	});

	it("la recarga SQL conserva los índices y la jerarquía sin mutar las fuentes", async () => {
		const user = userEvent.setup();
		const stored = JSON.stringify(normativeSources);
		const reloaded = normalizeSources(JSON.parse(stored));
		renderAnswer(reloaded, "Pasaje recuperado [doc9].");
		await user.click(screen.getByRole("button", { name: "Ver fuente 9" }));
		expect(within(screen.getByRole("region")).getByText("72")).toBeInTheDocument();
		expect(JSON.stringify(reloaded)).toBe(stored);
	});

	it("el resumen no reemplaza el cuerpo completo ni rompe Markdown o enlaces ordinarios", async () => {
		const user = userEvent.setup();
		const { container } = renderAnswer(normativeSources, "**Respuesta** [doc4]. [Sitio](https://example.org/ayuda)");
		expect(screen.getByRole("link", { name: "Sitio" })).toHaveAttribute("href", "https://example.org/ayuda");
		expect(container.querySelector("strong")).toHaveTextContent("Respuesta");
		await user.click(screen.getByRole("button", { name: "Ver fuente 4" }));
		expect(container.querySelector(".doc-popover-content--scroll")?.textContent).toBe(normativeSources[0].fragments[0].content);
		expect(container.querySelector(".doc-popover-summary")).toHaveTextContent("Resumen descriptivo separado.");
	});

	it("las fuentes planas antiguas normalizadas conservan atribución y cuerpo", async () => {
		const user = userEvent.setup();
		const legacy = normalizeSources([{ source: "anterior.pdf", title: "Norma anterior", content: "Cuerpo legado.", metadata: { doc_type: "normativa", articulo: "5 legado" } }]);
		renderAnswer(legacy, "Respuesta [DOC1].");
		await user.click(screen.getByRole("button", { name: "Ver fuente 1" }));
		const popover = within(screen.getByRole("region"));
		expect(popover.getByText("5 legado")).toBeInTheDocument();
		expect(popover.getByText("Cuerpo legado.")).toBeInTheDocument();
	});
});
