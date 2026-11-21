import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAuth, expireAuthSession, getStoredUser, getToken, getTokenForUser, setAuth, type AuthUser } from "@/lib/auth";

const user: AuthUser = { user_id: "A", email: "a@example.test", display_name: null, role: "user" };
beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("caché de identidad ligada a la sesión", () => {
	it("devuelve la identidad solo para el token con que se guardó", () => {
		setAuth("token-A", user);
		expect(getStoredUser()).toEqual(user);
		localStorage.setItem("atlas_token", "token-B");
		expect(getStoredUser()).toBeNull();
	});
	it("no confía en una caché heredada sin vínculo aunque conserve un JWT", () => {
		localStorage.setItem("atlas_token", "token-B");
		localStorage.setItem("atlas_user", JSON.stringify(user));
		expect(getStoredUser()).toBeNull();
	});

	it("tolera caché corrupta y el cierre elimina la identidad", () => {
		setAuth("token-A", user);
		localStorage.setItem("atlas_user", "null");
		expect(getStoredUser()).toBeNull();
		setAuth("token-A", user);
		clearAuth();
		expect(getStoredUser()).toBeNull();
		expect(getToken()).toBeNull();
	});

	it("un 401 de A no invalida B y el de B sí cierra su sesión", () => {
		setAuth("token-B", user);
		expect(expireAuthSession("token-A")).toBe(false);
		expect(getStoredUser()).toEqual(user);
		expect(expireAuthSession("token-B")).toBe(true);
		expect(getToken()).toBeNull();
	});

	it("solo entrega la credencial ligada a la identidad esperada", () => {
		setAuth("token-A", user);
		expect(getTokenForUser("A")).toBe("token-A");
		expect(getTokenForUser("B")).toBeNull();
		localStorage.setItem("atlas_token", "token-B");
		expect(getTokenForUser("A")).toBeNull();
	});

	it("congela el token del mismo envelope aunque el almacenamiento rote durante la lectura", () => {
		setAuth("token-A", user);
		const read = Storage.prototype.getItem;
		vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key) {
			const value = read.call(this, key);
			if (key === "atlas_token") setAuth("token-B", { ...user, user_id: "B" });
			return value;
		});
		expect(getTokenForUser("A")).toBe("token-A");
	});
});
