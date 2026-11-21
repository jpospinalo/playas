import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationList } from "@/components/chat/ConversationList";
import { FeedbackModal } from "@/components/chat/FeedbackModal";
import AdminPage from "@/app/admin/page";
import FeedbackPage from "@/app/admin/feedback/page";
import MessageFeedbackPage from "@/app/admin/message-feedback/page";
import UsuariosPage from "@/app/admin/usuarios/page";
import { setAuth } from "@/lib/auth";

const identity = vi.hoisted(() => ({ user: { user_id: "A", email: "a@example.test", display_name: "A", user_type: null, role: "admin" } }));
vi.mock("@/components/providers/AuthProvider", () => ({ useAuth: () => ({ user: identity.user, role: "admin" }) }));

const conversation = { id: "conv-A", title: "Chat de A", threadId: "thread-A", createdAt: new Date(), updatedAt: new Date(), messageCount: 2 };
const accountB = { user_id: "B", email: "b@example.test", display_name: "B", user_type: null, role: "admin" };
const fetchMock = vi.fn<typeof fetch>();

function switchBeforeStorage() {
	// The UI still belongs to A: deliberately do not deliver StorageEvent yet.
	setAuth("token-B", accountB);
}

beforeEach(() => {
	localStorage.clear();
	setAuth("token-A", identity.user);
	fetchMock.mockReset();
	fetchMock.mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0, avg_ratings: { tone: 0, length: 0, usability: 0, overall: 0, pertinence: 0, accuracy: 0 }, distributions: {} }), { status: 200 }));
	vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

function renderList() {
	render(<ConversationList conversations={[conversation]} activeConversationId={null} loading={false} onSelectConversation={vi.fn()} onNewChat={vi.fn()} />);
}

describe("Operaciones UI con la identidad que el usuario ve", () => {
	it.each(["rename", "delete"])("no envía %s de A usando el JWT B antes de storage", async (action) => {
		const user = userEvent.setup();
		renderList();
		await user.click(screen.getByRole("button", { name: "Opciones para Chat de A" }));
		await user.click(screen.getByRole("menuitem", { name: action === "rename" ? "Renombrar" : "Eliminar" }));
		if (action === "rename") {
			await user.clear(screen.getByDisplayValue("Chat de A"));
			await user.type(screen.getByRole("textbox"), "Título nuevo");
			switchBeforeStorage();
			await user.keyboard("{Enter}");
		} else {
			switchBeforeStorage();
			await user.click(screen.getByRole("button", { name: /^Eliminar$/ }));
		}
		expect(fetchMock).not.toHaveBeenCalled();
		expect(localStorage.getItem("atlas_token")).toBe("token-B");
	});

	it("no guarda feedback de la conversación A con la sesión B", async () => {
		const user = userEvent.setup();
		render(<FeedbackModal open conversationId="conv-A" onClose={vi.fn()} />);
		for (const label of ["Tono de las respuestas", "Longitud de las respuestas", "Usabilidad del sistema", "Calificación general"]) {
			await user.click(screen.getByRole("group", { name: label }).querySelectorAll("button")[4]);
		}
		switchBeforeStorage();
		await user.click(screen.getByRole("button", { name: "Enviar calificación" }));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it.each([
		["dashboard", AdminPage],
		["feedback", FeedbackPage],
		["message feedback", MessageFeedbackPage],
		["users", UsuariosPage],
	] as const)("no consulta %s con una identidad distinta antes de storage", async (_name, Page) => {
		switchBeforeStorage();
		render(<Page />);
		await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it.each(["create", "password"])("no ejecuta %s de usuario bajo B desde un modal de A", async (action) => {
		const user = userEvent.setup();
		fetchMock.mockImplementation(async () => new Response(JSON.stringify({ items: [{ uid: "target-user", email: "target@example.test", displayName: null, role: "user", createdAt: "2026-01-01T00:00:00Z" }], total: 1 }), { status: 200 }));
		render(<UsuariosPage />);
		await screen.findByText("target@example.test");
		await user.click(screen.getByRole("button", { name: action === "create" ? "Crear usuario" : "Cambiar contraseña" }));
		const dialog = screen.getByRole("dialog");
		if (action === "create") await user.type(screen.getByLabelText("Email"), "new@example.test");
		for (const input of dialog.querySelectorAll<HTMLInputElement>('input[type="password"]')) await user.type(input, "Synthetic12345");
		fetchMock.mockClear();
		switchBeforeStorage();
		await user.click(screen.getByRole("button", { name: action === "create" ? "Crear" : "Actualizar" }));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("una operación legítima conserva el token de A", async () => {
		const user = userEvent.setup();
		renderList();
		await user.click(screen.getByRole("button", { name: "Opciones para Chat de A" }));
		await user.click(screen.getByRole("menuitem", { name: "Eliminar" }));
		await user.click(screen.getByRole("button", { name: /^Eliminar$/ }));
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fetchMock.mock.calls[0][1]?.headers).toEqual({ Authorization: "Bearer token-A" });
	});
});
