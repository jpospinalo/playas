import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageList } from "@/components/chat/MessageList";
import type { Message } from "@/lib/types";

function makeMessages(): Message[] {
	return [
		{ id: "m1", role: "user", text: "¿Qué dice la norma?" },
		{ id: "m2", role: "assistant", text: "Así lo establece el artículo…" },
		// A5 — el mensaje de asistente vacío mientras aún no llega el primer
		// token nunca debe renderizarse (lo cubre LoadingBubble en su lugar).
		{ id: "m3", role: "assistant", text: "" },
	];
}

describe("MessageList — lista semántica", () => {
	it("renderiza los mensajes como una lista semántica (ul > li), uno por mensaje no vacío", () => {
		render(
			<MessageList
				messages={makeMessages()}
				ratedMessageIds={new Set()}
				onMessageRate={vi.fn()}
			/>,
		);

		const list = screen.getByRole("list");
		expect(list.tagName).toBe("UL");
		const items = screen.getAllByRole("listitem");
		expect(items).toHaveLength(2); // el mensaje de texto vacío se excluye
	});

	it("el contenedor de la lista no lleva role=\"log\" ni aria-live: el streaming llega token a token y el anuncio de progreso vive en ChatInterface", () => {
		render(
			<MessageList
				messages={makeMessages()}
				ratedMessageIds={new Set()}
				onMessageRate={vi.fn()}
			/>,
		);

		const list = screen.getByRole("list");
		expect(list).not.toHaveAttribute("aria-live");
		expect(list.getAttribute("role")).not.toBe("log");
	});

	it("conserva el contenido y el orden de los mensajes dentro de la lista", () => {
		render(
			<MessageList
				messages={makeMessages()}
				ratedMessageIds={new Set()}
				onMessageRate={vi.fn()}
			/>,
		);

		const items = screen.getAllByRole("listitem");
		expect(items[0]).toHaveTextContent("¿Qué dice la norma?");
		expect(items[1]).toHaveTextContent("Así lo establece el artículo…");
	});
});

describe("MessageList — nombre accesible de la lista", () => {
	it("la lista tiene un nombre accesible propio ('Historial de mensajes')", () => {
		render(
			<MessageList
				messages={makeMessages()}
				ratedMessageIds={new Set()}
				onMessageRate={vi.fn()}
			/>,
		);

		const list = screen.getByRole("list", { name: "Historial de mensajes" });
		expect(list.tagName).toBe("UL");
	});

	it("sigue sin role=\"log\" ni aria-live/aria-relevant: solo se añadió el nombre accesible", () => {
		render(
			<MessageList
				messages={makeMessages()}
				ratedMessageIds={new Set()}
				onMessageRate={vi.fn()}
			/>,
		);

		const list = screen.getByRole("list", { name: "Historial de mensajes" });
		expect(list.getAttribute("role")).not.toBe("log");
		expect(list).not.toHaveAttribute("aria-live");
		expect(list).not.toHaveAttribute("aria-relevant");
	});
});
