import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/components/providers/AuthProvider";

/**
 * Cobertura directa de `signUp` contra un 409 real del backend (correo ya
 * registrado): `readErrorDetail` debe propagar el mensaje real del `detail`
 * (un string en este caso, a diferencia del 422 de validación que es una
 * lista — ver `lib/__tests__/api.test.ts`), y `AuthModal` lo muestra tal
 * cual a través de `restErrorMessage`.
 */
describe("AuthProvider.signUp — correo ya registrado (409)", () => {
	afterEach(() => {
		localStorage.clear();
		vi.unstubAllGlobals();
	});

	it("propaga el mensaje del backend cuando el correo ya existe", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				new Response(JSON.stringify({ detail: "Este correo ya está registrado." }), {
					status: 409,
					headers: { "Content-Type": "application/json" },
				}),
			),
		);

		const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
		await waitFor(() => expect(result.current.loading).toBe(false));

		await expect(
			result.current.signUp("duplicado@example.com", "supersecret1", null, null),
		).rejects.toThrow("Este correo ya está registrado.");
	});
});
