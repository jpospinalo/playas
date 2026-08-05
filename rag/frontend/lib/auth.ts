/**
 * Gestión de sesión JWT en el cliente.
 * El token y los datos del usuario se almacenan en localStorage.
 */

const TOKEN_KEY = "atlas_token";
const USER_KEY = "atlas_user";
const LAST_EMAIL_KEY = "atlas_last_email";

export interface AuthUser {
	user_id: string;
	email: string;
	display_name: string | null;
	role: string;
}

export function getToken(): string | null {
	if (typeof window === "undefined") return null;
	return localStorage.getItem(TOKEN_KEY);
}

export function setAuth(token: string, user: AuthUser): void {
	localStorage.setItem(TOKEN_KEY, token);
	localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
	localStorage.removeItem(TOKEN_KEY);
	localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): AuthUser | null {
	if (typeof window === "undefined") return null;
	const raw = localStorage.getItem(USER_KEY);
	if (!raw) return null;
	try {
		return JSON.parse(raw) as AuthUser;
	} catch {
		return null;
	}
}

/**
 * Recuerda el último correo usado para iniciar sesión, para precargarlo
 * en el formulario de login la próxima vez (el usuario solo escribe la
 * contraseña). Se conserva incluso después de cerrar sesión.
 */
export function rememberEmail(email: string): void {
	localStorage.setItem(LAST_EMAIL_KEY, email);
}

export function getLastEmail(): string {
	if (typeof window === "undefined") return "";
	return localStorage.getItem(LAST_EMAIL_KEY) ?? "";
}
