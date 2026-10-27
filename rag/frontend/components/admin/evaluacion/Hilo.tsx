"use client";

import { useState } from "react";
import { fechaHora, mensajeError } from "@/lib/admin/panel";
import { comentar, type DetalleEvaluacion, type EntradaHilo } from "@/lib/admin/validacion";
import { AparecerSi } from "@/components/admin/panel/Aparece";

const TIPO: Record<EntradaHilo["tipo"], string> = {
	comentario: "Comentario",
	desacuerdo: "No de acuerdo",
	acuerdo: "De acuerdo",
	correccion: "Corrección",
};

/**
 * Conversación sobre una evaluación (reunión del 20-oct, T4): validadora y
 * semillerista dan su punto de vista; las correcciones quedan con "antes →
 * después".
 */
export function Hilo({
	detalle,
	onCambio,
	etiqueta = "Responder",
}: {
	detalle: DetalleEvaluacion;
	onCambio: (d: DetalleEvaluacion) => void;
	etiqueta?: string;
}) {
	const [texto, setTexto] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [enviando, setEnviando] = useState(false);
	const id = detalle.evaluacion.id.slice(0, 8);

	async function enviar(e: React.FormEvent) {
		e.preventDefault();
		if (!texto.trim()) return;
		setEnviando(true);
		setError(null);
		try {
			onCambio(await comentar(detalle.evaluacion.id, texto.trim()));
			setTexto("");
		} catch (err) {
			setError(mensajeError(err, "No se pudo enviar el mensaje."));
		} finally {
			setEnviando(false);
		}
	}

	return (
		<div className="pnl-hilo">
			{detalle.hilo.length ? (
				<ol className="pnl-hilo-lista">
					{detalle.hilo.map((m, i) => (
						<li key={`${m.fecha}-${i}`} className={`pnl-hilo-${m.tipo}`}>
							<p className="pnl-hilo-meta">
								<b>{m.autor}</b> ({TIPO[m.tipo]}), {fechaHora(m.fecha)}
							</p>
							<p className="pnl-hilo-texto">{m.texto}</p>
						</li>
					))}
				</ol>
			) : (
				<p className="pnl-vacio">Todavía no hay mensajes.</p>
			)}
			<form onSubmit={enviar} className="pnl-hilo-form">
				<label htmlFor={`hilo-${id}`}>{etiqueta}</label>
				<textarea id={`hilo-${id}`} value={texto} maxLength={2000} onChange={(e) => setTexto(e.target.value)} />
				<AparecerSi valor={error}>
					{(error) => (
						<p className="pnl-error-linea" role="alert">
							{error}
						</p>
					)}
				</AparecerSi>
				<button type="submit" className="pnl-btn-sec" disabled={enviando || !texto.trim()}>
					{enviando ? "Enviando…" : "Enviar mensaje"}
				</button>
			</form>
		</div>
	);
}
