import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FeedbackPage from "@/app/admin/feedback/page";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

function emptyResponse() {
	return {
		items: [],
		total: 0,
		avg_ratings: { tone: 0, length: 0, usability: 0, overall: 0 },
		distributions: { overall: {} },
	};
}

function jsonResponse(body: unknown, status = 200) {
	return {
		ok: status >= 200 && status < 300,
		status,
		json: async () => body,
	} as Response;
}

describe("FeedbackPage — filtros administrativos (A3)", () => {
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

		render(<FeedbackPage />);

		// Carga inicial (sin filtros).
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("General mínimo"), "3");
		await user.selectOptions(screen.getByLabelText("General máximo"), "5");
		await user.type(screen.getByLabelText("Desde"), "2026-08-01");
		await user.type(screen.getByLabelText("Hasta"), "2026-08-31");

		// Cambiar los borradores no debe disparar ninguna solicitud adicional.
		expect(fetchMock).toHaveBeenCalledTimes(1);

		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

		const [url] = fetchMock.mock.calls[1] as [string];
		const params = new URL(url).searchParams;
		expect(params.get("min_overall")).toBe("3");
		expect(params.get("max_overall")).toBe("5");
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

		const { unmount } = render(<FeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(capturedSignal?.aborted).toBe(false);

		unmount();

		expect(capturedSignal?.aborted).toBe(true);
	});

	it("'Limpiar' resetea los borradores, vuelve a la página 1 y genera como máximo una solicitud (G2.1)", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<FeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("General mínimo"), "3");
		await user.selectOptions(screen.getByLabelText("General máximo"), "5");
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
			(screen.getByLabelText("General mínimo") as HTMLSelectElement).value,
		).toBe("");
		expect(
			(screen.getByLabelText("General máximo") as HTMLSelectElement).value,
		).toBe("");

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
		// Ninguna solicitud extra tras el reseteo (mismo `page`/`appliedFilters`
		// de referencia una vez asentados).
		await new Promise((r) => setTimeout(r, 20));
		expect(fetchMock).toHaveBeenCalledTimes(3);

		const [clearedUrl] = fetchMock.mock.calls[2] as [string];
		const clearedParams = new URL(clearedUrl).searchParams;
		expect(clearedParams.get("min_overall")).toBeNull();
		expect(clearedParams.get("max_overall")).toBeNull();
		expect(clearedParams.get("start_date")).toBeNull();
		expect(clearedParams.get("end_date")).toBeNull();
	});

	it("bloquea 'Aplicar filtros' y muestra un error si el mínimo es mayor que el máximo", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<FeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		await user.selectOptions(screen.getByLabelText("General mínimo"), "5");
		await user.selectOptions(screen.getByLabelText("General máximo"), "2");
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		expect(await screen.findByRole("alert")).toHaveTextContent(
			/no puede ser mayor que el máximo/i,
		);
		// Ninguna solicitud adicional: sigue en 1 (solo la carga inicial).
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("bloquea 'Aplicar filtros' y muestra un error si «Desde» es posterior a «Hasta»", async () => {
		const user = userEvent.setup();
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse(emptyResponse()));

		render(<FeedbackPage />);
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
					total: 2,
					items: [
						{
							id: "f1",
							userId: "u1",
							userEmail: "nueva@example.com",
							ratings: { tone: 5, length: 5, usability: 5, overall: 5 },
							comment: null,
							conversationId: null,
							conversationTitle: null,
							createdAt: "2026-08-20T10:00:00Z",
						},
					],
				}),
			);

		render(<FeedbackPage />);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		// Dispara una segunda solicitud (aplicar filtros) antes de que la
		// primera (carga inicial) se resuelva; debe cancelar la primera.
		await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		await waitFor(() =>
			expect(screen.getByText("nueva@example.com")).toBeInTheDocument(),
		);
		// La primera solicitud, cancelada, nunca debió mostrar error ni pisar
		// el resultado de la segunda.
		expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
	});
});
