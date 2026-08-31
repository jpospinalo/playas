import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MessageFeedbackPage from "@/app/admin/message-feedback/page";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

function emptyResponse() {
	return {
		items: [],
		total: 0,
		avg_ratings: { pertinence: 0, accuracy: 0 },
		distributions: { pertinence: {}, accuracy: {} },
	};
}

function jsonResponse(body: unknown, status = 200) {
	return {
		ok: status >= 200 && status < 300,
		status,
		json: async () => body,
	} as Response;
}

describe("MessageFeedbackPage — filtros administrativos (A3)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("aplicar filtros dispara exactamente una solicitud con los parámetros correctos", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<MessageFeedbackPage />);

		// Carga inicial (sin filtros).
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("Pertinencia mín"), "2");
		await user.selectOptions(screen.getByLabelText("Pertinencia máx"), "4");
		await user.selectOptions(screen.getByLabelText("Precisión mín"), "3");
		await user.selectOptions(screen.getByLabelText("Precisión máx"), "5");
		await user.type(screen.getByLabelText("Desde"), "2026-08-01");
		await user.type(screen.getByLabelText("Hasta"), "2026-08-31");

		// Cambiar los borradores no debe disparar ninguna solicitud adicional
		// (regresión del bug original: `applyFilters` llamaba a `load(1)`
		// directamente Y dependía de filtros en `useCallback`, duplicando la
		// solicitud).
		expect(fetchMock).toHaveBeenCalledTimes(1);

		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		// Sigue en 2: ninguna solicitud extra causada por el cambio de `page`
		// a 1 dentro de `applyFilters`.
		await new Promise((r) => setTimeout(r, 20));
		expect(fetchMock).toHaveBeenCalledTimes(2);

		const [url] = fetchMock.mock.calls[1] as [string];
		const params = new URL(url).searchParams;
		expect(params.get("min_pertinence")).toBe("2");
		expect(params.get("max_pertinence")).toBe("4");
		expect(params.get("min_accuracy")).toBe("3");
		expect(params.get("max_accuracy")).toBe("5");
		// A3.7 — día calendario de Colombia (UTC-5), no medianoche UTC.
		expect(params.get("start_date")).toBe("2026-08-01T00:00:00.000-05:00");
		expect(params.get("end_date")).toBe("2026-08-31T23:59:59.999-05:00");
	});

	it("desmontar el componente aborta la solicitud activa (G2.1)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let capturedSignal: AbortSignal | null | undefined;
		const hanging = new Promise<Response>(() => {});
		fetchMock.mockImplementationOnce((_url: string, init?: RequestInit) => {
			capturedSignal = init?.signal;
			return hanging;
		});

		const { unmount } = render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(capturedSignal?.aborted).toBe(false);

		unmount();

		expect(capturedSignal?.aborted).toBe(true);
	});

	it("'Limpiar' resetea los borradores, vuelve a la página 1 y genera como máximo una solicitud (G2.1)", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("Pertinencia mín"), "2");
		await user.selectOptions(screen.getByLabelText("Pertinencia máx"), "4");
		await user.selectOptions(screen.getByLabelText("Precisión mín"), "3");
		await user.selectOptions(screen.getByLabelText("Precisión máx"), "5");
		await user.type(screen.getByLabelText("Desde"), "2026-08-01");
		await user.type(screen.getByLabelText("Hasta"), "2026-08-31");
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

		await user.click(screen.getByRole("button", { name: "Limpiar" }));

		expect((screen.getByLabelText("Desde") as HTMLInputElement).value).toBe(
			"",
		);
		expect((screen.getByLabelText("Hasta") as HTMLInputElement).value).toBe(
			"",
		);
		expect(
			(screen.getByLabelText("Pertinencia mín") as HTMLSelectElement).value,
		).toBe("");
		expect(
			(screen.getByLabelText("Precisión máx") as HTMLSelectElement).value,
		).toBe("");

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
		await new Promise((r) => setTimeout(r, 20));
		expect(fetchMock).toHaveBeenCalledTimes(3);

		const [clearedUrl] = fetchMock.mock.calls[2] as [string];
		const clearedParams = new URL(clearedUrl).searchParams;
		expect(clearedParams.get("min_pertinence")).toBeNull();
		expect(clearedParams.get("max_pertinence")).toBeNull();
		expect(clearedParams.get("min_accuracy")).toBeNull();
		expect(clearedParams.get("max_accuracy")).toBeNull();
		expect(clearedParams.get("start_date")).toBeNull();
		expect(clearedParams.get("end_date")).toBeNull();
	});

	it("bloquea 'Aplicar filtros' si la pertinencia mínima es mayor que la máxima", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("Pertinencia mín"), "5");
		await user.selectOptions(screen.getByLabelText("Pertinencia máx"), "2");
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		expect(await screen.findByRole("alert")).toHaveTextContent(
			/pertinencia mínima no puede ser mayor/i,
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("bloquea 'Aplicar filtros' si la precisión mínima es mayor que la máxima", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("Precisión mín"), "4");
		await user.selectOptions(screen.getByLabelText("Precisión máx"), "1");
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		expect(await screen.findByRole("alert")).toHaveTextContent(
			/precisión mínima no puede ser mayor/i,
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("bloquea 'Aplicar filtros' si «Desde» es posterior a «Hasta»", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.type(screen.getByLabelText("Desde"), "2026-08-31");
		await user.type(screen.getByLabelText("Hasta"), "2026-08-01");
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		expect(await screen.findByRole("alert")).toHaveTextContent(
			/no puede ser posterior a la fecha/i,
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("una respuesta obsoleta (cancelada) no pisa el resultado de la solicitud más reciente", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;

		let firstReject: (reason?: unknown) => void = () => {};
		const firstCall = new Promise<Response>((_resolve, reject) => {
			firstReject = reject;
		});
		fetchMock
			.mockImplementationOnce((_url: string, init?: RequestInit) => {
				init?.signal?.addEventListener("abort", () => {
					firstReject(new DOMException("Aborted", "AbortError"));
				});
				return firstCall;
			})
			.mockResolvedValueOnce(
				jsonResponse({
					...emptyResponse(),
					total: 1,
					items: [
						{
							id: "mf1",
							userId: "u1",
							userEmail: "nueva@example.com",
							conversationId: "conv-1",
							messageId: "msg-1",
							ratings: { pertinence: 5, accuracy: 5 },
							expectedAnswer: null,
							createdAt: "2026-08-20T10:00:00Z",
						},
					],
				}),
			);

		render(<MessageFeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		// Dispara una segunda solicitud (aplicar filtros) antes de que la
		// primera (carga inicial) se resuelva; debe cancelar la primera.
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		await waitFor(() =>
			expect(screen.getByText("nueva@example.com")).toBeInTheDocument(),
		);
		expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
	});

	it("preserva el expandir/contraer de la respuesta esperada (sin relación con los filtros)", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		const longAnswer = "x".repeat(80);
		fetchMock.mockResolvedValue(
			jsonResponse({
				...emptyResponse(),
				total: 1,
				items: [
					{
						id: "mf1",
						userId: "u1",
						userEmail: "user@example.com",
						conversationId: "conv-1",
						messageId: "msg-1",
						ratings: { pertinence: 4, accuracy: 4 },
						expectedAnswer: longAnswer,
						createdAt: "2026-08-20T10:00:00Z",
					},
				],
			}),
		);

		render(<MessageFeedbackPage />);
		await waitFor(() =>
			expect(screen.getByText("user@example.com")).toBeInTheDocument(),
		);

		expect(
			screen.queryByText(longAnswer, { exact: false }),
		).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "Ver más" }));
		expect(screen.getByText(longAnswer, { exact: false })).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "Ver menos" }));
		expect(screen.getByRole("button", { name: "Ver más" })).toBeInTheDocument();
	});

	it("los botones 'Ver más'/'Ver menos' exponen un indicador de foco visible", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		const longAnswer = "x".repeat(80);
		fetchMock.mockResolvedValue(
			jsonResponse({
				...emptyResponse(),
				total: 1,
				items: [
					{
						id: "mf1",
						userId: "u1",
						userEmail: "user@example.com",
						conversationId: "conv-1",
						messageId: "msg-1",
						ratings: { pertinence: 4, accuracy: 4 },
						expectedAnswer: longAnswer,
						createdAt: "2026-08-20T10:00:00Z",
					},
				],
			}),
		);

		render(<MessageFeedbackPage />);
		await waitFor(() =>
			expect(screen.getByText("user@example.com")).toBeInTheDocument(),
		);

		// Los botones deben exponer un indicador de foco visible propio (no
		// basta con `text-accent hover:underline`): un usuario de teclado que
		// llega a ellos con Tab necesita saber que están enfocados.
		const verMas = screen.getByRole("button", { name: "Ver más" });
		expect(verMas.className).toContain("focus-visible:ring-2");

		await user.click(verMas);
		const verMenos = screen.getByRole("button", { name: "Ver menos" });
		expect(verMenos.className).toContain("focus-visible:ring-2");
	});
});
