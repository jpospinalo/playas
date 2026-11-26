import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationList } from "@/components/chat/ConversationList";
import type { Conversation } from "@/hooks/useConversations";
import { useChat } from "@/hooks/useChat";

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: { user_id: "test-user", email: "test@example.test", display_name: null, role: "admin" } }),
}));

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	getTokenForUser: vi.fn(() => "test-token"),
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

function deferredResponse() {
	let resolve!: (response: Response) => void;
	const promise = new Promise<Response>((complete) => { resolve = complete; });
	return { promise, resolve };
}

const conversationA = makeConversation({ id: "conv-A", title: "Conversación A", threadId: "thread-A" });
const conversationB = makeConversation({ id: "conv-B", title: "Conversación B", threadId: "thread-B" });
const conversationC = makeConversation({ id: "conv-C", title: "Conversación C", threadId: "thread-C" });

function historyResponse(conversation: Conversation): Response {
	return new Response(JSON.stringify([
		{ id: `message-${conversation.id}`, role: "assistant", text: `Texto de ${conversation.title}`, sources: null },
	]), { status: 200, headers: { "Content-Type": "application/json" } });
}

function installDeferredDelete(
	historyB: Response | Promise<Response> = historyResponse(conversationB),
	historyA: Response | Promise<Response> = historyResponse(conversationA),
) {
	const deletion = deferredResponse();
	vi.mocked(fetch).mockImplementation(async (url, init) => {
		if (init?.method === "DELETE") return deletion.promise;
		if (String(url).endsWith("/conv-A/messages")) return historyA;
		if (String(url).endsWith("/conv-B/messages")) return historyB;
		if (String(url).endsWith("/conv-C/messages")) return historyResponse(conversationC);
		throw new Error(`Solicitud inesperada: ${String(url)}`);
	});
	return deletion;
}

function ConversationHarness({
	initial,
	onNewChat,
}: {
	initial: Conversation;
	onNewChat: () => void;
}) {
	const chat = useChat();
	return (
		<>
			<button type="button" onClick={() => chat.loadConversation(initial)}>Cargar inicial</button>
			<button type="button" onClick={() => chat.loadConversation(conversationC)}>Selección externa C</button>
			<button type="button" onClick={() => { onNewChat(); chat.resetChat(); }}>Nueva desde fuera</button>
			<input aria-label="Borrador" value={chat.input} onChange={(event) => chat.setInput(event.target.value)} />
			<output data-testid="active-conversation">{chat.conversationId ?? "nuevo"}</output>
			<output data-testid="chat-messages">{chat.messages.map((message) => message.text).join(" | ")}</output>
			<output data-testid="chat-loading">{String(chat.loading)}</output>
			{chat.error && <p data-testid="chat-error">{chat.error}</p>}
			<ConversationList
				conversations={[conversationA, conversationB]}
				activeConversationId={chat.conversationId}
				loading={false}
				onSelectConversation={chat.loadConversation}
				onNewChat={() => { onNewChat(); chat.resetChat(); }}
				onConversationDeleted={chat.handleConversationDeleted}
				onConversationsRefresh={async () => {}}
			/>
		</>
	);
}

async function mountHarness(user: ReturnType<typeof userEvent.setup>, initial = conversationA) {
	const onNewChat = vi.fn();
	render(<ConversationHarness initial={initial} onNewChat={onNewChat} />);
	await user.click(screen.getByRole("button", { name: "Cargar inicial" }));
	await waitFor(() => expect(screen.getByTestId("active-conversation")).toHaveTextContent(initial.id));
	return onNewChat;
}

