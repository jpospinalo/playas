import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConversationSearchDialog } from "@/components/chat/ConversationSearchDialog";
import type { Conversation } from "@/hooks/useConversations";

function baseProps(overrides: Record<string, unknown> = {}) {
	return {
		open: true,
		search: "",
		conversations: [] as Conversation[],
		results: [] as Conversation[],
		activeConversationId: null,
		loading: false,
		onSearchChange: vi.fn(),
		onClose: vi.fn(),
		onSelectConversation: vi.fn().mockResolvedValue(undefined),
		...overrides,
	};
}

describe("ConversationSearchDialog — overlay de cierre por click-afuera", () => {
	it("el overlay de fondo ya no es un <button> enfocable ni duplica el nombre accesible 'Cerrar búsqueda'", () => {
		render(<ConversationSearchDialog {...baseProps()} />);

		// El overlay de pantalla completa NO debe ser un `<button
		// aria-label="Cerrar búsqueda">`: sería exactamente el mismo nombre
		// accesible que el botón "X" visible del encabezado — un lector de
		// pantalla en modo de navegación por elementos interactivos vería DOS
		// controles con el mismo nombre, y un usuario de teclado podría caer
		// en el overlay invisible sin ningún indicador de foco. Solo debe
		// existir el botón "X" real.
		const closeButtons = screen.getAllByRole("button", {
			name: "Cerrar búsqueda",
		});
		expect(closeButtons).toHaveLength(1);
	});

	it("el overlay de fondo sigue cerrando el diálogo al hacer click, aunque ya no sea un <button>", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		const { container } = render(
			<ConversationSearchDialog {...baseProps({ onClose })} />,
		);

		const overlay = container.querySelector(
			'div[aria-hidden="true"].absolute.inset-0',
		);
		expect(overlay).not.toBeNull();

		await user.click(overlay as Element);
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("el overlay está fuera del árbol de accesibilidad (aria-hidden) y del orden de tabulación", () => {
		const { container } = render(<ConversationSearchDialog {...baseProps()} />);

		const overlay = container.querySelector(
			'div[aria-hidden="true"].absolute.inset-0',
		) as HTMLElement;
		expect(overlay.tagName).toBe("DIV");
		expect(overlay).toHaveAttribute("aria-hidden", "true");
		// Un `<div>` sin `tabIndex` explícito nunca entra al orden de
		// tabulación (a diferencia del `<button>` anterior).
		expect(overlay).not.toHaveAttribute("tabindex");
	});
});
