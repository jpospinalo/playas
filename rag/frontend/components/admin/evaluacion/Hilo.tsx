"use client";

import { useState } from "react";
import { fechaHora } from "@/lib/admin/panel";
import { comentar, type DetalleEvaluacion, type EntradaHilo } from "@/lib/admin/validacion";
import { ResultadoJunto, textoBoton, useAccion } from "@/components/admin/panel/Resultado";

const TIPO: Record<EntradaHilo["tipo"], string> = {
	comentario: "Comentario",
	desacuerdo: "No de acuerdo",
	acuerdo: "De acuerdo",
	correccion: "Corrección",
};

/**
 * Conversación sobre una evaluación (reunión del 20-oct, T4): quien valida y
 * el semillerista dan su punto de vista; las correcciones quedan con "antes →
 * después".
 *
 * J6-A2/A3: los textos siguen el estado y usan el nombre real. Quien calificó
 * (`lado="semillerista"`) solo ve el cuadro para responder cuando ya hay algo
 * a qué responder; quien valida le escribe a esa persona por su nombre.
 */
export function Hilo({
	detalle,
	onCambio,
	lado,
}: {
	detalle: DetalleEvaluacion;
	onCambio: (d: DetalleEvaluacion) => void;
	lado: "semillerista" | "validacion";
}) {
	const [texto, setTexto] = useState("");
	const accion = useAccion();
	const id = detalle.evaluacion.id.slice(0, 8);
	const quienCalifico = detalle.evaluacion.evaluador;
	const otro = detalle.hilo.find((m) => m.autor !== quienCalifico)?.autor;
	const etiqueta =
		lado === "validacion" ? `Escribirle a ${quienCalifico}` : `Responder a ${otro ?? "quien valida"}`;
	const puedeEscribir = lado === "validacion" || detalle.hilo.length > 0;

	async function enviar(e: React.FormEvent) {
		e.preventDefault();
		if (!texto.trim()) return;
		await accion.correr(
			async () => {
				onCambio(await comentar(detalle.evaluacion.id, texto.trim()));
				setTexto("");
				return "Mensaje enviado.";
			},
			{ error: "No se pudo enviar el mensaje." },
		);
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
				<p className="pnl-vacio">
					{lado === "semillerista"
						? "Cuando la validación se haga, aquí verá su comentario."
						: "Todavía no hay mensajes."}
				</p>
			)}
			{puedeEscribir ? (
				<form onSubmit={enviar} className="pnl-hilo-form">
					<label htmlFor={`hilo-${id}`}>{etiqueta}</label>
					<textarea id={`hilo-${id}`} value={texto} maxLength={2000} onChange={(e) => setTexto(e.target.value)} />
					<button type="submit" className="pnl-btn-sec" disabled={accion.enviando || !texto.trim()}>
						{textoBoton(accion.estado, { listo: "Enviar mensaje", enviando: "Enviando…", hecho: "Enviado" })}
					</button>
					<ResultadoJunto resultado={accion.resultado} />
				</form>
			) : null}
		</div>
	);
}