async function startDelete(user: ReturnType<typeof userEvent.setup>, conversation: Conversation) {
	await openMenu(user, conversation);
	await user.click(screen.getByRole("button", { name: /eliminar/i }));
	await user.click(screen.getByRole("button", { name: "Eliminar" }));
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
		await user.click(screen.getByRole("button", { name: /renombrar/i }));
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
		await user.click(screen.getByRole("button", { name: /renombrar/i }));
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
			// Cuerpo de texto plano real: `.json()` debe rechazar (como lo haría
			// una `Response` real cuyo texto no es JSON válido), no resolver a
			// `{}`. `readErrorDetail` cae a `.text()` en ese caso.
			clone: () => ({
				json: async () => {
					throw new SyntaxError("Unexpected token 'f', \"fallo simu\"... is not valid JSON");
				},
			}),
			text: async () => "fallo simulado del servidor",
			headers: new Headers({ "Content-Type": "text/plain" }),
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
		await user.click(screen.getByRole("button", { name: /renombrar/i }));
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
		await user.click(screen.getByRole("button", { name: /renombrar/i }));
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
		await user.click(screen.getByRole("button", { name: /eliminar/i }));
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
		await user.click(screen.getByRole("button", { name: /eliminar/i }));
		await user.click(screen.getByRole("button", { name: "Eliminar" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("No autorizado");
		expect(onNewChat).not.toHaveBeenCalled();
		// La confirmación de borrado sigue visible (no se descartó el estado).
		expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
	});

	it("borrar A no reinicia B si B terminó de cargar durante el DELETE", async () => {
		const user = userEvent.setup();
		const deletion = installDeferredDelete();
		const onNewChat = await mountHarness(user);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación B" }));
		await waitFor(() => expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-B"));
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(onNewChat).not.toHaveBeenCalled();
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-B");
		expect(screen.getByTestId("chat-messages")).toHaveTextContent("Texto de Conversación B");
	});

	it("borrar A no cancela B mientras su historial sigue pendiente", async () => {
		const user = userEvent.setup();
		const historyB = deferredResponse();
		const deletion = installDeferredDelete(historyB.promise);
		const onNewChat = await mountHarness(user);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación B" }));
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("true");
		const loadingSignal = vi.mocked(fetch).mock.calls.find(([url]) =>
			String(url).endsWith("/conv-B/messages"),
		)?.[1]?.signal;
		expect(loadingSignal).toBeDefined();
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(onNewChat).not.toHaveBeenCalled();
		expect(loadingSignal?.aborted).toBe(false);
		await act(async () => { historyB.resolve(historyResponse(conversationB)); });
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-B");
		expect(screen.getByTestId("chat-messages")).toHaveTextContent("Texto de Conversación B");
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("false");
	});

	it("descarta A si se abrió A mientras se confirmaba su borrado desde B", async () => {
		const user = userEvent.setup();
		const deletion = installDeferredDelete();
		await mountHarness(user, conversationB);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación A" }));
		await waitFor(() => expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-A"));
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("nuevo");
		expect(screen.getByTestId("chat-messages")).toBeEmptyDOMElement();
	});

	it("una carga fallida conserva A y borrar B no descarta esa vista", async () => {
		const user = userEvent.setup();
		const deletion = installDeferredDelete(new Response(null, { status: 500 }));
		const onNewChat = await mountHarness(user);
		await startDelete(user, conversationB);
		await user.click(screen.getByRole("button", { name: "Conversación B" }));
		await waitFor(() => expect(screen.getByTestId("chat-error")).toHaveTextContent("No fue posible cargar"));
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(onNewChat).not.toHaveBeenCalled();
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-A");
		expect(screen.getByTestId("chat-messages")).toHaveTextContent("Texto de Conversación A");
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("false");
	});

	it("si B falla después de borrar A, no restaura la vista eliminada ni cancela B", async () => {
		const user = userEvent.setup();
		const historyB = deferredResponse();
		const deletion = installDeferredDelete(historyB.promise);
		await mountHarness(user);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación B" }));
		const loadingSignal = vi.mocked(fetch).mock.calls.find(([url]) =>
			String(url).endsWith("/conv-B/messages"),
		)?.[1]?.signal;
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(loadingSignal?.aborted).toBe(false);
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("true");
		await act(async () => { historyB.resolve(new Response(null, { status: 500 })); });
		expect(screen.getByTestId("chat-error")).toHaveTextContent("No fue posible cargar");
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("nuevo");
		expect(screen.getByTestId("chat-messages")).toBeEmptyDOMElement();
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("false");
	});

	it("borrar el destino A pendiente cancela sólo su carga y conserva B visible", async () => {
		const user = userEvent.setup();
		const historyA = deferredResponse();
		const deletion = installDeferredDelete(historyResponse(conversationB), historyA.promise);
		await mountHarness(user, conversationB);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación A" }));
		const loadingSignal = vi.mocked(fetch).mock.calls.find(([url]) =>
			String(url).endsWith("/conv-A/messages"),
		)?.[1]?.signal;
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(loadingSignal?.aborted).toBe(true);
		await act(async () => { historyA.resolve(historyResponse(conversationA)); });
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-B");
		expect(screen.getByTestId("chat-messages")).toHaveTextContent("Texto de Conversación B");
		expect(screen.getByTestId("chat-loading")).toHaveTextContent("false");
	});

	it("un DELETE tardío no borra el borrador de una consulta nueva", async () => {
		const user = userEvent.setup();
		const deletion = installDeferredDelete();
		const onNewChat = await mountHarness(user);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Nueva desde fuera" }));
		await user.type(screen.getByRole("textbox", { name: "Borrador" }), "Borrador nuevo");
		await act(async () => { deletion.resolve(new Response(null, { status: 204 })); });
		expect(onNewChat).toHaveBeenCalledTimes(1);
		expect(screen.getByRole("textbox", { name: "Borrador" })).toHaveValue("Borrador nuevo");
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("nuevo");
	});

	it("una selección externa C supera a B pendiente y sobrevive al DELETE de A", async () => {
		const user = userEvent.setup();
		const historyB = deferredResponse();
		const deletion = installDeferredDelete(historyB.promise);
		await mountHarness(user);
		await startDelete(user, conversationA);
		await user.click(screen.getByRole("button", { name: "Conversación B" }));
		await user.click(screen.getByRole("button", { name: "Selección externa C" }));
		await waitFor(() => expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-C"));
		await act(async () => {
			deletion.resolve(new Response(null, { status: 204 }));
			historyB.resolve(historyResponse(conversationB));
		});
		expect(screen.getByTestId("active-conversation")).toHaveTextContent("conv-C");
		expect(screen.getByTestId("chat-messages")).toHaveTextContent("Texto de Conversación C");
	});
});

describe("ConversationList — nombres y teclado de acciones ordinarias", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	function renderActions() {
		const conv = makeConversation();
		const onConversationsRefresh = vi.fn();
		render(
			<>
				<ConversationList
					conversations={[conv]}
					activeConversationId={conv.id}
					loading={false}
					onSelectConversation={vi.fn()}
					onNewChat={vi.fn()}
					onConversationsRefresh={onConversationsRefresh}
				/>
				<div role="dialog" aria-label="Otro diálogo">
					<input aria-label="Campo de otro diálogo" />
				</div>
			</>,
		);
		return { conv, onConversationsRefresh };
	}

	it("el renombrado expone un nombre accesible y recibe el foco de la acción", async () => {
		const user = userEvent.setup();
		const { conv } = renderActions();
		await openMenu(user, conv);
		await user.click(screen.getByText("Renombrar", { exact: true }));
		const input = screen.getByRole("textbox", { name: "Título de la conversación" });
		expect(input).toHaveValue(conv.title);
		expect(input).toHaveFocus();
	});

	it("las acciones son botones ordinarios recorribles con Tab y Shift+Tab", async () => {
		const user = userEvent.setup();
		renderActions();
		const trigger = screen.getByRole("button", { name: "Opciones para Título original" });
		expect(trigger).toHaveAttribute("aria-expanded", "false");
		trigger.focus();
		await user.keyboard("{Enter}");
		expect(trigger).toHaveAttribute("aria-expanded", "true");
		const rename = screen.getByText("Renombrar", { exact: true });
		const remove = screen.getByText("Eliminar", { exact: true });
		await user.tab();
		expect(rename).toHaveFocus();
		await user.tab();
		expect(remove).toHaveFocus();
		await user.tab({ shift: true });
		expect(rename).toHaveFocus();
		expect(screen.getByRole("button", { name: "Renombrar" })).toBe(rename);
		expect(screen.getByRole("button", { name: "Eliminar" })).toBe(remove);
		expect(screen.queryByRole("menu")).not.toBeInTheDocument();
		expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
		expect(trigger).not.toHaveAttribute("aria-haspopup");
	});

	it("Escape desde una acción cierra el desplegable y devuelve foco al disparador conectado", async () => {
		const user = userEvent.setup();
		renderActions();
		const trigger = screen.getByRole("button", { name: "Opciones para Título original" });
		trigger.focus();
		await user.keyboard(" ");
		expect(trigger).toHaveAttribute("aria-expanded", "true");
		await user.tab();
		expect(screen.getByText("Renombrar", { exact: true })).toHaveFocus();
		await user.keyboard("{Escape}");
		await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
		await waitFor(() => expect(trigger).toHaveFocus());
		expect(fetch).not.toHaveBeenCalled();
	});

	it("Escape en otro diálogo no roba su foco al cerrar acciones abiertas", async () => {
		const user = userEvent.setup();
		const { conv } = renderActions();
		await openMenu(user, conv);
		const trigger = screen.getByRole("button", { name: "Opciones para Título original" });
		const otherInput = screen.getByRole("textbox", { name: "Campo de otro diálogo" });
		otherInput.focus();
		expect(trigger).toHaveAttribute("aria-expanded", "true");
		await user.keyboard("{Escape}");
		expect(otherInput).toHaveFocus();
		expect(fetch).not.toHaveBeenCalled();
	});

	it("Escape al renombrar descarta el borrador sin envío ni devolución de foco a un disparador retirado", async () => {
		const user = userEvent.setup();
		const { conv, onConversationsRefresh } = renderActions();
		await openMenu(user, conv);
		await user.click(screen.getByText("Renombrar", { exact: true }));
		const input = screen.getByDisplayValue("Título original");
		expect(input).toHaveFocus();
		await user.clear(input);
		await user.type(input, "Borrador no guardado");
		await user.keyboard("{Escape}");
		expect(screen.queryByDisplayValue("Borrador no guardado")).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Título original" })).toBeInTheDocument();
		expect(fetch).not.toHaveBeenCalled();
		expect(onConversationsRefresh).not.toHaveBeenCalled();
	});

	it("un conflicto 409 al renombrar conserva borrador, selección y error local", async () => {
		vi.mocked(fetch).mockResolvedValue(new Response(
			JSON.stringify({ detail: "La conversación está en uso." }),
			{ status: 409, headers: { "Content-Type": "application/json" } },
		));
		const user = userEvent.setup();
		const { conv, onConversationsRefresh } = renderActions();
		await openMenu(user, conv);
		await user.click(screen.getByText("Renombrar", { exact: true }));
		const input = screen.getByDisplayValue("Título original");
		await user.clear(input);
		await user.type(input, "Título pendiente");
		await user.keyboard("{Enter}");
		expect(await screen.findByRole("alert")).toHaveTextContent("La conversación está en uso.");
		expect(input).toHaveValue("Título pendiente");
		expect(input.closest("li")).toHaveAttribute("aria-current", "true");
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch).toHaveBeenCalledWith(
			expect.stringContaining(`/api/conversations/${conv.id}`),
			expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "Título pendiente" }) }),
		);
		expect(onConversationsRefresh).not.toHaveBeenCalled();
	});
});
