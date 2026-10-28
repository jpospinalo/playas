import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PanelResumen from "@/app/admin/page";
import type { Preguntas, Resumen } from "@/lib/admin/panel";

const replaceMock = vi.fn();
let parametros = new URLSearchParams();
vi.mock("next/navigation", () => ({
	useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
	useSearchParams: () => parametros,
}));

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const CIFRAS = {
	preguntas: 482,
	personas: 64,
	personas_nuevas: 18,
	respuestas: 385,
	con_fuente: 312,
	sin_respuesta_segura: 35,
	fuera_de_tema: 30,
	pide_aclarar: 8,
	saludos: 97,
	sin_respuesta_guardada: 0,
	calificaciones: 141,
	le_sirvio: 102,
	no_le_sirvio: 30,
};

function resumen(cambios: Partial<Resumen> = {}): Resumen {
	return {
		demo: true,
		periodo: { dias: 30, desde: "2026-09-27T05:00:00Z", hasta: "2026-10-26T15:00:00Z", agrupacion: "semana" },
		cifras: CIFRAS,
		anterior: { ...CIFRAS, preguntas: 430, con_fuente: 300, sin_respuesta_segura: 27 },
		serie: [
			{ fecha: "2026-09-21", desde: "2026-09-27", hasta: "2026-09-27", parcial: true, preguntas: 5, sin_respuesta_segura: 0 },
			{ fecha: "2026-09-28", desde: "2026-09-28", hasta: "2026-10-04", parcial: false, preguntas: 120, sin_respuesta_segura: 9 },
		],
		temas: [
			{ id: "entrar", titulo: "Entrar o caminar por la playa", preguntas: 138, calificaciones: 40, le_sirvio: 31, brechas: 5 },
			{ id: "lanchas", titulo: "Lanchas, motos de agua y bañistas", preguntas: 31, calificaciones: 4, le_sirvio: 4, brechas: 0 },
		],
		normas: [{ nombre: "Decreto 2324 de 1984", doc_type: "normativa", respuestas: 164 }],
		playas: [{ nombre: "Taganga", preguntas: 58 }],
		sin_playa: 257,
		personas: { activas: 64, nuevas: 18, recurrentes: 46, preguntas_por_persona: 7.5 },
		brechas_total: 43,
		brechas: [
			{
				pregunta: "<img src=x onerror=alert(1)> ¿Puedo arreglar el techo?",
				veces: 4,
				tema: "obras",
				tema_titulo: "Construcciones cerca del mar",
				motivo: "sin_respuesta_segura",
				esperaba: "Saber si la DIMAR da permiso",
				ultima: "2026-10-25T20:00:00Z",
				conversation_id: "c1",
			},
		],
		...cambios,
	};
}

const PREGUNTAS: Preguntas = { items: [], total: 0, page: 1, page_size: 20 };

let respuestaResumen: () => Response;

beforeEach(() => {
	parametros = new URLSearchParams();
	replaceMock.mockClear();
	respuestaResumen = () => new Response(JSON.stringify(resumen()), { status: 200 });
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string) => {
			if (url.includes("/resumen")) return respuestaResumen();
			return new Response(JSON.stringify(PREGUNTAS), { status: 200 });
		}),
	);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("app/admin/page — resumen del panel", () => {
	it("muestra aviso de demo, cifras con su número bruto y el cambio con texto", async () => {
		render(<PanelResumen />);
		expect(await screen.findByText("Datos de demostración.")).toBeInTheDocument();
		expect(screen.getByText("482")).toBeInTheDocument();
		// J6-B: la cifra con su contexto, "312 de 385 (81 %)".
		expect(screen.getByText("312")).toBeInTheDocument();
		expect(screen.getAllByText(/de 385 \(81 %\)/).length).toBeGreaterThan(0);
		expect(screen.getByText(/Subió 12/)).toBeInTheDocument();
		// "Le sirvió" usa las respuestas como base (PQ-01): 141 / 385 = 37 %.
		expect(screen.getByText(/Calificaron el 37/)).toBeInTheDocument();
		// Desglose que suma (PQ-04).
		expect(screen.getByText(/385 respuestas: 312 con fuente citada, 35 sin respuesta segura, 30 fuera de tema y 8 en que pidió aclarar/)).toBeInTheDocument();
	});

	it("con menos de 5 calificaciones dice 'pocos datos' en vez de un %", async () => {
		render(<PanelResumen />);
		const temas = await screen.findByRole("list", { name: "Preguntas por tema" });
		expect(within(temas).getByText(/Pocos datos: 4 calificaciones/)).toBeInTheDocument();
	});

	it("muestra el texto de las preguntas como texto plano", async () => {
		const { container } = render(<PanelResumen />);
		expect(await screen.findByText(/¿Puedo arreglar el techo\?/)).toBeInTheDocument();
		expect(container.querySelector("img[src='x']")).toBeNull();
	});

	it("'Todo' no compara con un periodo anterior", async () => {
		respuestaResumen = () =>
			new Response(
				JSON.stringify(resumen({ anterior: null, periodo: { dias: 0, desde: null, hasta: "2026-10-26T15:00:00Z", agrupacion: "semana" } })),
				{ status: 200 },
			);
		render(<PanelResumen />);
		expect(await screen.findByText("Desde la primera pregunta guardada")).toBeInTheDocument();
		expect(screen.queryByText(/Subió|Bajó/)).toBeNull();
		// Con "Todo" toda persona es "nueva": no se muestra la división (PQ-11).
		expect(screen.queryByText(/ya habían preguntado antes/)).toBeNull();
		expect(screen.getByText(/En todo el tiempo preguntaron 64 personas/)).toBeInTheDocument();
	});

	it("periodo sin preguntas explica qué hacer", async () => {
		respuestaResumen = () =>
			new Response(JSON.stringify(resumen({ cifras: { ...CIFRAS, preguntas: 0, respuestas: 0 } })), { status: 200 });
		render(<PanelResumen />);
		expect(await screen.findByText("No hay preguntas en este periodo")).toBeInTheDocument();
		expect(screen.getByText(/periodo más largo/)).toBeInTheDocument();
	});

	it("si el servidor falla, lo dice y deja reintentar", async () => {
		respuestaResumen = () => new Response("{}", { status: 500 });
		render(<PanelResumen />);
		expect(await screen.findByText("No se pudieron cargar las cifras.")).toBeInTheDocument();
		respuestaResumen = () => new Response(JSON.stringify(resumen()), { status: 200 });
		await userEvent.click(screen.getByRole("button", { name: "Intentar otra vez" }));
		await waitFor(() => expect(screen.getByText("482")).toBeInTheDocument());
	});

	it("cambiar el periodo pide de nuevo las cifras con ese periodo", async () => {
		render(<PanelResumen />);
		await screen.findByText("482");
		await userEvent.click(screen.getByRole("radio", { name: "7 días" }));
		await waitFor(() =>
			expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("/resumen?dias=7"))).toBe(true),
		);
	});

	it("los filtros van a la URL y se leen de ella (PQ-22)", async () => {
		parametros = new URLSearchParams("dias=0&tema=obras");
		render(<PanelResumen />);
		const reemplazar = vi.spyOn(window.history, "replaceState");
		await screen.findByText("482");
		expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("/resumen?dias=0&tema=obras"))).toBe(true);
		await userEvent.click(screen.getByRole("radio", { name: "7 días" }));
		expect(reemplazar).toHaveBeenCalledWith(null, "", "/admin?dias=7&tema=obras");
		reemplazar.mockRestore();
	});
});
