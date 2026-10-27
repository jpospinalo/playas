"use client";

import { type ReactNode, type RefObject, useEffect, useState } from "react";
import { autorizarPrivacidad, pedirPrivacidad, type Privacidad } from "@/lib/privacidad";

/**
 * Primer ingreso: aviso de privacidad y autorización de tratamiento de datos
 * (Ley 1581 de 2012, Decreto 1377 de 2013). Hasta autorizar no se ve el
 * flujo de preguntas; la autorización queda guardada con su fecha.
 */
export function ConPrivacidad({
	tituloRef,
	onSalir,
	children,
}: {
	tituloRef: RefObject<HTMLHeadingElement | null>;
	onSalir: () => void;
	children: ReactNode;
}) {
	const [estado, setEstado] = useState<Privacidad | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [acepto, setAcepto] = useState(false);
	const [enviando, setEnviando] = useState(false);
	const [intento, setIntento] = useState(0);

	useEffect(() => {
		let vigente = true;
		pedirPrivacidad()
			.then((p) => {
				if (vigente) {
					setEstado(p);
					setError(null);
				}
			})
			.catch(() => {
				if (vigente) setError("No se pudo cargar el aviso de privacidad. Revise la conexión.");
			});
		return () => {
			vigente = false;
		};
	}, [intento]);

	useEffect(() => {
		if (estado && !estado.aceptada) tituloRef.current?.focus();
	}, [estado, tituloRef]);

	if (estado?.aceptada) return <>{children}</>;

	if (error) {
		return (
			<section aria-labelledby="titulo">
				<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
					Un momento
				</h1>
				<p className="guia-error" role="alert">
					{error}
				</p>
				<div className="guia-acciones">
					<button type="button" className="guia-btn" onClick={() => setIntento((n) => n + 1)}>
						Intentar otra vez
					</button>
				</div>
			</section>
		);
	}

	if (!estado) {
		return (
			<p role="status" className="pista">
				Cargando…
			</p>
		);
	}

	async function autorizar(e: React.FormEvent) {
		e.preventDefault();
		if (!acepto) return;
		setEnviando(true);
		try {
			setEstado(await autorizarPrivacidad());
		} catch {
			setError("No se pudo guardar su autorización. Revise la conexión e intente otra vez.");
		} finally {
			setEnviando(false);
		}
	}

	return (
		<form className="guia-privacidad" onSubmit={autorizar} aria-labelledby="titulo">
			<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
				Antes de empezar: sus datos
			</h1>
			<p className="ejemplo">Léalo con calma. Solo se pide una vez.</p>
			<div className="guia-aviso-texto">
				{estado.parrafos.map((p) => (
					<p key={p.slice(0, 40)}>{p}</p>
				))}
				{/* PQ-110: correo para revocar la autorización; sin correo configurado no se inventa uno. */}
				{estado.correo ? (
					<p>
						Para revocar esta autorización o ejercer sus derechos, escriba a{" "}
						<a href={`mailto:${estado.correo}`}>{estado.correo}</a>.
					</p>
				) : null}
			</div>
			<label className="guia-casilla">
				<input type="checkbox" checked={acepto} onChange={(e) => setAcepto(e.target.checked)} />
				<span>
					Autorizo el tratamiento de mis datos para el ejercicio de validación de ATLAS, como dice este aviso.
				</span>
			</label>
			<div className="guia-acciones">
				<button type="submit" className="guia-btn" disabled={!acepto || enviando}>
					{enviando ? "Guardando…" : "Continuar"}
				</button>
				<button type="button" className="guia-btn-sec" onClick={onSalir}>
					No autorizo, salir
				</button>
			</div>
		</form>
	);
}
