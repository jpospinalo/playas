import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LoadingBubble } from "@/components/chat/LoadingBubble";

describe("LoadingBubble — sin aria-live redundante", () => {
	it("no expone ninguna región viva propia: el anuncio de progreso vive en la región dedicada de ChatInterface", () => {
		const { container } = render(<LoadingBubble label="Buscando evidencia…" />);

		expect(container.querySelector("[aria-live]")).toBeNull();
		expect(screen.queryByRole("status")).not.toBeInTheDocument();
	});

	it("sigue mostrando el texto visible de la etapa actual junto a los puntos de carga", () => {
		const { container } = render(<LoadingBubble label="Buscando evidencia…" />);

		const visibleLabel = container.querySelector("span.text-xs.text-muted");
		expect(visibleLabel).toHaveTextContent("Buscando evidencia…");
	});

	it("sin label, sigue sin ninguna región viva y conserva el texto accesible por defecto", () => {
		const { container } = render(<LoadingBubble />);

		expect(container.querySelector("[aria-live]")).toBeNull();
		expect(
			screen.getByText("Buscando fuentes jurídicas relevantes…"),
		).toBeInTheDocument();
	});
});

describe("LoadingBubble — sin texto accesible duplicado", () => {
	it("con label, el texto solo aparece una vez en el árbol: no hay una copia sr-only adicional", () => {
		const { container } = render(<LoadingBubble label="Buscando evidencia…" />);

		const matches = Array.from(container.querySelectorAll("span")).filter(
			(el) => el.textContent?.trim() === "Buscando evidencia…",
		);
		expect(matches).toHaveLength(1);

		// Tampoco queda el texto accesible por defecto como una copia extra.
		expect(
			screen.queryByText("Buscando fuentes jurídicas relevantes…"),
		).not.toBeInTheDocument();
	});

	it("sin label, el texto accesible por defecto aparece una sola vez", () => {
		const { container } = render(<LoadingBubble />);

		const matches = Array.from(container.querySelectorAll("span")).filter(
			(el) =>
				el.textContent?.trim() === "Buscando fuentes jurídicas relevantes…",
		);
		expect(matches).toHaveLength(1);
	});
});
