import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MessageRatingPopover } from "@/components/chat/MessageRatingPopover";
import { useChat } from "@/hooks/useChat";
import type { Conversation } from "@/hooks/useConversations";
import { clearAuth, getToken, setAuth } from "@/lib/auth";

const identity = vi.hoisted(() => ({
	user: { user_id: "A", email: "a@example.test", display_name: "A", role: "user" },
}));

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: identity.user }),
}));

const accountB = { user_id: "B", email: "b@example.test", display_name: "B", role: "user" };
const conversationA: Conversation = {
	id: "conv-A", title: "A", threadId: "thread-A", createdAt: new Date(), updatedAt: new Date(), messageCount: 1,
};
const fetchMock = vi.fn<typeof fetch>();
const ratings = { pertinence: 5, accuracy: 4 };

function json(body: unknown, status = 200) {
	return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function deferredResponse() {
	let resolve!: (response: Response) => void;
	const promise = new Promise<Response>((complete) => { resolve = complete; });
	return { promise, resolve };
}

function feedbackCalls() {
	return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/feedback/message"));
}

function assertCapturedContext() {
	expect(feedbackCalls()).toHaveLength(1);
	const [, init] = feedbackCalls()[0];
	expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-A");
	expect(JSON.parse(String(init?.body))).toEqual({
		conversation_id: "conv-A", message_id: "message-A", ratings, expected_answer: "Respuesta esperada",
	});
}

function FeedbackHarness() {
	const chat = useChat();
	return (
		<>
			<button type="button" onClick={() => chat.loadConversation(conversationA)}>Cargar A</button>
			<span data-testid="rated">{String(chat.ratedMessageIds.has("message-A"))}</span>
			<span data-testid="active">{chat.conversationId ?? "nuevo"}</span>
			<MessageRatingPopover
				open
				onSubmit={(value, expectedAnswer) => chat.rateMessage("message-A", value, expectedAnswer)}
				onClose={() => {}}
			/>
		</>
	);
}

function SessionHarness() {
	return <FeedbackHarness key={identity.user.user_id} />;
}

async function selectRatings(user: ReturnType<typeof userEvent.setup>) {
	await user.click(screen.getByRole("group", { name: "Pertinencia de la respuesta" }).querySelectorAll("button")[4]);
	await user.click(screen.getByRole("group", { name: "Precisión de la respuesta" }).querySelectorAll("button")[3]);
	await user.type(screen.getByLabelText(/Respuesta esperada/), "Respuesta esperada");
}

async function loadConversation(user: ReturnType<typeof userEvent.setup>) {
	await user.click(screen.getByRole("button", { name: "Cargar A" }));
	await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("conv-A"));
}

beforeEach(() => {
	identity.user = { user_id: "A", email: "a@example.test", display_name: "A", role: "user" };
	localStorage.clear();
	setAuth("token-A", identity.user);
	fetchMock.mockReset().mockImplementation(async (url) => {
		if (String(url).endsWith("/api/conversations/conv-A/messages")) {
			return json([{ id: "message-A", role: "assistant", text: "Respuesta A", sources: null }]);
		}
		if (String(url).endsWith("/api/feedback/message")) return json({ id: "feedback-A" }, 201);
		throw new Error(`Solicitud inesperada: ${String(url)}`);
	});
	vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	localStorage.clear();
});

