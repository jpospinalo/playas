"use client";

import { type RefObject, useEffect, useRef, useState } from "react";
import { diaLargo, pedirVentana } from "@/lib/admin/calendario";
import { submitConversationFeedback } from "@/lib/api";

/**
 * Encuesta de percepción del ejercicio de validación (documento del profe,
 * p. 2, momento 3): al terminar, claridad de las respuestas, facilidad de
 * uso y percepción general. Se guarda en la misma tabla que la encuesta del
 * chat (`/api/feedback`), con las claves `clarity`, `usability` y `overall`.
 */

type Clave = "clarity" | "usability" | "overall";

const PREGUNTAS: { clave: Clave; texto: string; opciones: string[] }[] = [
	{
		clave: "clarity",
		texto: "¿Qué tan claras fueron las respuestas de ATLAS?",
		opciones: ["Nada claras", "Poco claras", "Más o menos", "Claras", "Muy claras"],
	},
	{
		clave: "usability",
		texto: "¿Qué tan fácil fue usar ATLAS?",
		opciones: ["Muy difícil", "Difícil", "Más o menos", "Fácil", "Muy fácil"],
	},
	{
		clave: "overall",
		texto: "En general, ¿cómo le pareció la experiencia?",
		opciones: ["Muy mala", "Mala", "Regular", "Buena", "Muy buena"],
	},
];

interface OpinionProps {
	tituloRef: RefObject<HTMLHeadingElement | null>;
	conversationId: string | null;
	onVolver: () => void;
	onOtraPregunta: () => void;
	onSalir: () => void;
	/** J5-5: avisa que ya la llenó (no se vuelve a ofrecer). */
	onEnviada?: () => void;
}

export function PantallaOpinion({
	tituloRef,
	conversationId,
	onVolver,
	onOtraPregunta,
	onSalir,
	onEnviada,
}: OpinionProps) {
	const [hasta, setHasta] = useState<string | null>(null);
	useEffect(() => {
		let vigente = true;
		pedirVentana()
			.then((v) => {
				if (vigente && v.dias_restantes >= 0) setHasta(diaLargo(v.ultimo_dia));
			})
			.catch(() => {
				// Sin la fecha se usa el cierre general del ejercicio.
			});
		return () => {
			vigente = false;
		};
	}, []);
	const [notas, setNotas] = useState<Partial<Record<Clave, number>>>({});
	const [comentario, setComentario] = useState("");
	const [paso, setPaso] = useState<"llenar" | "enviando" | "gracias">("llenar");
	const [error, setError] = useState<string | null>(null);
	const graciasRef = useRef<HTMLHeadingElement>(null);

	const faltan = PREGUNTAS.filter((p) => !notas[p.clave]);

	async function enviar(e: React.FormEvent) {
		e.preventDefault();
		if (faltan.length) {
			setError(
				faltan.length === 1
					? `Falta responder: “${faltan[0].texto}”`
					: `Faltan ${faltan.length} preguntas por responder.`,
			);
			return;
		}
		setError(null);
		setPaso("enviando");
		try {
			await submitConversationFeedback({
				ratings: { clarity: notas.clarity, usability: notas.usability, overall: notas.overall },
				comment: comentario.trim() || undefined,
				conversation_id: conversationId ?? undefined,
			});
			setPaso("gracias");
			onEnviada?.();
			requestAnimationFrame(() => graciasRef.current?.focus());
		} catch {
			setPaso("llenar");
			setError("No se pudo guardar su opinión. Revise la conexión e intente otra vez.");
		}
	}

	if (paso === "gracias") {
		return (
			<section aria-labelledby="titulo-gracias">
				<h1 id="titulo-gracias" ref={graciasRef} tabIndex={-1}>
					Gracias por su opinión
				</h1>
				<p>
					Puede seguir preguntando cuando quiera, desde su casa, hasta el {hasta ?? "20 de noviembre"}, con el mismo
					correo y clave. Quien participe más días puede ganar un bono.
				</p>
				<div className="guia-acciones">
					<button type="button" className="guia-btn" onClick={onOtraPregunta}>
						Volver al inicio
					</button>
				</div>
				{/* Celular compartido (QA E2-11): cerrar sesión es secundario y dice
				    para qué sirve; borra lo de esta persona antes de pasar el celular. */}
				<div className="guia-dejar">
					<button type="button" className="guia-btn-sec" onClick={onSalir} aria-describedby="dejar-ayuda">
						Terminar y dejar el celular para otra persona
					</button>
					<p id="dejar-ayuda" className="pista">
						Sale de ATLAS y borra de este celular su pregunta y su correo. Lo que preguntó queda guardado en
						ATLAS.
					</p>
				</div>
			</section>
		);
	}

	return (
		<form onSubmit={enviar} noValidate aria-labelledby="titulo">
			<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
				Su opinión sobre ATLAS
			</h1>
			<p className="ejemplo">Son 3 preguntas cortas. El comentario es opcional.</p>
			{PREGUNTAS.map((p) => (
				<fieldset key={p.clave} className="guia-opinion">
					<legend>{p.texto}</legend>
					<div className="guia-opinion-escala">
						{p.opciones.map((texto, i) => (
							<label key={texto} className={notas[p.clave] === i + 1 ? "elegida" : undefined}>
								<input
									type="radio"
									name={p.clave}
									value={i + 1}
									checked={notas[p.clave] === i + 1}
									onChange={() => setNotas((n) => ({ ...n, [p.clave]: i + 1 }))}
								/>
								<span>{texto}</span>
							</label>
						))}
					</div>
				</fieldset>
			))}
			<label className="grande" htmlFor="opinion-comentario">
				¿Quiere contarnos algo más? (opcional)
			</label>
			<textarea
				id="opinion-comentario"
				maxLength={500}
				value={comentario}
				onChange={(e) => setComentario(e.target.value)}
			/>
			{error ? (
				<p className="guia-error" role="alert">
					{error}
				</p>
			) : null}
			<div className="guia-acciones">
				<button type="submit" className="guia-btn" disabled={paso === "enviando"}>
					{paso === "enviando" ? "Guardando…" : "Enviar mi opinión"}
				</button>
				<button type="button" className="guia-btn-sec" onClick={onVolver}>
					Volver a la respuesta
				</button>
			</div>
		</form>
	);
}
