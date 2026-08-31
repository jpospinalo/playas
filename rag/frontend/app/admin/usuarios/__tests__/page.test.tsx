import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UsuariosPage from "@/app/admin/usuarios/page";
import { listAdminUsers } from "@/lib/api";

vi.mock("@/lib/api", () => ({
	listAdminUsers: vi.fn(),
	createAdminUser: vi.fn(),
	updateAdminUserPassword: vi.fn(),
}));

const listAdminUsersMock = listAdminUsers as unknown as ReturnType<typeof vi.fn>;

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
