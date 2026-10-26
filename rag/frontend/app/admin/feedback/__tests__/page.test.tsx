import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PaginaEncuestas from "@/app/admin/feedback/page";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const ENCUESTAS = {
	items: [
		{
			id: "e1",
			fecha: "2026-10-25T15:00:00Z",
			persona: "Ana Gómez",
			titulo: "Permiso para vender",
			conversation_id: "c1",
			general: 4,
			tono: 5,
			largo: 3,
			facilidad: 4,
			comentario: "Clara y con la norma, gracias.",
		},
	],
	total: 1,
	page: 1,
	page_size: 10,
	promedios: { general: 3.4, tono: 3.4, largo: 3.3, facilidad: 3.4 },
};

beforeEach(() => {
	vi.stubGlobal(
		"fetch",
		vi.fn(async () => new Response(JSON.stringify(ENCUESTAS), { status: 200 })),
	);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("app/admin/feedback — encuestas de satisfacción", () => {
	it("muestra promedios en formato colombiano y el comentario completo", async () => {
		render(<PaginaEncuestas />);
		expect(await screen.findByText("Permiso para vender")).toBeInTheDocument();
		expect(screen.getAllByText("3,4").length).toBe(3);
		expect(screen.getByText("3,3")).toBeInTheDocument();
		expect(screen.getByText("Comentó: “Clara y con la norma, gracias.”")).toBeInTheDocument();
		expect(screen.getAllByText("4 de 5").length).toBe(2);
		expect(screen.queryByText(/@/)).toBeNull();
	});

	it("el filtro simple pide solo las malas", async () => {
		render(<PaginaEncuestas />);
		await screen.findByText("Permiso para vender");
		await userEvent.selectOptions(screen.getByLabelText("Mostrar"), "malas");
		await waitFor(() =>
			expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("filtro=malas"))).toBe(true),
		);
	});
});
