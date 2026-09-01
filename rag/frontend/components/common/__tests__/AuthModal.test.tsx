import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuthModal } from "@/components/common/AuthModal";

vi.mock("@/lib/auth", () => ({
	getLastEmail: vi.fn(() => ""),
}));

const signInMock = vi.fn();

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({
		signIn: signInMock,
		sessionExpiredMessage: null,
	}),
}));

describe("AuthModal — mensaje de error en el límite de presentación", () => {
	it("un timeout local en signIn() se muestra como el mensaje controlado, no el texto nativo del DOMException", async () => {
		signInMock.mockReset();
		signInMock.mockRejectedValueOnce(
			new DOMException("The operation was aborted due to timeout", "TimeoutError"),
		);

		render(<AuthModal open onClose={vi.fn()} />);

		fireEvent.change(screen.getByLabelText(/correo/i), {
			target: { value: "a@b.com" },
		});
		fireEvent.change(screen.getByLabelText("Contraseña"), {
			target: { value: "x".repeat(8) },
		});
		fireEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

		await waitFor(() =>
			expect(
				screen.getByText("La solicitud tardó demasiado. Intenta nuevamente."),
			).toBeInTheDocument(),
		);
	});
});

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
