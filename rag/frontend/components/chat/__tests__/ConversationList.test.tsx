import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationList } from "@/components/chat/ConversationList";
import type { Conversation } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
	return {
		id: "conv-1",
		title: "Título original",
		threadId: "thread-1",
		createdAt: new Date("2026-01-01T00:00:00Z"),
		updatedAt: new Date("2026-01-01T00:00:00Z"),
		messageCount: 2,
		...overrides,
	};
}

async function openMenu(user: ReturnType<typeof userEvent.setup>, conv: Conversation) {
	const menuButton = screen.getByRole("button", {
		name: new RegExp(`Opciones para ${conv.title}`),
	});
	await user.click(menuButton);
}

describe("ConversationList — renombrar y eliminar (A2)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("cierra la edición sin solicitud si el título no cambió", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		const onConversationsRefresh = vi.fn();
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={null}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={vi.fn()}
				onConversationsRefresh={onConversationsRefresh}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /renombrar/i }));
		const input = screen.getByDisplayValue("Título original");
		await user.keyboard("{Enter}");

		await waitFor(() => {
			expect(screen.queryByDisplayValue("Título original")).not.toBeInTheDocument();
		});
		expect(fetch).not.toHaveBeenCalled();
		expect(onConversationsRefresh).not.toHaveBeenCalled();
		expect(input).not.toBeInTheDocument();
	});

	it("mantiene la edición abierta y muestra validación si el título queda vacío", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={null}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={vi.fn()}
				onConversationsRefresh={vi.fn()}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /renombrar/i }));
		const input = screen.getByDisplayValue("Título original");
		await user.clear(input);
		await user.keyboard("{Enter}");

		expect(await screen.findByRole("alert")).toHaveTextContent(/no puede estar vacío/i);
		expect(input).toBeInTheDocument();
		expect(fetch).not.toHaveBeenCalled();
	});

	it("muestra un error local sin vaciar la lista cuando el PATCH falla", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
			ok: false,
			status: 500,
			clone: () => ({ json: async () => ({}) }),
			text: async () => "fallo simulado del servidor",
		});
		const onConversationsRefresh = vi.fn();
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={null}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={vi.fn()}
				onConversationsRefresh={onConversationsRefresh}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /renombrar/i }));
		const input = screen.getByDisplayValue("Título original");
		await user.clear(input);
		await user.type(input, "Nuevo título");
		await user.keyboard("{Enter}");

		expect(await screen.findByRole("alert")).toHaveTextContent(/fallo simulado del servidor/i);
		// La edición sigue abierta: el input no se descarta ante un fallo.
		expect(screen.getByDisplayValue("Nuevo título")).toBeInTheDocument();
		expect(onConversationsRefresh).not.toHaveBeenCalled();
	});

	it("no duplica la solicitud cuando Enter y blur se disparan para el mismo guardado", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		let resolveFetch: (value: unknown) => void = () => {};
		(fetch as ReturnType<typeof vi.fn>).mockReturnValue(
			new Promise((resolve) => {
				resolveFetch = resolve;
			}),
		);
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={null}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={vi.fn()}
				onConversationsRefresh={vi.fn()}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /renombrar/i }));
		const input = screen.getByDisplayValue("Título original");
		await user.clear(input);
		await user.type(input, "Otro título");
		await user.keyboard("{Enter}");
		// Segundo disparo (blur) mientras la primera solicitud sigue en vuelo.
		input.blur();

		expect(fetch).toHaveBeenCalledTimes(1);
		resolveFetch({
			ok: true,
			status: 200,
			clone: () => ({ json: async () => ({}) }),
			text: async () => "",
		});
		await waitFor(() => {
			expect(screen.queryByDisplayValue("Otro título")).not.toBeInTheDocument();
		});
	});

	it("elimina la conversación activa y dispara onNewChat solo tras éxito", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
			ok: true,
			status: 204,
			clone: () => ({ json: async () => ({}) }),
			text: async () => "",
		});
		const onNewChat = vi.fn();
		const onConversationsRefresh = vi.fn().mockResolvedValue(undefined);
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={conv.id}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={onNewChat}
				onConversationsRefresh={onConversationsRefresh}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /eliminar/i }));
		const confirmButton = screen.getByRole("button", { name: "Eliminar" });
		await user.click(confirmButton);

		await waitFor(() => expect(onNewChat).toHaveBeenCalledTimes(1));
		expect(onConversationsRefresh).toHaveBeenCalledTimes(1);
		expect(fetch).toHaveBeenCalledWith(
			expect.stringContaining(`/api/conversations/${conv.id}`),
			expect.objectContaining({ method: "DELETE" }),
		);
	});

	it("mantiene la conversación y muestra error si falla la eliminación, sin llamar onNewChat", async () => {
		const user = userEvent.setup();
		const conv = makeConversation();
		(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
			ok: false,
			status: 403,
			clone: () => ({ json: async () => ({ detail: "No autorizado" }) }),
			text: async () => "",
		});
		const onNewChat = vi.fn();
		render(
			<ConversationList
				conversations={[conv]}
				activeConversationId={conv.id}
				loading={false}
				onSelectConversation={vi.fn()}
				onNewChat={onNewChat}
				onConversationsRefresh={vi.fn()}
			/>,
		);

		await openMenu(user, conv);
		await user.click(screen.getByRole("menuitem", { name: /eliminar/i }));
		await user.click(screen.getByRole("button", { name: "Eliminar" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("No autorizado");
		expect(onNewChat).not.toHaveBeenCalled();
		// La confirmación de borrado sigue visible (no se descartó el estado).
		expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
	});
});
