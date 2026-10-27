"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { diaHoraCalendario, mensajeError, sinMarcasDeCita } from "@/lib/admin/panel";
import {
	guardarCalificacion,
	pedirFicha,
	pedirRubrica,
	type CalificacionIn,
	type Ficha,
	type Rubrica,
} from "@/lib/admin/evaluacion";
import { ChipEstado, IconoAviso } from "@/components/admin/panel/Estados";
import { EstadoEval } from "@/components/admin/evaluacion/EstadoEval";
import { FormCalificacion, TarjetaCalificacion } from "@/components/admin/evaluacion/FormCalificacion";
import { Hilo } from "@/components/admin/evaluacion/Hilo";
import { pedirDetalle, TEXTO_VALIDACION, type DetalleEvaluacion } from "@/lib/admin/validacion";
import { AparecerSi } from "@/components/admin/panel/Aparece";

/** Ficha de una pregunta: calificar con la planilla o resolver como comité. */
export default function PaginaFicha() {
	return (
		<div className="pnl-pag">
			<Suspense fallback={<p className="pnl-cargando">Cargando pregunta…</p>}>
				<Ficha_ />
			</Suspense>
		</div>
	);
}

function Ficha_() {
	const id = useSearchParams().get("id") ?? "";
	const [ficha, setFicha] = useState<Ficha | null>(null);
	const [rubrica, setRubrica] = useState<Rubrica | null>(null);
	const [error, setError] = useState<string | null>(id ? null : "Falta indicar qué pregunta abrir.");

	useEffect(() => {
		if (!id) return;
		let vigente = true;
		Promise.all([pedirFicha(id), pedirRubrica()])
			.then(([f, r]) => {
				if (vigente) {
					setFicha(f);
					setRubrica(r);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo abrir la pregunta."));
			});
		return () => {
			vigente = false;
		};
	}, [id]);

	// J6-A1/A7: el resultado sale junto al botón y lleva a la siguiente pregunta.
	async function guardar(c: CalificacionIn, final: boolean) {
		const nueva = await guardarCalificacion(id, c, final);
		setFicha(nueva);
		const texto = final
			? "Calificación final guardada."
			: nueva.estado === "con_diferencias"
				? "Guardada. No coincide con la otra calificación: la revisa el comité."
				: "Calificación guardada.";
		return (
			<>
				{texto}
				{nueva.siguiente ? (
					<Link className="pnl-btn pnl-btn-chico" href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(nueva.siguiente)}`}>
						Ir a la siguiente pregunta
					</Link>
				) : null}
			</>
		);
	}

	return (
		<>
			<title>{ficha ? `Pregunta ${ficha.numero}: evaluación de ATLAS` : "Pregunta: evaluación de ATLAS"}</title>
			<p className="pnl-volver">
				<Link href="/admin/evaluacion" className="pnl-btn-sec">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
						<path d="M15 5l-7 7 7 7" />
					</svg>
					Volver a las preguntas
				</Link>
			</p>
			<AparecerSi valor={error}>
				{(error) => (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudo abrir la pregunta.</b>
							<p>{error}</p>
						</div>
					</div>
				)}
			</AparecerSi>
			{!ficha && !error ? <p className="pnl-cargando">Cargando pregunta…</p> : null}
			{ficha && rubrica ? (
				<>
					<h1>Pregunta {ficha.numero}</h1>
					<p className="pnl-fila-meta pnl-mb">
						<span className="pnl-etq">{ficha.codigo}</span>
						{ficha.practica ? <span className="pnl-practica">Práctica: no cuenta</span> : null}
						<span>{ficha.tipo_playa_nombre ?? "Sin tipo"}</span>
						<span>
							{diaHoraCalendario(ficha.fecha, ficha.hora)}
						</span>
						<EstadoEval estado={ficha.estado} />
					</p>
					{ficha.asignada_a?.length ? (
						<p className="pnl-sub pnl-mb">
							Asignada a: {ficha.asignada_a.join(" y ")}
						</p>
					) : null}

					<section className="pnl-bloque" aria-labelledby="t-preg">
						<h2 id="t-preg" className="sr">
							Pregunta formulada
						</h2>
						<p className="pnl-pregunta-texto">{ficha.pregunta}</p>
						{ficha.respuesta ? (
							<details className="pnl-plegable">
								<summary>Ver la respuesta de ATLAS</summary>
								<div className="pnl-md">
									<ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
										{sinMarcasDeCita(ficha.respuesta)}
									</ReactMarkdown>
								</div>
							</details>
						) : null}
					</section>

					{ficha.es_comite ? (
						<>
							<section className="pnl-bloque" aria-labelledby="t-comp">
								<h2 id="t-comp">Calificaciones de los semilleristas</h2>
								{ficha.otras && ficha.otras.length ? (
									<div className="pnl-comparar">
										{ficha.otras.map((c, i) => (
											<TarjetaCalificacion key={`${c.evaluador}-${i}`} c={c} titulo={`Calificación ${i + 1}`} />
										))}
									</div>
								) : (
									<p className="pnl-vacio">Todavía nadie la ha calificado.</p>
								)}
							</section>
							<section className="pnl-bloque" aria-labelledby="t-final">
								<h2 id="t-final">Calificación final del comité</h2>
								<p className="pnl-sub pnl-mb">
									Reemplaza a las de los semilleristas y queda como “Revisó” en la planilla.
								</p>
								{/* PQ-93: la fija la validación jurídica o el admin, cuando ya hay calificaciones. */}
								{ficha.puede_fijar_final && ficha.otras?.length ? (
									<FormCalificacion
										key={`final-${ficha.final ? "si" : "no"}`}
										rubrica={rubrica}
										inicial={ficha.final ?? ficha.otras?.[0] ?? null}
										textoBoton={ficha.final ? "Actualizar la calificación final" : "Guardar la calificación final"}
										onGuardar={(c) => guardar(c, true)}
									/>
								) : (
									<p className="pnl-vacio">
										{ficha.puede_fijar_final
											? "Se podrá fijar cuando los semilleristas la califiquen."
											: "La fija la validación jurídica (Ana María o Sandra) o el administrador."}
									</p>
								)}
							</section>
						</>
					) : (
						<section className="pnl-bloque" aria-labelledby="t-mia">
							<h2 id="t-mia">{ficha.mia ? "Su calificación" : "Calificar esta pregunta"}</h2>
							{!ficha.puede_evaluar && ficha.motivo_no_puede ? (
								<p className="pnl-aviso" role="note">
									<IconoAviso />
									<span>{ficha.motivo_no_puede}</span>
								</p>
							) : null}
							<FormCalificacion
								key={`mia-${ficha.mia ? "si" : "no"}`}
								rubrica={rubrica}
								inicial={ficha.mia}
								textoBoton={ficha.mia ? "Guardar cambios" : "Guardar calificación"}
								onGuardar={(c) => guardar(c, false)}
								deshabilitado={!ficha.puede_evaluar}
							/>
						</section>
					)}
					{!ficha.es_comite && ficha.mia?.id ? (
						<MiValidacion key={`${ficha.mia.id}-${ficha.mia.total}-${ficha.mia.ct}`} evaluacionId={ficha.mia.id} />
					) : null}

					<nav className="pnl-pagin" aria-label="Otras preguntas">
						<span />
						<div>
							{ficha.anterior ? (
								<Link className="pnl-btn-sec" href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(ficha.anterior)}`}>
									Pregunta anterior
								</Link>
							) : null}
							{ficha.siguiente ? (
								<Link className="pnl-btn-sec" href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(ficha.siguiente)}`}>
									Pregunta siguiente
								</Link>
							) : null}
						</div>
					</nav>
				</>
			) : null}
		</>
	);
}

/** Reunión del 20-oct (T4): qué dijo quien valida y la conversación. */
function MiValidacion({ evaluacionId }: { evaluacionId: string }) {
	const [detalle, setDetalle] = useState<DetalleEvaluacion | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		pedirDetalle(evaluacionId)
			.then((d) => {
				if (vigente) setDetalle(d);
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo cargar la validación."));
			});
		return () => {
			vigente = false;
		};
	}, [evaluacionId]);

	if (error) {
		return (
			<p className="pnl-error-linea" role="alert">
				{error}
			</p>
		);
	}
	if (!detalle) return null;
	const est = detalle.evaluacion.estado;
	// J6-A3: el nombre real de quien validó, o neutro si todavía no hay nadie.
	const quien = detalle.hilo.find((m) => m.autor !== detalle.evaluacion.evaluador)?.autor;
	return (
		<section className="pnl-bloque" aria-labelledby="t-validacion">
			<div className="pnl-titulo-estado">
				<h2 id="t-validacion">Validación de su calificación</h2>
				<ChipEstado tono={est === "validada" ? "bien" : est === "en_conversacion" ? "ojo" : "espera"}>
					{TEXTO_VALIDACION[est]}
				</ChipEstado>
			</div>
			<p>
				{est === "en_conversacion"
					? `${quien ?? "Quien valida"} no está de acuerdo. Lea su comentario, respóndale y, si corresponde, corrija la calificación arriba.`
					: est === "por_validar"
						? "Quien valida lo jurídico en su sede todavía no la revisa."
						: `${quien ?? "Quien valida"} está de acuerdo.`}
			</p>
			<Hilo detalle={detalle} onCambio={setDetalle} lado="semillerista" />
		</section>
	);
}