describe("useChat y popover — confirmación real del feedback", () => {
	it.each(["missing", "other-session"])("sin credencial ligada (%s) muestra error y conserva el formulario", async (credential) => {
		const user = userEvent.setup();
		render(<SessionHarness />);
		await loadConversation(user);
		await selectRatings(user);
		fetchMock.mockClear();
		if (credential === "missing") clearAuth();
		else setAuth("token-B", accountB); // La UI de A aún no recibió storage.
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo enviar la calificación");
		expect(screen.queryByText("¡Gracias por tu calificación!")).not.toBeInTheDocument();
		expect(screen.getByTestId("rated")).toHaveTextContent("false");
		expect(screen.getByLabelText(/Respuesta esperada/)).toHaveValue("Respuesta esperada");
		expect(fetchMock).not.toHaveBeenCalled();
		if (credential === "other-session") expect(getToken()).toBe("token-B");
	});

	it("sin conversación no agradece, no envía y no marca el mensaje", async () => {
		const user = userEvent.setup();
		render(<SessionHarness />);
		await selectRatings(user);
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo enviar la calificación");
		expect(screen.queryByText("¡Gracias por tu calificación!")).not.toBeInTheDocument();
		expect(screen.getByTestId("rated")).toHaveTextContent("false");
		expect(fetchMock).not.toHaveBeenCalled();
		expect(getToken()).toBe("token-A");
	});

	it.each([201, 409])("el resultado HTTP %i conserva su significado en la UI", async (status) => {
		const user = userEvent.setup();
		render(<SessionHarness />);
		await loadConversation(user);
		await selectRatings(user);
		fetchMock.mockClear().mockResolvedValueOnce(json(
			status === 201 ? { id: "feedback-A" } : { detail: "Ya existe feedback para este mensaje." }, status,
		));
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		if (status === 201) {
			expect(await screen.findByRole("status")).toHaveTextContent("¡Gracias por tu calificación!");
			expect(screen.getByTestId("rated")).toHaveTextContent("true");
		} else {
			expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo enviar la calificación");
			expect(screen.queryByText("¡Gracias por tu calificación!")).not.toBeInTheDocument();
			expect(screen.getByTestId("rated")).toHaveTextContent("false");
			expect(getToken()).toBe("token-A");
		}
		assertCapturedContext();
	});

	it("captura conversación y credencial antes del import aunque luego se reinicie la vista", async () => {
		const { result } = renderHook(() => useChat());
		await act(async () => { await result.current.loadConversation(conversationA); });
		fetchMock.mockClear();
		let submitted!: Promise<void>;
		act(() => {
			submitted = result.current.rateMessage("message-A", ratings, "Respuesta esperada");
			result.current.resetChat();
			setAuth("token-B", accountB);
		});
		await act(async () => { await submitted; });
		assertCapturedContext();
		expect(getToken()).toBe("token-B");
		expect(result.current.conversationId).toBeNull();
	});

	it.each([201, 401])("un envío A admitido mantiene el destino y no expira B al responder %i", async (status) => {
		const user = userEvent.setup();
		const pending = deferredResponse();
		render(<SessionHarness />);
		await loadConversation(user);
		await selectRatings(user);
		fetchMock.mockClear().mockImplementationOnce(() => pending.promise);
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		await waitFor(() => expect(feedbackCalls()).toHaveLength(1));
		setAuth("token-B", accountB); // Sigue montada A hasta el evento storage.
		await act(async () => { pending.resolve(json({ id: "feedback-A" }, status)); });
		if (status === 201) {
			expect(await screen.findByRole("status")).toHaveTextContent("¡Gracias por tu calificación!");
			expect(screen.getByTestId("rated")).toHaveTextContent("true");
		} else {
			expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo enviar la calificación");
			expect(screen.queryByText("¡Gracias por tu calificación!")).not.toBeInTheDocument();
			expect(screen.getByTestId("rated")).toHaveTextContent("false");
		}
		assertCapturedContext();
		expect(getToken()).toBe("token-B");
	});

	it("al remontar B, la confirmación tardía de A no marca ni agradece en B", async () => {
		const user = userEvent.setup();
		const pending = deferredResponse();
		const view = render(<SessionHarness />);
		await loadConversation(user);
		await selectRatings(user);
		fetchMock.mockClear().mockImplementationOnce(() => pending.promise);
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		await waitFor(() => expect(feedbackCalls()).toHaveLength(1));
		setAuth("token-B", accountB);
		identity.user = accountB;
		view.rerender(<SessionHarness />);
		await act(async () => { pending.resolve(json({ id: "feedback-A" }, 201)); });
		assertCapturedContext();
		expect(screen.queryByText("¡Gracias por tu calificación!")).not.toBeInTheDocument();
		expect(screen.getByTestId("rated")).toHaveTextContent("false");
		expect(screen.getByTestId("active")).toHaveTextContent("nuevo");
		expect(getToken()).toBe("token-B");
	});
});
