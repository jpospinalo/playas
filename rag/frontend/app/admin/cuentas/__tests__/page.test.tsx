import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PaginaCuentas from "@/app/admin/cuentas/page";
import { leerLista } from "@/lib/admin/cuentas";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const CUENTAS = {
	items: [
		{
			uid: "u1",
			nombre: "Ana Gómez",
			correo: "p001@ejercicio.atlas",
			rol: "user",
			codigo: "P001",
			tipo_playa: 2,
			tipo_playa_nombre: "Pescadores",
			sede: null,
			preguntas: 7,
			creada: "2026-10-20T10:00:00Z",
		},
		{
			uid: "u2",
			nombre: "Luis Díaz",
			correo: "luis.diaz@ejercicio.atlas",
			rol: "evaluador",
			codigo: null,
			tipo_playa: null,
			tipo_playa_nombre: null,
			sede: "Barranquilla",
			preguntas: 0,
			creada: "2026-10-20T10:00:00Z",
		},
	],
	total: 2,
};

let llamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
	llamadas = [];
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string, init?: RequestInit) => {
			llamadas.push({ url, init });
			if (url.endsWith("/lote")) {
				return new Response(
					JSON.stringify({
						creadas: [
							{
								uid: "u9",
								nombre: "María Pérez",
								rol: "user",
								codigo: "P002",
								tipo_playa: 2,
								sede: null,
								correo: "p002@ejercicio.atlas",
								clave: "ola-1234-faro",
							},
						],
					}),
					{ status: 201 },
				);
			}
			return new Response(JSON.stringify(CUENTAS), { status: 200 });
		}),
	);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("leerLista — lista pegada para crear cuentas", () => {
	it("acepta número o nombre del tipo, organización opcional y separador ; o tabulador", () => {
		const r = leerLista("María Pérez; 2; Asopesca\nJuan Ríos; Turistas\nRosa\tcomerciantes", "user");
		expect(r.errores).toEqual([]);
		expect(r.personas.map((p) => p.tipo_playa)).toEqual([2, 5, 3]);
		expect(r.personas[0].organizacion).toBe("Asopesca");
		expect(r.personas[1].organizacion).toBeUndefined();
	});

	it("dice qué renglón está mal", () => {
		const r = leerLista("Sin tipo\n; 2", "user");
		expect(r.errores).toEqual([
			"Renglón 1 (Sin tipo): falta el tipo de usuario de playa (1 a 5).",
			"Renglón 2: falta el nombre.",
		]);
	});

	it("evaluadores llevan la sede y no piden tipo", () => {
		const r = leerLista("Ana\nLuis", "evaluador", "Santa Marta");
		expect(r.personas).toEqual([
			{ nombre: "Ana", rol: "evaluador", sede: "Santa Marta" },
			{ nombre: "Luis", rol: "evaluador", sede: "Santa Marta" },
		]);
	});
});

describe("app/admin/cuentas", () => {
	it("lista con número, tipo, sede y preguntas", async () => {
		render(<PaginaCuentas />);
		expect(await screen.findByText("Ana Gómez")).toBeInTheDocument();
		expect(screen.getByText("P001")).toBeInTheDocument();
		expect(screen.getByText("Tipo: Pescadores")).toBeInTheDocument();
		expect(screen.getByText("Sede: Barranquilla")).toBeInTheDocument();
		expect(screen.getByText("7")).toBeInTheDocument();
	});

	it("crea por lote y muestra las credenciales para imprimir", async () => {
		render(<PaginaCuentas />);
		await screen.findByText("Ana Gómez");
		await userEvent.type(screen.getByLabelText("Nombre; tipo; organización"), "María Pérez; 2");
		await userEvent.click(screen.getByRole("button", { name: "Crear cuentas" }));
		expect(await screen.findByText("Credenciales para entregar")).toBeInTheDocument();
		expect(screen.getByText("ola-1234-faro")).toBeInTheDocument();
		const lote = llamadas.find((l) => l.url.endsWith("/lote"));
		expect(JSON.parse(String(lote?.init?.body))).toEqual({
			personas: [{ nombre: "María Pérez", rol: "user", tipo_playa: 2 }],
		});
	});

	it("no envía si la lista tiene errores", async () => {
		render(<PaginaCuentas />);
		await screen.findByText("Ana Gómez");
		await userEvent.type(screen.getByLabelText("Nombre; tipo; organización"), "Solo nombre");
		await userEvent.click(screen.getByRole("button", { name: "Crear cuentas" }));
		await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Renglón 1"));
		expect(llamadas.some((l) => l.url.endsWith("/lote"))).toBe(false);
	});
});
