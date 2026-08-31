import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { MAX_QUESTION_CHARS } from "@/lib/contracts";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const STABLE_USER = { user_id: "u1", email: "user@example.com", display_name: null, role: "user" };

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER }),
}));

vi.mock("@/lib/api", () => ({
	queryRagStream: vi.fn(),
	throwIfSessionExpired: vi.fn(async () => {}),
}));

describe("useChat — submit(): límite de 4.000 caracteres (A7, defensa en profundidad)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("rechaza una pregunta que supera el límite: no crea conversación, no persiste nada, y avisa del error", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		const { result } = renderHook(() => useChat());

		const tooLong = "x".repeat(MAX_QUESTION_CHARS + 1);
		await act(async () => {
			await result.current.submit(tooLong);
		});

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.current.messages).toHaveLength(0);
		expect(result.current.error).toBe(
			`La pregunta no puede superar ${MAX_QUESTION_CHARS} caracteres.`,
		);
		expect(result.current.loading).toBe(false);
	});

	it("acepta una pregunta exactamente en el límite (no la rechaza de más)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValueOnce(
			new Response(JSON.stringify({ id: "conv-1" }), { status: 200 }),
		);
		const { result } = renderHook(() => useChat());

		const exact = "x".repeat(MAX_QUESTION_CHARS);
		await act(async () => {
			// No importa que la llamada quede a medias (la creación de
			// conversación es la única solicitud simulada): lo que se
			// verifica es que SÍ intentó proceder, a diferencia del caso
			// anterior.
			await result.current.submit(exact).catch(() => {});
		});

		expect(fetchMock).toHaveBeenCalled();
		expect(result.current.error).not.toBe(
			`La pregunta no puede superar ${MAX_QUESTION_CHARS} caracteres.`,
		);
	});
});
