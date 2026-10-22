"use client";

import { useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { getLastEmail } from "@/lib/auth";
import { restErrorMessage } from "@/lib/httpTimeout";
import { TXT } from "@/lib/guia/textos";

/** Pantalla de entrada del flujo guiado. Usa el mismo inicio de sesión de siempre. */
export function Entrar({ tituloRef }: { tituloRef: React.RefObject<HTMLHeadingElement | null> }) {
	const { signIn, sessionExpiredMessage } = useAuth();
	const [correo, setCorreo] = useState(() => (typeof window === "undefined" ? "" : getLastEmail()));
	const [clave, setClave] = useState("");
	const [mostrar, setMostrar] = useState(false);
	const [enviando, setEnviando] = useState(false);
	const [error, setError] = useState<string | null>(null);

	async function entrar(e: React.FormEvent) {
		e.preventDefault();
		if (!correo.trim() || !clave) {
			setError("Escriba el correo y la contraseña.");
			return;
		}
		setEnviando(true);
		setError(null);
		try {
			await signIn(correo.trim(), clave);
		} catch (err) {
			setError(restErrorMessage(err, "No se pudo entrar. Revise el correo y la contraseña."));
			setEnviando(false);
		}
	}

	const aviso = error ?? (sessionExpiredMessage ? "Por seguridad, vuelva a entrar." : null);

	return (
		<>
			<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
				{TXT.entrarTitulo}
			</h1>
			<p className="pista">{TXT.entrarPista}</p>
			<form noValidate onSubmit={entrar}>
				<label className="grande" htmlFor="correo">
					Correo
				</label>
				<input
					id="correo"
					type="email"
					autoComplete="email"
					inputMode="email"
					autoCapitalize="none"
					spellCheck={false}
					value={correo}
					onChange={(e) => setCorreo(e.target.value)}
				/>
				<label className="grande" htmlFor="clave">
					Contraseña
				</label>
				<input
					id="clave"
					type={mostrar ? "text" : "password"}
					autoComplete="current-password"
					value={clave}
					onChange={(e) => setClave(e.target.value)}
				/>
				<label className="guia-casilla">
					<input type="checkbox" checked={mostrar} onChange={(e) => setMostrar(e.target.checked)} />
					Mostrar la contraseña
				</label>
				{aviso ? (
					<p className="guia-error" role="alert">
						{aviso}
					</p>
				) : null}
				<div className="guia-acciones">
					<button className="guia-btn" type="submit" disabled={enviando}>
						{enviando ? "Entrando…" : "Entrar"}
					</button>
				</div>
			</form>
		</>
	);
}
