/**
 * Gestión de sesión JWT en el cliente.
 * El token y los datos del usuario se almacenan en localStorage.
 */

const TOKEN_KEY = "atlas_token";
const USER_KEY = "atlas_user";
const LAST_EMAIL_KEY = "atlas_last_email";

/**
 * Evento disparado en `window` cuando una llamada autenticada descubre que la
 * sesión activa ya no es válida (401 del backend). `AuthProvider` lo escucha
 * para limpiar el usuario en memoria y mostrar el login de nuevo.
 */
export const AUTH_SESSION_EXPIRED_EVENT = "atlas:session-expired";

export interface SessionExpiredDetail {
	message: string;
}

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

/**
 * Invalida la sesión actual, pero solo si `expectedToken` (el token que hizo
 * la llamada que recibió el 401) sigue siendo el token activo en este
 * momento. Esto hace la operación segura frente a carreras entre sesiones:
 * una respuesta 401 tardía de una solicitud lanzada por el usuario A no debe
 * poder cerrar la sesión del usuario B si este ya inició sesión después,
 * en la misma pestaña, sin recargar.
 *
 * Devuelve `true` si efectivamente cerró la sesión activa (y notificó vía
 * `AUTH_SESSION_EXPIRED_EVENT`); `false` si no hizo nada porque el token ya
 * no coincidía con el actual.
 */
export function expireAuthSession(expectedToken: string, message: string): boolean {
	if (typeof window === "undefined") return false;
	if (getToken() !== expectedToken) return false;
	clearAuth();
	window.dispatchEvent(
		new CustomEvent<SessionExpiredDetail>(AUTH_SESSION_EXPIRED_EVENT, {
			detail: { message },
		}),
	);
	return true;
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
