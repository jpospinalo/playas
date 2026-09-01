"use client";

import {
	createContext,
	useContext,
	useEffect,
	useState,
	type ReactNode,
} from "react";
import {
	AUTH_SESSION_EXPIRED_EVENT,
	clearAuth,
	expireAuthSession,
	getStoredUser,
	getToken,
	rememberEmail,
	SESSION_EXPIRED_MESSAGE,
	setAuth,
	type AuthUser,
	type SessionExpiredDetail,
} from "@/lib/auth";
import { API_URL } from "@/lib/config";
import { readErrorDetail } from "@/lib/api";
import { withRestTimeout } from "@/lib/httpTimeout";

interface AuthContextValue {
	user: AuthUser | null;
	role: string | null;
	/** true mientras se resuelve el estado inicial de sesión desde localStorage */
	loading: boolean;
	/** Mensaje a mostrar en el login cuando la sesión se cerró por expiración, no por logout manual. */
	sessionExpiredMessage: string | null;
	signIn: (email: string, password: string) => Promise<void>;
	signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<AuthUser | null>(null);
	const [loading, setLoading] = useState(true);
	const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(
		null,
	);

	// Escucha el evento emitido por expireAuthSession()/throwIfSessionExpired()
	// desde cualquier llamada autenticada (lib/api.ts, hooks, componentes admin).
	// Es la única vía por la que un 401 tardío cierra la sesión: el listener
	// solo se activa cuando expireAuthSession confirmó que el token que
	// recibió el 401 seguía siendo el token activo, así que una respuesta
	// tardía de una sesión anterior nunca puede cerrar la sesión de un
	// usuario distinto que ya inició sesión después en la misma pestaña.
	useEffect(() => {
		function handleSessionExpired(event: Event) {
			const detail = (event as CustomEvent<SessionExpiredDetail>).detail;
			setUser(null);
			setSessionExpiredMessage(detail?.message ?? SESSION_EXPIRED_MESSAGE);
		}
		window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
		return () =>
			window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
	}, []);

	useEffect(() => {
		let cancelled = false;

		async function validateSession() {
			const token = getToken();
			if (!token) {
				if (!cancelled) setLoading(false);
				return;
			}

			// El token puede cambiar mientras esta solicitud está en curso (el
			// usuario cierra sesión e inicia como otro en otra pestaña, sin
			// recargar esta). canApplyResult() se vuelve a evaluar justo antes de
			// aplicar cualquier resultado no-401, para que una respuesta tardía de
			// `token` nunca sobrescriba ni restaure una sesión distinta de la que
			// está activa en ese momento.
			const canApplyResult = () => !cancelled && getToken() === token;

			try {
				const res = await fetch(`${API_URL}/api/auth/me`, {
					headers: { Authorization: `Bearer ${token}` },
					signal: withRestTimeout(),
				});
				if (res.status === 401) {
					// Sesión realmente inválida/expirada: expireAuthSession() ya
					// comprueba internamente que `token` siga siendo el activo, así
					// que no necesita canApplyResult() aquí. Dispara
					// AUTH_SESSION_EXPIRED_EVENT, que el listener de arriba atiende.
					expireAuthSession(token, SESSION_EXPIRED_MESSAGE);
					return;
				}
				if (!res.ok) {
					// Fallo transitorio (red inestable, 5xx, 403 inesperado...): no
					// eliminar una sesión que podría seguir siendo válida. Se usa la
					// identidad cacheada como estado provisional; cada endpoint sigue
					// autorizando por su cuenta, y un 401 posterior sí cerrará la
					// sesión. Solo se aplica si `token` sigue siendo el activo.
					if (canApplyResult()) setUser(getStoredUser());
					return;
				}
				const data = (await res.json()) as AuthUser;
				// El token también puede haber cambiado durante la espera de
				// res.json(), así que se vuelve a comprobar aquí, no solo antes
				// del fetch.
				if (canApplyResult()) {
					setAuth(token, data);
					setUser(data);
				}
			} catch {
				// Error de red: mismo criterio que arriba, no cerrar la sesión.
				if (canApplyResult()) setUser(getStoredUser());
			} finally {
				// Termina el estado de carga siempre que el componente siga
				// montado, incluso si `token` ya no es el activo: de lo contrario,
				// un cambio de sesión durante esta validación dejaría `loading`
				// bloqueado en true para siempre. No reactiva ni copia datos de
				// una sesión anterior — eso ya está condicionado arriba.
				if (!cancelled) setLoading(false);
			}
		}

		void validateSession();
		return () => {
			cancelled = true;
		};
	}, []);

	async function signIn(email: string, password: string): Promise<void> {
		const res = await fetch(`${API_URL}/api/auth/login`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ email, password }),
			signal: withRestTimeout(),
		});
		if (!res.ok) {
			// Mismo mensaje de respaldo de siempre ("credenciales incorrectas"),
			// pero leído con `readErrorDetail`: nunca muestra un cuerpo JSON
			// serializado si el backend responde con una forma inesperada, y
			// evita duplicar la lógica de lectura de `detail`.
			throw new Error(
				await readErrorDetail(res, "Correo o contraseña incorrectos."),
			);
		}
		const data = (await res.json()) as {
			access_token: string;
			user_id: string;
			email: string;
			display_name: string | null;
			role: string;
		};
		const authUser: AuthUser = {
			user_id: data.user_id,
			email: data.email,
			display_name: data.display_name,
			role: data.role,
		};
		setAuth(data.access_token, authUser);
		rememberEmail(data.email);
		setUser(authUser);
		setSessionExpiredMessage(null);
	}

	async function signOut(): Promise<void> {
		clearAuth();
		setUser(null);
		setSessionExpiredMessage(null);
	}

	return (
		<AuthContext.Provider
			value={{
				user,
				role: user?.role ?? null,
				loading,
				sessionExpiredMessage,
				signIn,
				signOut,
			}}
		>
			{children}
		</AuthContext.Provider>
	);
}

export function useAuth(): AuthContextValue {
	const ctx = useContext(AuthContext);
	if (!ctx) {
		throw new Error("useAuth debe usarse dentro de <AuthProvider>");
	}
	return ctx;
}
