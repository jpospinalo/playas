import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PaginaOpiniones from "@/app/admin/message-feedback/page";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const RESUMEN = {
	cifras: {
		preguntas: 100,
		respuestas: 90,
		calificaciones: 40,
		le_sirvio: 30,
		no_le_sirvio: 8,
	},
};

const PREGUNTAS = {
	items: [
		{
			id: "q1",
			fecha: "2026-10-25T15:00:00Z",
			pregunta: "¿Puedo arreglar el techo de mi kiosco?",
			tema: "obras",
			tema_titulo: "Construcciones cerca del mar",
			playa: null,
			resultado: "con_fuente",
			fuentes: 2,
			fuentes_sentencias: 1,
			calificacion: "no_util",
			esperaba: "Saber si la DIMAR da permiso",
			persona: "Ana Gómez",
			conversation_id: "c1",
		},
	],
	total: 1,
	page: 1,
	page_size: 20,
};

beforeEach(() => {
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string) => {
			if (url.includes("/resumen")) return new Response(JSON.stringify(RESUMEN), { status: 200 });
			return new Response(JSON.stringify(PREGUNTAS), { status: 200 });
		}),
	);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("app/admin/message-feedback — opiniones sobre cada respuesta", () => {
	it("muestra la pregunta, el resultado con normas y sentencias, la opinión y el nombre (sin correo)", async () => {
		render(<PaginaOpiniones />);
		expect(await screen.findByText("¿Puedo arreglar el techo de mi kiosco?")).toBeInTheDocument();
		expect(screen.getByText("Respondió citando 2 fuentes: 1 norma y 1 sentencia")).toBeInTheDocument();
		expect(screen.getByText("No le sirvió", { selector: "span" })).toBeInTheDocument();
		expect(screen.getByText(/Saber si la DIMAR da permiso/)).toBeInTheDocument();
		expect(screen.getByText(/Ana Gómez/)).toBeInTheDocument();
		expect(screen.getByRole("link", { name: /techo de mi kiosco/ })).toHaveAttribute(
			"href",
			"/admin/conversacion?id=c1&volver=%2Fadmin%2Fmessage-feedback",
		);
		expect(await screen.findByText("40")).toBeInTheDocument();
	});

	it("por defecto pide solo las calificadas y el filtro simple cambia la consulta", async () => {
		render(<PaginaOpiniones />);
		await screen.findByText("¿Puedo arreglar el techo de mi kiosco?");
		expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("resultado=calificadas"))).toBe(true);
		await userEvent.selectOptions(screen.getByLabelText("Mostrar"), "no_le_sirvio");
		await waitFor(() =>
			expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("resultado=no_le_sirvio"))).toBe(true),
		);
	});
});
