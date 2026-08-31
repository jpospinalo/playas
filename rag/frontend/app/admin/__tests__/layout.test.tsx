import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AdminLayout from "@/app/admin/layout";

const routerMock = { replace: vi.fn(), push: vi.fn() };

vi.mock("next/navigation", () => ({
	usePathname: () => "/admin",
	useRouter: () => routerMock,
}));

const useAuthMock = vi.fn();
vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => useAuthMock(),
}));

describe("app/admin/layout — landmarks en los estados de carga y 403", () => {
	it("el estado de carga expone un <main id=\"main-content\">", () => {
		useAuthMock.mockReturnValue({ user: null, role: null, loading: true });

		render(<AdminLayout>{"contenido"}</AdminLayout>);

		const main = screen.getByRole("main");
		expect(main).toHaveAttribute("id", "main-content");
		expect(main).toHaveTextContent("Verificando acceso…");
	});

	it("el estado 403 (usuario sin rol admin) expone un <main id=\"main-content\">", () => {
		useAuthMock.mockReturnValue({
			user: { user_id: "u1", email: "user@example.com", display_name: null, role: "user" },
			role: "user",
			loading: false,
		});

		render(<AdminLayout>{"contenido"}</AdminLayout>);

		const main = screen.getByRole("main");
		expect(main).toHaveAttribute("id", "main-content");
		expect(main).toHaveTextContent("Acceso restringido");
	});

	it("el contenido normal (usuario admin) sigue teniendo un único <main id=\"main-content\">", () => {
		useAuthMock.mockReturnValue({
			user: { user_id: "u1", email: "admin@example.com", display_name: null, role: "admin" },
			role: "admin",
			loading: false,
		});

		render(<AdminLayout>{"contenido admin"}</AdminLayout>);

		const mains = screen.getAllByRole("main");
		expect(mains).toHaveLength(1);
		expect(mains[0]).toHaveAttribute("id", "main-content");
		expect(mains[0]).toHaveTextContent("contenido admin");
	});
});
