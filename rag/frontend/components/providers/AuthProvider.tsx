"use client";

import {
	createContext,
	useContext,
	useEffect,
	useState,
	type ReactNode,
} from "react";
import {
	clearAuth,
	getStoredUser,
	setAuth,
	type AuthUser,
} from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

interface AuthContextValue {
	user: AuthUser | null;
	role: string | null;
	/** true mientras se resuelve el estado inicial de sesión desde localStorage */
	loading: boolean;
	signIn: (email: string, password: string) => Promise<void>;
	signUp: (email: string, password: string, displayName: string) => Promise<void>;
	signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<AuthUser | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		setUser(getStoredUser());
		setLoading(false);
	}, []);

	async function signIn(email: string, password: string): Promise<void> {
		const res = await fetch(`${API_URL}/api/auth/login`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ email, password }),
		});
		if (!res.ok) {
			const data = (await res.json().catch(() => ({}))) as {
				detail?: string;
			};
			throw new Error(data.detail ?? "Correo o contraseña incorrectos.");
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
		setUser(authUser);
	}

	async function signUp(
		email: string,
		password: string,
		displayName: string,
	): Promise<void> {
		const res = await fetch(`${API_URL}/api/auth/register`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ email, password, display_name: displayName }),
		});
		if (!res.ok) {
			const data = (await res.json().catch(() => ({}))) as {
				detail?: string;
			};
			throw new Error(data.detail ?? "Error al registrarse.");
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
		setUser(authUser);
	}

	async function signOut(): Promise<void> {
		clearAuth();
		setUser(null);
	}

	return (
		<AuthContext.Provider
			value={{
				user,
				role: user?.role ?? null,
				loading,
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
