"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { mensajeError, sinMarcasDeCita } from "@/lib/admin/panel";
import {
	guardarCalificacion,
	pedirFicha,
	pedirRubrica,
	type CalificacionIn,
	type Ficha,
	type Rubrica,
} from "@/lib/admin/evaluacion";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { EstadoEval } from "@/components/admin/evaluacion/EstadoEval";
import { FormCalificacion, TarjetaCalificacion } from "@/components/admin/evaluacion/FormCalificacion";
import { Hilo } from "@/components/admin/evaluacion/Hilo";
import { pedirDetalle, TEXTO_VALIDACION, type DetalleEvaluacion } from "@/lib/admin/validacion";

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
	const [aviso, setAviso] = useState<string | null>(null);
	const [errorGuardar, setErrorGuardar] = useState<string | null>(null);

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

	async function guardar(c: CalificacionIn, final: boolean) {
		setErrorGuardar(null);
		setAviso(null);
		try {
			const nueva = await guardarCalificacion(id, c, final);
			setFicha(nueva);
			setAviso(
				final
					? "Calificación final guardada."
					: nueva.estado === "con_diferencias"
						? "Guardada. Difiere de la otra calificación: pasa al comité."
						: "Calificación guardada.",
			);
		} catch (e) {
			setErrorGuardar(mensajeError(e, "No se pudo guardar."));
		}
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
			{error ? (
				<div className="pnl-error" role="alert">
					<IconoAviso />
					<div>
						<b>No se pudo abrir la pregunta.</b>
						<p>{error}</p>
					</div>
				</div>
			) : null}
			{!ficha && !error ? <p className="pnl-cargando">Cargando pregunta…</p> : null}
			{ficha && rubrica ? (
				<>
					<h1>Pregunta {ficha.numero}</h1>
					<p className="pnl-fila-meta" style={{ marginBottom: 14 }}>
						<span className="pnl-etq">{ficha.codigo}</span>
						{ficha.practica ? <span className="pnl-practica">Práctica: no cuenta</span> : null}
						<span>{ficha.tipo_playa_nombre ?? "Sin tipo"}</span>
						<span>
							{ficha.fecha}, {ficha.hora}
						</span>
						<EstadoEval estado={ficha.estado} />
					</p>

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

					{aviso ? (
						<p className="pnl-ok" role="status">
							{aviso}{" "}
							{ficha.siguiente ? (
								<Link href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(ficha.siguiente)}`}>
									Ir a la siguiente pregunta
								</Link>
							) : null}
						</p>
					) : null}
					{errorGuardar ? (
						<div className="pnl-error" role="alert">
							<IconoAviso />
							<div>
								<b>No se pudo guardar.</b>
								<p>{errorGuardar}</p>
							</div>
						</div>
					) : null}

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
								<p className="pnl-sub" style={{ marginBottom: 12 }}>
									Reemplaza a las de los semilleristas y queda como “Revisó” en la planilla.
								</p>
								<FormCalificacion
									key={`final-${ficha.final ? "si" : "no"}`}
									rubrica={rubrica}
									inicial={ficha.final ?? ficha.otras?.[0] ?? null}
									textoBoton={ficha.final ? "Actualizar la calificación final" : "Guardar la calificación final"}
									onGuardar={(c) => guardar(c, true)}
								/>
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

/** Reunión del 20-oct (T4): qué dijo la validadora y la conversación. */
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
	return (
		<section className="pnl-bloque" aria-labelledby="t-validacion">
			<h2 id="t-validacion">Validación de su calificación</h2>
			<p>
				<span className={`pnl-estado ${est === "validada" ? "bien" : est === "en_conversacion" ? "ojo" : "neutro"}`}>
					{TEXTO_VALIDACION[est]}
				</span>{" "}
				{est === "en_conversacion"
					? "La validadora no está de acuerdo. Lea su comentario, respóndale y, si corresponde, corrija la calificación arriba."
					: est === "por_validar"
						? "La validadora jurídica de su sede todavía no la revisa."
						: "La validadora está de acuerdo."}
			</p>
			<Hilo detalle={detalle} onCambio={setDetalle} etiqueta="Responder a la validadora" />
		</section>
	);
}

