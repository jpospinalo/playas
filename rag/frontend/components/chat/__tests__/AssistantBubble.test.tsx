import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssistantBubble } from "@/components/chat/AssistantBubble";
import type { SourceGroup } from "@/lib/types";

const sources: SourceGroup[] = [
	{
		source: "sentencia-c-123.pdf",
		title: "Sentencia C-123 de 2020",
		doc_type: "jurisprudencia",
		metadata: {
			doc_type: "jurisprudencia",
			Corporación: "Corte Constitucional",
			Radicado: "C-123/20",
		},
		fragments: [
			{
				index: 1,
				content: "Contenido del fragmento citado.",
				metadata: {},
			},
		],
	},
];

function setup(text = "Una afirmación [doc1] y otra sin fuente [doc2].") {
	const onRate = vi.fn().mockResolvedValue(undefined);
	const utils = render(
		<AssistantBubble
			text={text}
			sources={sources}
			messageId="msg-1"
			isRated={false}
			onRate={onRate}
		/>,
	);
	return { ...utils, onRate };
}

describe("AssistantBubble — badges de cita", () => {
	it("un badge con fragmento disponible no está deshabilitado y expone aria-expanded", async () => {
		const user = userEvent.setup();
		const { container } = setup();

		const badge = screen.getByRole("button", { name: "Ver fuente 1" });
		expect(badge).not.toBeDisabled();
		expect(badge).toHaveAttribute("aria-expanded", "false");

		await user.click(badge);

		// `aria-expanded` se recalcula de forma declarativa en cada
		// invocación de `a()` (ver comentario en AssistantBubble.tsx), sin
		// que eso añada `popover` a las dependencias del memo que produce
		// `a`: el badge NUNCA se desmonta/remonta al abrir/cerrar el popover;
		// por eso sigue siendo seguro reusar la misma referencia `badge`
		// capturada antes del click.
		expect(badge).toHaveAttribute("aria-expanded", "true");
		// El texto del fragmento también aparece en el acordeón de fuentes
		// (fuera del popover), así que se acota la búsqueda al popover.
		expect(
			container.querySelector(".doc-popover--rich"),
		).toHaveTextContent("Contenido del fragmento citado.");
	});

	it("un badge sin fragmento disponible usa disabled real, no solo aria-disabled", () => {
		setup();

		const missingBadge = screen.getByRole("button", {
			name: "Fuente 2 no disponible",
		});
		// Con `disabled` real (no solo `aria-disabled` + `pointer-events:none`
		// en CSS), queda fuera del orden de tabulación.
		expect(missingBadge).toBeDisabled();
		expect(missingBadge).toHaveAttribute("aria-disabled", "true");
	});

	it("abrir y cerrar el popover no desmonta el badge (preserva su identidad de nodo)", async () => {
		const user = userEvent.setup();
		setup();

		const badge = screen.getByRole("button", { name: "Ver fuente 1" });
		await user.click(badge); // abre
		await user.click(badge); // cierra (toggle)

		// Si `aria-expanded` volviera a ser una prop reactiva del render de
		// ReactMarkdown, React remontaría el botón en cada click (cambia la
		// identidad de la función que produce el elemento) y esta misma
		// referencia dejaría de estar en el documento.
		expect(badge).toBe(screen.getByRole("button", { name: "Ver fuente 1" }));
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute("aria-expanded", "false");
	});

	it("el popover abierto ya no usa role=\"tooltip\" y es alcanzable por teclado", async () => {
		const user = userEvent.setup();
		const { container } = setup();

		await user.click(screen.getByRole("button", { name: "Ver fuente 1" }));

		expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
		// El texto del fragmento también aparece en el acordeón de fuentes
		// (fuera del popover), así que se busca acotado a la región
		// desplazable del popover en vez de por texto ambiguo.
		const scrollRegion = container.querySelector(
			".doc-popover-content--scroll",
		);
		expect(scrollRegion).toHaveAttribute("tabindex", "0");
		expect(scrollRegion).toHaveTextContent("Contenido del fragmento citado.");
	});

	it("el popover expone role=\"region\" (no es un contenedor sin rol)", async () => {
		const user = userEvent.setup();
		const { container } = setup();

		await user.click(screen.getByRole("button", { name: "Ver fuente 1" }));

		const popoverEl = container.querySelector(".doc-popover--rich");
		expect(popoverEl).toHaveAttribute("role", "region");
	});

	it("el recorte vertical respeta también el margen SUPERIOR frente al viewport", async () => {
		const user = userEvent.setup();
		const { container } = setup();

		await user.click(screen.getByRole("button", { name: "Ver fuente 1" }));

		// jsdom no calcula layout real: tanto el botón como el propio popover
		// devuelven un `getBoundingClientRect()` en (0,0,0,0). Con la posición
		// inicial (`btnRect.bottom - wrapperRect.top + POPOVER_GAP` = 0 - 0 + 6
		// = 6px) el popover queda por encima del margen mínimo
		// `POPOVER_VIEWPORT_MARGIN` (8px, ver AssistantBubble.tsx) respecto al
		// borde superior del viewport: el efecto de recorte debe empujar el
		// popover también hacia abajo cuando queda demasiado cerca del borde
		// superior, no solo hacia arriba cuando se sale por abajo. El efecto
		// debe sumar el faltante (8px) a los 6px iniciales, dejando `top` en
		// 14px.
		const popoverEl = container.querySelector(
			".doc-popover--rich",
		) as HTMLElement;
		expect(popoverEl.style.top).toBe("14px");
	});

	it("aria-expanded se mantiene sincronizado sin efecto imperativo al alternar entre dos citas", async () => {
		const user = userEvent.setup();
		const twoSources: SourceGroup[] = [
			...sources,
			{
				source: "decreto-456.pdf",
				title: "Decreto 456 de 2021",
				doc_type: "normativa",
				metadata: { doc_type: "normativa" },
				fragments: [
					{ index: 2, content: "Otro fragmento citado.", metadata: {} },
				],
			},
		];
		const onRate = vi.fn().mockResolvedValue(undefined);
		render(
			<AssistantBubble
				text="Una afirmación [doc1] y otra [doc2]."
				sources={twoSources}
				messageId="msg-1"
				isRated={false}
				onRate={onRate}
			/>,
		);

		const badge1 = screen.getByRole("button", { name: "Ver fuente 1" });
		const badge2 = screen.getByRole("button", { name: "Ver fuente 2" });

		// Evidencia empírica: ReactMarkdown (no memoizado, con `remarkPlugins`
		// recreado en cada render) vuelve a invocar `a()` en cada cambio de
		// `popover`, así que basta con leer `popoverRef.current` dentro de
		// `a()` para mantener `aria-expanded` al día, sin un efecto
		// imperativo que recorra el DOM.
		await user.click(badge1);
		expect(badge1).toHaveAttribute("aria-expanded", "true");
		expect(badge2).toHaveAttribute("aria-expanded", "false");

		await user.click(badge2);
		expect(badge1).toHaveAttribute("aria-expanded", "false");
		expect(badge2).toHaveAttribute("aria-expanded", "true");

		// Ambas referencias siguen siendo las mismas capturadas al inicio:
		// ninguna se desmontó/remontó durante los dos clicks.
		expect(badge1).toBe(screen.getByRole("button", { name: "Ver fuente 1" }));
		expect(badge2).toBe(screen.getByRole("button", { name: "Ver fuente 2" }));
	});
});
