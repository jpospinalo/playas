import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PaginaCuentas from "@/app/admin/cuentas/page";
import { csvALista, leerLista, tipoDeTexto } from "@/lib/admin/cuentas";

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

	it("distingue un tipo inexistente de uno que falta (PQ-50)", () => {
		const r = leerLista("QA Prueba; 7", "user");
		expect(r.errores).toEqual([
			"Renglón 1 (QA Prueba): el tipo «7» no existe; use 1 a 5 o su nombre (p. ej. Pescadores).",
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

describe("importar el CSV de Forms (T10)", () => {
	it("reconoce las columnas por su encabezado y arma la lista", () => {
		const csv =
			"\ufeffMarca temporal,Nombre completo,Correo electrónico,Tipo de usuario de playa,Organización o asociación\n" +
			'1/11/2026 9:00,María Pérez,MARIA@correo.co,"Hoteleros, restauranteros y empresas de servicios vinculados a la playa",Hotel Playa\n' +
			"1/11/2026 9:05,Juan Ríos,juan@correo.co,Tipo 2. Pescadores,\n";
		const r = csvALista(csv);
		expect(r.faltan).toEqual([]);
		expect(r.filas).toBe(2);
		const l = leerLista(r.lista, "user");
		expect(l.errores).toEqual([]);
		expect(l.personas).toEqual([
			{ nombre: "María Pérez", rol: "user", tipo_playa: 4, organizacion: "Hotel Playa", correo: "maria@correo.co" },
			{ nombre: "Juan Ríos", rol: "user", tipo_playa: 2, correo: "juan@correo.co" },
		]);
	});

	it("acepta punto y coma y avisa si faltan columnas", () => {
		expect(csvALista("Nombre;Tipo\nAna;Turistas").filas).toBe(1);
		expect(csvALista("Correo\na@b.co").faltan).toEqual([
			"No encontré la columna del nombre.",
			"No encontré la columna del tipo de usuario de playa.",
		]);
	});

	it("entiende el tipo escrito de varias formas", () => {
		expect(["3", "Tipo 3. Comerciantes", "comerciantes", "Comerciantes y trabajadores de playa"].map(tipoDeTexto)).toEqual([
			3, 3, 3, 3,
		]);
		expect(tipoDeTexto("7")).toBeUndefined();
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

	it("busca por número, nombre o correo (PQ-53)", async () => {
		render(<PaginaCuentas />);
		await screen.findByText("Ana Gómez");
		await userEvent.type(screen.getByLabelText("Buscar (número, nombre o correo)"), "p001");
		expect(screen.getByText("Ana Gómez")).toBeInTheDocument();
		expect(screen.queryByText("Luis Díaz")).not.toBeInTheDocument();
		await userEvent.clear(screen.getByLabelText("Buscar (número, nombre o correo)"));
		await userEvent.type(screen.getByLabelText("Buscar (número, nombre o correo)"), "díaz");
		expect(screen.getByText("Luis Díaz")).toBeInTheDocument();
		expect(screen.queryByText("Ana Gómez")).not.toBeInTheDocument();
	});

	it("crea por lote y muestra las credenciales para imprimir", async () => {
		render(<PaginaCuentas />);
		await screen.findByText("Ana Gómez");
		await userEvent.type(screen.getByLabelText("Nombre; tipo; organización"), "María Pérez; 2");
		await userEvent.click(screen.getByRole("button", { name: "Crear cuentas" }));
		expect(await screen.findByText("Credenciales para entregar")).toBeInTheDocument();
		expect(screen.getByText("ola-1234-faro")).toBeInTheDocument();
		expect(screen.getByText(/escriba este correo y esta clave/)).toBeInTheDocument();
		const lote = llamadas.find((l) => l.url.endsWith("/lote"));
		expect(JSON.parse(String(lote?.init?.body))).toEqual({
			personas: [{ nombre: "María Pérez", rol: "user", tipo_playa: 2 }],
		});
	});

	it("desactiva con confirmación (CHECKLIST-FINAL c2)", async () => {
		render(<PaginaCuentas />);
		await screen.findByText("Ana Gómez");
		await userEvent.click(screen.getByRole("button", { name: "Desactivar la cuenta de Ana Gómez" }));
		expect(screen.getByText(/sus preguntas y calificaciones se conservan/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Sí, desactivar" }));
		const patch = llamadas.find((l) => l.init?.method === "PATCH");
		expect(JSON.parse(String(patch?.init?.body))).toEqual({ activa: false });
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
