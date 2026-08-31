import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SidebarUserMenu } from "@/components/chat/SidebarUserMenu";

function CollapsedHarness() {
	const [open, setOpen] = useState(false);
	const onSignOut = vi.fn().mockResolvedValue(undefined);
	return (
		<SidebarUserMenu
			expanded={false}
			open={open}
			userName="Juan Pérez"
			userEmail="juan@example.com"
			userInitial="J"
			isAdmin
			onToggle={() => setOpen((current) => !current)}
			onClose={() => setOpen(false)}
			onSignOut={onSignOut}
		/>
	);
}

function Harness() {
	const [open, setOpen] = useState(false);
	const onSignOut = vi.fn().mockResolvedValue(undefined);
	return (
		<SidebarUserMenu
			expanded
			open={open}
			userName="Juan Pérez"
			userEmail="juan@example.com"
			userInitial="J"
			isAdmin
			onToggle={() => setOpen((current) => !current)}
			onClose={() => setOpen(false)}
			onSignOut={onSignOut}
		/>
	);
}

describe("SidebarUserMenu — semántica de disclosure ordinaria", () => {
	it("el panel abierto no usa role=\"menu\"/\"menuitem\" (no es un menú de aplicación)", async () => {
		const user = userEvent.setup();
		render(<Harness />);

		await user.click(
			screen.getByRole("button", { name: "Abrir menú de perfil" }),
		);

		expect(screen.queryByRole("menu")).not.toBeInTheDocument();
		expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
		// El enlace de admin y "Cerrar sesión" siguen siendo alcanzables como
		// elementos ordinarios (link / button), solo que sin el contrato de
		// teclado de un menú de aplicación (que este widget no implementa).
		expect(
			screen.getByRole("link", { name: /panel de administrador/i }),
		).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /cerrar sesión/i }),
		).toBeInTheDocument();
	});

	it("el disparador ya no anuncia aria-haspopup=\"menu\"", () => {
		render(<Harness />);
		const trigger = screen.getByRole("button", { name: "Abrir menú de perfil" });
		expect(trigger).not.toHaveAttribute("aria-haspopup");
		expect(trigger).toHaveAttribute("aria-expanded", "false");
	});
});

describe("SidebarUserMenu — avatar colapsado con contraste suficiente", () => {
	it("usa text-accent-fg (no text-white) sobre bg-accent, igual que el avatar del panel expandido", () => {
		render(<CollapsedHarness />);

		const trigger = screen.getByRole("button", { name: "Abrir menú de perfil" });
		expect(trigger.className).toMatch(/\btext-accent-fg\b/);
		expect(trigger.className).not.toMatch(/\btext-white\b/);
	});
});
