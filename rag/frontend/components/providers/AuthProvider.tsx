"use client";

import {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useRef,
	useState,
	type ReactNode,
} from "react";
import {
	AUTH_SESSION_EXPIRED_EVENT,
	clearAuth,
	expireAuthSession,
	getStoredUser,
	getToken,
	isAuthStorageEvent,
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
	signUp: (
		email: string,
		password: string,
		displayName: string | null,
		userType: string | null,
	) => Promise<void>;
	signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<AuthUser | null>(null);
	const [loading, setLoading] = useState(true);
	const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(
		null,
	);
	const mounted = useRef(false);
	const generation = useRef(0);
	const observedToken = useRef<string | null>(null);
	const validationController = useRef<AbortController | null>(null);
	const invalidateValidation = useCallback(() => {
		generation.current += 1;
		validationController.current?.abort();
		validationController.current = null;
	}, []);

	useEffect(() => {
		mounted.current = true;
		function handleSessionExpired(event: Event) {
			const detail = (event as CustomEvent<SessionExpiredDetail>).detail;
			invalidateValidation();
			observedToken.current = null;
			setUser(null);
			setLoading(false);
			setSessionExpiredMessage(detail?.message ?? SESSION_EXPIRED_MESSAGE);
		}

		async function validateSession() {
			const token = getToken();
			invalidateValidation();
			const currentGeneration = generation.current;
			observedToken.current = token;
			setUser(null);
			setSessionExpiredMessage(null);
			setLoading(Boolean(token));
			if (!token) return;
			const controller = new AbortController();
			validationController.current = controller;
			const canApplyResult = () => mounted.current &&
				generation.current === currentGeneration && getToken() === token;

			try {
				const res = await fetch(`${API_URL}/api/auth/me`, {
					headers: { Authorization: `Bearer ${token}` },
					signal: withRestTimeout(controller.signal),
				});
				if (!canApplyResult()) return;
				if (res.status === 401) {
					expireAuthSession(token, SESSION_EXPIRED_MESSAGE);
					return;
				}
				if (!res.ok) {
					// La caché está vinculada al token; nunca toma la identidad de
					// otra sesión durante un fallo transitorio de /me.
					if (canApplyResult()) setUser(getStoredUser());
					return;
				}
				const data = (await res.json()) as AuthUser;
				if (canApplyResult()) {
					setAuth(token, data);
					setUser(data);
				}
			} catch {
				if (canApplyResult()) setUser(getStoredUser());
			} finally {
				if (canApplyResult()) {
					validationController.current = null;
					setLoading(false);
				}
			}
		}

		function handleStorage(event: StorageEvent) {
			if (isAuthStorageEvent(event) && getToken() !== observedToken.current) {
				void validateSession();
			}
		}
		window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
		window.addEventListener("storage", handleStorage);
		void validateSession();
		return () => {
			mounted.current = false;
			invalidateValidation();
			window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
			window.removeEventListener("storage", handleStorage);
		};
	}, [invalidateValidation]);

	async function signIn(email: string, password: string): Promise<void> {
		const initialGeneration = generation.current;
		const initialToken = getToken();
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
			user_type: string | null;
			role: string;
		};
		const authUser: AuthUser = {
			user_id: data.user_id,
			email: data.email,
			display_name: data.display_name,
			user_type: data.user_type,
			role: data.role,
		};
		if (!mounted.current || generation.current !== initialGeneration ||
			getToken() !== initialToken) return;
		invalidateValidation();
		setAuth(data.access_token, authUser);
		observedToken.current = data.access_token;
		rememberEmail(data.email);
		setUser(authUser);
		setLoading(false);
		setSessionExpiredMessage(null);
	}

	async function signUp(
		email: string,
		password: string,
		displayName: string | null,
		userType: string | null,
	): Promise<void> {
		const initialGeneration = generation.current;
		const initialToken = getToken();
		const res = await fetch(`${API_URL}/api/auth/register`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				email,
				password,
				display_name: displayName,
				user_type: userType,
			}),
			signal: withRestTimeout(),
		});
		if (!res.ok) {
			throw new Error(
				await readErrorDetail(res, "No se pudo completar el registro."),
			);
		}
		const data = (await res.json()) as {
			access_token: string;
			user_id: string;
			email: string;
			display_name: string | null;
			user_type: string | null;
			role: string;
		};
		const authUser: AuthUser = {
			user_id: data.user_id,
			email: data.email,
			display_name: data.display_name,
			user_type: data.user_type,
			role: data.role,
		};
		if (!mounted.current || generation.current !== initialGeneration ||
			getToken() !== initialToken) return;
		invalidateValidation();
		setAuth(data.access_token, authUser);
		observedToken.current = data.access_token;
		rememberEmail(data.email);
		setUser(authUser);
		setLoading(false);
		setSessionExpiredMessage(null);
	}

	async function signOut(): Promise<void> {
		invalidateValidation();
		clearAuth();
		observedToken.current = null;
		setUser(null);
		setLoading(false);
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
				signUp,
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
