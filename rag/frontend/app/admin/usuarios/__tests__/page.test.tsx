import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UsuariosPage from "@/app/admin/usuarios/page";
import { createAdminUser, listAdminUsers, updateAdminUserPassword } from "@/lib/api";

vi.mock("@/lib/api", () => ({
	listAdminUsers: vi.fn(),
	createAdminUser: vi.fn(),
	updateAdminUserPassword: vi.fn(),
}));

const listAdminUsersMock = listAdminUsers as unknown as ReturnType<typeof vi.fn>;
const createAdminUserMock = createAdminUser as unknown as ReturnType<typeof vi.fn>;
const updateAdminUserPasswordMock = updateAdminUserPassword as unknown as ReturnType<
	typeof vi.fn
>;

// jsdom implementa `DOMException` en un realm cuyo `Error` no coincide con
// el `Error` global que usa el resto del módulo bajo prueba: una instancia
// real de `DOMException` allí falla `instanceof Error`, aunque
// `instanceof DOMException` siga funcionando. En un navegador real (un
// único realm) esto no ocurre — `AbortSignal.timeout()` produce un
// `DOMException` que SÍ es `instanceof Error`. Este reemplazo, activo solo
// dentro de cada prueba que lo usa, reproduce ese comportamiento de
// navegador real para ejercitar el límite de presentación tal como se
// comporta en producción.
class TimeoutDOMException extends Error {
	constructor(message: string, name: string) {
		super(message);
		this.name = name;
	}
}

describe("app/admin/usuarios — ModalShell, reflow vertical", () => {
	beforeEach(() => {
		listAdminUsersMock.mockReset();
		listAdminUsersMock.mockResolvedValue([]);
	});

	it("el panel de ModalShell tiene un límite de altura relativo al viewport con scroll local", async () => {
		const user = userEvent.setup();
		render(<UsuariosPage />);

		await user.click(await screen.findByRole("button", { name: "Crear usuario" }));

		const dialog = screen.getByRole("dialog");
		expect(dialog.className).toMatch(/max-h-\[calc\(100dvh-2rem\)\]/);
		expect(dialog.className).toMatch(/overflow-y-auto/);
	});

	it("el botón de mostrar/ocultar contraseña y 'Cancelar' exponen un indicador de foco visible", async () => {
		const user = userEvent.setup();
		render(<UsuariosPage />);

		await user.click(await screen.findByRole("button", { name: "Crear usuario" }));

		// Ambos deben exponer un estilo `focus-visible` propio (el botón
		// "Guardar" vecino, en el mismo formulario, ya lo tenía) — un usuario
		// de teclado que llega a ellos con Tab necesita saber que están
		// enfocados.
		const toggle = screen.getByRole("button", { name: "Mostrar contraseña" });
		expect(toggle.className).toContain("focus-visible:ring-2");

		const cancelar = screen.getByRole("button", { name: "Cancelar" });
		expect(cancelar.className).toContain("focus-visible:ring-2");
	});
});

describe("app/admin/usuarios — timeout REST en listar, crear y cambiar contraseña", () => {
	beforeEach(() => {
		listAdminUsersMock.mockReset();
		createAdminUserMock.mockReset();
		updateAdminUserPasswordMock.mockReset();
		vi.stubGlobal("DOMException", TimeoutDOMException);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("un timeout al listar usuarios muestra el mensaje controlado, no el texto nativo del DOMException", async () => {
		listAdminUsersMock.mockRejectedValue(
			new DOMException("The operation was aborted due to timeout", "TimeoutError"),
		);

		render(<UsuariosPage />);

		expect(
			await screen.findByText("Error: La solicitud tardó demasiado. Intenta nuevamente."),
		).toBeInTheDocument();
	});

	it("un timeout al crear un usuario muestra el mensaje controlado sin cerrar el modal ni perder los datos del formulario", async () => {
		listAdminUsersMock.mockResolvedValue([]);
		createAdminUserMock.mockRejectedValue(
			new DOMException("The operation was aborted due to timeout", "TimeoutError"),
		);

		const user = userEvent.setup();
		render(<UsuariosPage />);

		await user.click(await screen.findByRole("button", { name: "Crear usuario" }));
		const dialog = screen.getByRole("dialog");
		const [passwordInput, confirmInput] = Array.from(
			dialog.querySelectorAll<HTMLInputElement>('input[type="password"]'),
		);

		await user.type(screen.getByLabelText("Email"), "nueva@example.com");
		await user.type(passwordInput, "contrasena123");
		await user.type(confirmInput, "contrasena123");
		await user.click(screen.getByRole("button", { name: "Crear" }));

		expect(
			await screen.findByText("La solicitud tardó demasiado. Intenta nuevamente."),
		).toBeInTheDocument();
		// El modal sigue abierto y el formulario conserva lo escrito: nada se
		// pierde por un timeout.
		expect(screen.getByRole("dialog")).toBeInTheDocument();
		expect(screen.getByLabelText("Email")).toHaveValue("nueva@example.com");
		expect(passwordInput).toHaveValue("contrasena123");
	});

	it("un timeout al cambiar la contraseña muestra el mensaje controlado sin cerrar el modal", async () => {
		listAdminUsersMock.mockResolvedValue([
			{
				uid: "u1",
				email: "usuario@example.com",
				displayName: null,
				role: "user",
				createdAt: "2026-01-01T00:00:00Z",
			},
		]);
		updateAdminUserPasswordMock.mockRejectedValue(
			new DOMException("The operation was aborted due to timeout", "TimeoutError"),
		);

		const user = userEvent.setup();
		render(<UsuariosPage />);

		await user.click(await screen.findByRole("button", { name: "Cambiar contraseña" }));
		const dialog = screen.getByRole("dialog");
		const [passwordInput, confirmInput] = Array.from(
			dialog.querySelectorAll<HTMLInputElement>('input[type="password"]'),
		);

		await user.type(passwordInput, "nuevaClave123");
		await user.type(confirmInput, "nuevaClave123");
		await user.click(screen.getByRole("button", { name: "Actualizar" }));

		expect(
			await screen.findByText("La solicitud tardó demasiado. Intenta nuevamente."),
		).toBeInTheDocument();
		expect(screen.getByRole("dialog")).toBeInTheDocument();
	});
});
