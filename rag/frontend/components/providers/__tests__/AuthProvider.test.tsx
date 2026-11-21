import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/components/providers/AuthProvider";
import { clearAuth, getToken, setAuth, type AuthUser } from "@/lib/auth";

const A: AuthUser = { user_id: "A", email: "a@example.test", display_name: "A", user_type: null, role: "user" };
const B: AuthUser = { user_id: "B", email: "b@example.test", display_name: "B", user_type: null, role: "admin" };

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}

function response(user: AuthUser, status = 200): Response {
	return { ok: status === 200, status, json: async () => user } as Response;
}

function storage(key: string | null = "atlas_token", storageArea: Storage = localStorage) {
	window.dispatchEvent(new StorageEvent("storage", { key, storageArea }));
}

function mount() {
	return renderHook(() => useAuth(), {
		wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
	});
}

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => { localStorage.clear(); fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("AuthProvider — identidad entre pestañas", () => {
	it("valida la sesión inicial y conserva la caché ligada si hay un fallo transitorio", async () => {
		setAuth("token-A", A);
		fetchMock.mockRejectedValueOnce(new TypeError("offline"));
		const { result } = mount();
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.user).toEqual(A);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("oculta A al cambiar a B y solo publica B tras validar /me", async () => {
		setAuth("token-A", A);
		const pending = deferred<Response>();
		fetchMock.mockResolvedValueOnce(response(A)).mockReturnValueOnce(pending.promise);
		const { result } = mount();
		await waitFor(() => expect(result.current.user).toEqual(A));
		act(() => { setAuth("token-B", B); storage(); });
		expect(result.current.user).toBeNull();
		expect(result.current.loading).toBe(true);
		await act(async () => { pending.resolve(response(B)); });
		await waitFor(() => expect(result.current.user).toEqual(B));
		expect(fetchMock.mock.calls[1][1]?.headers).toEqual({ Authorization: "Bearer token-B" });
	});

	it.each(["logout", "clear"])("limpia la identidad de otra pestaña con %s", async (kind) => {
		setAuth("token-A", A);
		fetchMock.mockResolvedValueOnce(response(A));
		const { result } = mount();
		await waitFor(() => expect(result.current.user).toEqual(A));
		act(() => { clearAuth(); storage(kind === "clear" ? null : "atlas_token"); });
		expect(result.current.user).toBeNull();
		expect(result.current.loading).toBe(false);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("no revalida por la escritura de usuario, otras claves o el mismo token", async () => {
		setAuth("token-A", A);
		fetchMock.mockResolvedValueOnce(response(A));
		const { result } = mount();
		await waitFor(() => expect(result.current.user).toEqual(A));
		act(() => { storage("atlas_user"); storage("theme"); storage(); storage(null); storage("atlas_token", sessionStorage); });
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(result.current.user).toEqual(A);
	});

	it("revalida una rotación de token aun con el mismo user_id", async () => {
		setAuth("token-A", A);
		fetchMock.mockResolvedValueOnce(response(A)).mockResolvedValueOnce(response({ ...A, role: "admin" }));
		const { result } = mount();
		await waitFor(() => expect(result.current.user).toEqual(A));
		act(() => { setAuth("token-A2", A); storage(); });
		await waitFor(() => expect(result.current.role).toBe("admin"));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it.each([401, 200])("descarta una respuesta tardía %s de A después de validar B", async (status) => {
		setAuth("token-A", A);
		const pendingA = deferred<Response>();
		fetchMock.mockReturnValueOnce(pendingA.promise).mockResolvedValueOnce(response(B));
		const { result } = mount();
		act(() => { setAuth("token-B", B); storage(); });
		await waitFor(() => expect(result.current.user).toEqual(B));
		await act(async () => { pendingA.resolve(response(A, status)); });
		expect(result.current.user).toEqual(B);
		expect(getToken()).toBe("token-B");
		expect(result.current.sessionExpiredMessage).toBeNull();
	});

	it("no copia una caché de A bajo B si /me de B falla", async () => {
		setAuth("token-A", A);
		fetchMock.mockResolvedValueOnce(response(A)).mockRejectedValueOnce(new TypeError("offline"));
		const { result } = mount();
		await waitFor(() => expect(result.current.user).toEqual(A));
		act(() => { localStorage.setItem("atlas_token", "token-B"); storage(); });
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.user).toBeNull();
		expect(getToken()).toBe("token-B");
	});

	it("descarta JSON tardío y aborta la validación anterior", async () => {
		setAuth("token-A", A);
		const bodyA = deferred<AuthUser>();
		const jsonA = vi.fn(() => bodyA.promise);
		fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: jsonA } as unknown as Response).mockResolvedValueOnce(response(B));
		const { result } = mount();
		await waitFor(() => expect(jsonA).toHaveBeenCalled());
		const signal = fetchMock.mock.calls[0][1]?.signal;
		act(() => { setAuth("token-B", B); storage(); });
		await waitFor(() => expect(result.current.user).toEqual(B));
		expect(signal?.aborted).toBe(true);
		await act(async () => { bodyA.resolve(A); });
		expect(result.current.user).toEqual(B);
	});

	it("unmount aborta y un 401 posterior no borra el token persistido", async () => {
		setAuth("token-A", A);
		const pending = deferred<Response>();
		fetchMock.mockReturnValueOnce(pending.promise);
		const { unmount } = mount();
		const signal = fetchMock.mock.calls[0][1]?.signal;
		unmount();
		expect(signal?.aborted).toBe(true);
		await act(async () => { pending.resolve(response(A, 401)); });
		expect(getToken()).toBe("token-A");
	});

	it("un 401 de la validación vigente cierra la sesión y termina la carga", async () => {
		setAuth("token-A", A);
		fetchMock.mockResolvedValueOnce(response(A, 401));
		const { result } = mount();
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.user).toBeNull();
		expect(result.current.sessionExpiredMessage).toContain("expiró");
		expect(getToken()).toBeNull();
	});

	it("logout local aborta /me y su respuesta no restaura la sesión", async () => {
		setAuth("token-A", A);
		const pending = deferred<Response>();
		fetchMock.mockReturnValueOnce(pending.promise);
		const { result } = mount();
		const signal = fetchMock.mock.calls[0][1]?.signal;
		await act(async () => { await result.current.signOut(); });
		expect(signal?.aborted).toBe(true);
		await act(async () => { pending.resolve(response(A)); });
		expect(result.current.user).toBeNull();
		expect(result.current.loading).toBe(false);
		expect(getToken()).toBeNull();
	});

	it("un login tardío no reemplaza la sesión B confirmada desde otra pestaña", async () => {
		const pendingLogin = deferred<Response>();
		fetchMock.mockReturnValueOnce(pendingLogin.promise).mockResolvedValueOnce(response(B));
		const { result } = mount();
		let login!: Promise<void>;
		act(() => { login = result.current.signIn(A.email, "synthetic"); });
		act(() => { setAuth("token-B", B); storage(); });
		await waitFor(() => expect(result.current.user).toEqual(B));
		await act(async () => {
			pendingLogin.resolve({ ok: true, status: 200, json: async () => ({ ...A, access_token: "token-A" }) } as Response);
			await login;
		});
		expect(result.current.user).toEqual(B);
		expect(getToken()).toBe("token-B");
	});

	it("StrictMode conserva la validación actual frente a un 401 del primer montaje", async () => {
		setAuth("token-A", A);
		const stale = deferred<Response>();
		fetchMock.mockReturnValueOnce(stale.promise).mockResolvedValueOnce(response(A));
		const { result } = renderHook(() => useAuth(), {
			reactStrictMode: true,
			wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
		});
		expect(fetchMock).toHaveBeenCalledTimes(2);
		await waitFor(() => expect(result.current.user).toEqual(A));
		expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
		await act(async () => { stale.resolve(response(A, 401)); });
		expect(result.current.user).toEqual(A);
		expect(getToken()).toBe("token-A");
		expect(result.current.sessionExpiredMessage).toBeNull();
	});
});

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
