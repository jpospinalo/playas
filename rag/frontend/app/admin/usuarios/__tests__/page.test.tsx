import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UsuariosPage from "@/app/admin/usuarios/page";
import { createAdminUser, listAdminUsers, updateAdminUserPassword } from "@/lib/api";

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: { user_id: "test-user", email: "test@example.test", display_name: null, role: "admin" } }),
}));

vi.mock("@/lib/auth", () => ({ getTokenForUser: vi.fn(() => "test-token") }));

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

describe("app/admin/usuarios — nombres accesibles y anuncios locales", () => {
	const account = {
		uid: "u1",
		email: "usuario@example.com",
		displayName: null,
		role: "user",
		createdAt: "2026-01-01T00:00:00Z",
	};

	beforeEach(() => {
		listAdminUsersMock.mockReset();
		createAdminUserMock.mockReset();
		updateAdminUserPasswordMock.mockReset();
		listAdminUsersMock.mockResolvedValue([account]);
		createAdminUserMock.mockResolvedValue({ ...account, uid: "u2", email: "nueva@example.com" });
		updateAdminUserPasswordMock.mockResolvedValue(undefined);
	});

	it.each([
		{ action: "Crear usuario", label: "Contraseña", submit: "Crear" },
		{ action: "Cambiar contraseña", label: "Nueva contraseña", submit: "Actualizar" },
	])("$action conserva el nombre, valor y envío al alternar visibilidad", async ({ action, label, submit }) => {
		const user = userEvent.setup();
		render(<UsuariosPage />);
		await user.click(await screen.findByRole("button", { name: action }));
		const dialog = within(screen.getByRole("dialog"));
		const password = dialog.getByLabelText(label, { exact: true });
		const confirmation = dialog.getByLabelText("Confirmar contraseña", { exact: true });
		expect(password).toHaveAttribute("type", "password");
		expect(password.id).not.toBe("");
		expect(password.id).not.toBe(confirmation.id);
		await user.type(password, "nuevaClave123");
		await user.type(confirmation, "nuevaClave123");
		await user.click(dialog.getByRole("button", { name: "Mostrar contraseña" }));
		expect(dialog.getByLabelText(label, { exact: true })).toBe(password);
		expect(password).toHaveAttribute("type", "text");
		expect(password).toHaveValue("nuevaClave123");
		expect(confirmation).toHaveValue("nuevaClave123");
		await user.click(dialog.getByRole("button", { name: "Ocultar contraseña" }));
		expect(dialog.getByLabelText(label, { exact: true })).toBe(password);
		expect(password).toHaveAttribute("type", "password");
		if (action === "Crear usuario") {
			await user.type(dialog.getByLabelText("Email"), "nueva@example.com");
		}
		await user.click(dialog.getByRole("button", { name: submit }));
		if (action === "Crear usuario") {
			expect(createAdminUserMock).toHaveBeenCalledTimes(1);
			expect(createAdminUserMock).toHaveBeenCalledWith(
				{ email: "nueva@example.com", password: "nuevaClave123", displayName: null },
				"test-token",
			);
		} else {
			expect(updateAdminUserPasswordMock).toHaveBeenCalledTimes(1);
			expect(updateAdminUserPasswordMock).toHaveBeenCalledWith(
				"u1", "nuevaClave123", "test-token",
			);
		}
	});

	it.each([
		{ action: "Crear usuario", submit: "Crear", success: "Usuario nueva@example.com creado." },
		{ action: "Cambiar contraseña", submit: "Actualizar", success: "Contraseña actualizada para usuario@example.com." },
	])("$action anuncia el éxito una vez sin convertir la tabla en región viva", async ({ action, submit, success }) => {
		const user = userEvent.setup();
		render(<UsuariosPage />);
		await user.click(await screen.findByRole("button", { name: action }));
		const panel = screen.getByRole("dialog");
		const dialog = within(panel);
		if (action === "Crear usuario") {
			await user.type(dialog.getByLabelText("Email"), "nueva@example.com");
		}
		// El contrato del anuncio se caracteriza por separado del nombre del input.
		for (const input of panel.querySelectorAll<HTMLInputElement>('input[type="password"]')) {
			await user.type(input, "nuevaClave123");
		}
		await user.click(dialog.getByRole("button", { name: submit }));
		expect(await screen.findByText(success)).toBeInTheDocument();
		expect(screen.getAllByRole("status")).toHaveLength(1);
		expect(screen.getByRole("status")).toHaveTextContent(success);
		expect(screen.getByRole("table").closest('[aria-live], [role="status"], [role="alert"]')).toBeNull();
	});

	it.each([
		{ action: "Crear usuario", submit: "Crear" },
		{ action: "Cambiar contraseña", submit: "Actualizar" },
	])("$action anuncia el error local y conserva el formulario", async ({ action, submit }) => {
		createAdminUserMock.mockRejectedValue(new Error("No fue posible guardar."));
		updateAdminUserPasswordMock.mockRejectedValue(new Error("No fue posible guardar."));
		const user = userEvent.setup();
		render(<UsuariosPage />);
		await user.click(await screen.findByRole("button", { name: action }));
		const panel = screen.getByRole("dialog");
		const dialog = within(panel);
		if (action === "Crear usuario") {
			await user.type(dialog.getByLabelText("Email"), "nueva@example.com");
		}
		const passwords = panel.querySelectorAll<HTMLInputElement>('input[type="password"]');
		for (const input of passwords) await user.type(input, "nuevaClave123");
		await user.click(dialog.getByRole("button", { name: submit }));
		expect(await dialog.findByText("No fue posible guardar.")).toBeInTheDocument();
		expect(dialog.getAllByRole("alert")).toHaveLength(1);
		expect(dialog.getByRole("alert")).toHaveTextContent("No fue posible guardar.");
		expect(screen.getByRole("dialog")).toBe(panel);
		for (const input of passwords) expect(input).toHaveValue("nuevaClave123");
		expect(screen.queryByRole("status")).not.toBeInTheDocument();
	});

	it("anuncia el error de carga una vez y conserva disponible Crear usuario", async () => {
		listAdminUsersMock.mockRejectedValue(new Error("No fue posible cargar los usuarios."));
		render(<UsuariosPage />);
		expect(await screen.findByText("Error: No fue posible cargar los usuarios.")).toBeInTheDocument();
		expect(screen.getAllByRole("alert")).toHaveLength(1);
		expect(screen.getByRole("alert")).toHaveTextContent("Error: No fue posible cargar los usuarios.");
		expect(screen.getByRole("button", { name: "Crear usuario" })).toBeEnabled();
	});
});
