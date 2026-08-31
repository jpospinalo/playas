import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuthModal } from "@/components/common/AuthModal";

vi.mock("@/lib/auth", () => ({
	getLastEmail: vi.fn(() => ""),
}));

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({
		signIn: vi.fn(),
		sessionExpiredMessage: null,
	}),
}));

describe("AuthModal — reflow vertical", () => {
	it("el panel tiene un límite de altura relativo al viewport con scroll local", () => {
		render(<AuthModal open onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		expect(dialog.className).toMatch(/max-h-\[calc\(100dvh-2rem\)\]/);
		expect(dialog.className).toMatch(/overflow-y-auto/);
	});

	it("el título sigue siendo el nombre accesible del panel", () => {
		render(<AuthModal open onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		const labelledBy = dialog.getAttribute("aria-labelledby");
		expect(labelledBy).toBeTruthy();
		expect(document.getElementById(labelledBy as string)).toHaveTextContent(
			"Iniciar sesión",
		);
	});
});
