import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	createAdminUser, generateConversationTitle, listAdminUsers, queryRagStream,
	submitConversationFeedback, submitMessageFeedback, updateAdminUserPassword,
} from "@/lib/api";
import { getToken, setAuth } from "@/lib/auth";

const fetchMock = vi.fn<typeof fetch>();
const conversationFeedback = { ratings: { tone: 4, length: 4, usability: 4, overall: 4 } };
const messageFeedback = { conversation_id: "conv-A", message_id: "message-A", ratings: { pertinence: 4, accuracy: 4 } };
async function query(token: string | null) {
	for await (const event of queryRagStream({ question: "A" }, undefined, token)) void event;
}
const operations: Array<[string, (token: string | null) => Promise<unknown>]> = [
	["list", (token) => listAdminUsers(token)],
	["create", (token) => createAdminUser({ email: "a@example.test", password: "synthetic" }, token)],
	["password", (token) => updateAdminUserPassword("uid-A", "synthetic", token)],
	["conversation-feedback", (token) => submitConversationFeedback(conversationFeedback, token)],
	["message-feedback", (token) => submitMessageFeedback(messageFeedback, token)],
	["query", query],
];
beforeEach(() => {
	localStorage.clear();
	setAuth("token-B", { user_id: "B", email: "b@example.test", display_name: null, role: "user" });
	fetchMock.mockReset();
	vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

describe("API — credencial capturada por la UI", () => {
	it.each(operations)("%s no sustituye null explícito por la sesión B", async (_name, operation) => {
		await expect(operation(null)).rejects.toThrow("sesión no es válida");
		expect(fetchMock).not.toHaveBeenCalled();
		expect(getToken()).toBe("token-B");
	});

	it.each(operations)("%s conserva token A y su 401 no expira B", async (_name, operation) => {
		fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }));
		await expect(operation("token-A")).rejects.toThrow();
		expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBe("Bearer token-A");
		expect(getToken()).toBe("token-B");
	});

	it("el título conserva su fallback silencioso sin enviar null ni usar B", async () => {
		await expect(generateConversationTitle("Pregunta de A", "conv-A", null)).resolves.toBe("Pregunta de A");
		expect(fetchMock).not.toHaveBeenCalled();
	});
});
