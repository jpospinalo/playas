import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { queryRagStream } from "@/lib/api";

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

function jsonResponse(body: unknown, status = 200) {
	return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

async function* failingStream() {
	yield { type: "token", content: "Respuesta parc" } as const;
	throw new Error("Conexión perdida durante el streaming.");
}

async function* okStream() {
	yield { type: "token", content: "Respuesta completa." } as const;
	yield { type: "sources", sources: [] } as const;
}

describe("useChat — submit(): fallo de streaming vs. fallo de persistencia (A5)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("un fallo DURANTE el streaming descarta la respuesta incompleta y muestra un error", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })); // persistir pregunta

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => failingStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		// A5 — sin respuesta completa, no queda ningún mensaje de asistente
		// (parcial) presentado como si fuera la respuesta final.
		expect(result.current.messages.some((m) => m.role === "assistant")).toBe(
			false,
		);
		expect(result.current.error).toBe("Conexión perdida durante el streaming.");
	});

	it("un fallo SOLO al guardar (streaming ya completo) conserva la respuesta visible, marcada como no guardada", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })) // persistir pregunta
			.mockResolvedValue(jsonResponse({}, 500)); // guardar respuesta: falla (con reintento interno)

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		const assistantMsg = result.current.messages.find(
			(m) => m.role === "assistant",
		);
		expect(assistantMsg).toBeDefined();
		expect(assistantMsg?.text).toBe("Respuesta completa.");
		expect(assistantMsg?.persistenceStatus).toBe("failed");
		// A5 — a diferencia de un fallo de streaming, esto NO dispara el
		// banner de error general del chat: la respuesta ya se generó bien.
		expect(result.current.error).toBeNull();
	});

	it("retryPersistMessage() reintenta manualmente y, si tiene éxito, limpia persistenceStatus", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValue(jsonResponse({}, 500));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		const failedId = result.current.messages.find(
			(m) => m.role === "assistant",
		)?.id;
		expect(failedId).toBeDefined();

		fetchMock.mockReset();
		fetchMock.mockResolvedValue(jsonResponse({ id: "assistant-msg-saved" }));

		await act(async () => {
			await result.current.retryPersistMessage(failedId!);
		});

		const savedMsg = result.current.messages.find(
			(m) => m.id === "assistant-msg-saved",
		);
		expect(savedMsg).toBeDefined();
		expect(savedMsg?.persistenceStatus).toBeUndefined();
	});

	it("retryPersistMessage() no dispara una segunda solicitud mientras la primera sigue en curso", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValue(jsonResponse({}, 500));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());
		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		const failedId = result.current.messages.find(
			(m) => m.role === "assistant",
		)?.id;

		fetchMock.mockReset();
		let resolveRetry: (r: Response) => void = () => {};
		const pending = new Promise<Response>((resolve) => {
			resolveRetry = resolve;
		});
		fetchMock.mockReturnValue(pending);

		let firstRetryCallCount = 0;
		act(() => {
			void result.current.retryPersistMessage(failedId!).then(() => {
				firstRetryCallCount += 1;
			});
		});
		await waitFor(() => expect(result.current.persistingMessageIds.has(failedId!)).toBe(true));

		// Segundo llamado mientras el primero sigue en vuelo: no debe agregar
		// una solicitud adicional.
		await act(async () => {
			await result.current.retryPersistMessage(failedId!);
		});
		expect(fetchMock).toHaveBeenCalledTimes(1);

		await act(async () => {
			resolveRetry(jsonResponse({ id: "assistant-msg-saved" }));
			await pending;
		});
		expect(firstRetryCallCount).toBe(1);
	});
});

// jsdom implementa `DOMException` en un realm cuyo `Error` no coincide con
// el `Error` global que usa el resto del módulo bajo prueba: una instancia
// real de `DOMException` allí falla `instanceof Error`, aunque
// `instanceof DOMException` siga funcionando. En un navegador real (un
// único realm) esto no ocurre — `AbortSignal.timeout()` produce un
// `DOMException` que SÍ es `instanceof Error`. Este reemplazo, activo solo
// dentro de cada prueba que lo usa (`vi.unstubAllGlobals()` ya lo revierte
// en el `afterEach` existente), reproduce ese comportamiento de navegador
// real para ejercitar el límite de presentación tal como se comporta en
// producción.
class TimeoutDOMException extends Error {
	constructor(message: string, name: string) {
		super(message);
		this.name = name;
	}
}

describe("useChat — submit(): timeout REST en la creación de la conversación y en el guardado de la pregunta", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
		vi.stubGlobal("DOMException", TimeoutDOMException);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("un timeout al crear la conversación muestra el mensaje controlado, no el texto nativo del DOMException", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockRejectedValueOnce(
			new DOMException("The operation was aborted due to timeout", "TimeoutError"),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		expect(result.current.error).toBe(
			"La solicitud tardó demasiado. Intenta nuevamente.",
		);
		// La pregunta optimista se retira: no queda ningún mensaje colgado de
		// una conversación que nunca llegó a crearse.
		expect(result.current.messages).toHaveLength(0);
		// El texto se restaura en el input para que la persona no lo pierda.
		expect(result.current.input).toBe("¿Qué dice la norma?");
		expect(result.current.loading).toBe(false);
		// Sin conversación creada, nunca debió iniciarse el stream.
		expect(queryRagStream).not.toHaveBeenCalled();
	});

	it("un timeout al persistir la pregunta (dos intentos agotados) muestra el mensaje controlado, no el texto nativo del DOMException", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation
			.mockRejectedValueOnce(
				new DOMException("The operation was aborted due to timeout", "TimeoutError"),
			) // persistMessage intento 1
			.mockRejectedValueOnce(
				new DOMException("The operation was aborted due to timeout", "TimeoutError"),
			); // persistMessage intento 2

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		expect(result.current.error).toBe(
			"La solicitud tardó demasiado. Intenta nuevamente.",
		);
		expect(result.current.messages).toHaveLength(0);
		expect(result.current.input).toBe("¿Qué dice la norma?");
		expect(result.current.loading).toBe(false);
		expect(queryRagStream).not.toHaveBeenCalled();
		// Exactamente dos intentos de persistencia (más la creación previa):
		// la política de reintentos de `persistMessage` no cambió.
		expect(fetchMock).toHaveBeenCalledTimes(3);
	});
});
