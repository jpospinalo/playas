"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSearchParams } from "next/navigation";
import {
	fechaHora,
	fechaLarga,
	mensajeError,
	pedirConversacion,
	sinMarcasDeCita,
	tipoDocumento,
	type Conversacion,
} from "@/lib/admin/panel";
import { EstadoCalificacion, EstadoResultado, IconoAviso } from "@/components/admin/panel/Estados";

/** Una conversación completa, para leer el caso desde el panel (solo lectura). */
export default function PaginaConversacion() {
	return (
		<div className="pnl-pag">
			<Suspense fallback={<p className="pnl-cargando">Cargando conversación…</p>}>
				<Detalle />
			</Suspense>
		</div>
	);
}

function Detalle() {
	const sp = useSearchParams();
	const id = sp.get("id") ?? "";
	// Filtros con los que se llegó desde el resumen (PQ-22).
	const volver = sp.get("volver") ?? "";
	// "volver" es la página de origen (/admin/feedback…) o los filtros del resumen.
	const desdeOtra = volver.startsWith("/admin/");
	const destino = desdeOtra ? volver : volver ? `/admin?${volver}` : "/admin";
	const [datos, setDatos] = useState<Conversacion | null>(null);
	const [error, setError] = useState<string | null>(id ? null : "Falta indicar qué conversación abrir.");

	useEffect(() => {
		if (!id) return;
		let vigente = true;
		pedirConversacion(id)
			.then((c) => {
				if (vigente) setDatos(c);
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo abrir la conversación."));
			});
		return () => {
			vigente = false;
		};
	}, [id]);

	return (
		<>
			<p className="pnl-volver">
				<Link href={destino} className="pnl-btn-sec">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
						<path d="M15 5l-7 7 7 7" />
					</svg>
					{desdeOtra ? "Volver" : "Volver al resumen"}
				</Link>
			</p>
			<title>
				{datos ? `Conversación de ${datos.persona}: panel de ATLAS` : "Conversación: panel de ATLAS"}
			</title>
			<h1>Conversación</h1>
			{error ? (
				<div className="pnl-error" role="alert" style={{ marginTop: 18 }}>
					<IconoAviso />
					<div>
						<b>No se pudo abrir la conversación.</b>
						<p>{error} Vuelva al resumen y elíjala de nuevo.</p>
					</div>
				</div>
			) : null}
			{!datos && !error ? <p className="pnl-cargando">Cargando conversación…</p> : null}
			{datos ? (
				<>
					<p className="pnl-sub" style={{ marginBottom: 18 }}>
						De {datos.persona}, empezó el {fechaLarga(datos.creada)}
					</p>
					<ol className="pnl-mensajes">
						{datos.mensajes.map((m) => {
							const esRespuesta = m.role === "assistant";
							return (
								<li key={m.id} className={`pnl-msj${esRespuesta ? " respuesta" : ""}`}>
									<div className="pnl-msj-cab">
										<b>{esRespuesta ? "Respuesta de ATLAS" : "Pregunta"}</b>
										<span className="num">{fechaHora(m.fecha)}</span>
									</div>
									{esRespuesta ? (
										// Las respuestas de ATLAS vienen en markdown; se muestra con
										// formato y sin HTML crudo (skipHtml), como en el chat (PQ-18).
										<div className="pnl-msj-texto pnl-md">
											<ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
												{sinMarcasDeCita(m.text)}
											</ReactMarkdown>
										</div>
									) : (
										<p className="pnl-msj-texto">{m.text}</p>
									)}
									{esRespuesta ? (
										<div className="pnl-msj-pie">
											<span className="pnl-msj-estados">
												{m.resultado ? <EstadoResultado
															resultado={m.resultado}
															fuentes={m.fuentes.length}
															sentencias={m.fuentes.filter((f) => f.doc_type === "jurisprudencia").length}
														/> : null}{" "}
												<EstadoCalificacion calificacion={m.calificacion} />
											</span>
											{m.esperaba ? <span className="pnl-esperaba">Esperaba: “{m.esperaba}”</span> : null}
											{m.fuentes.length ? (
												<div>
													<b>Fuentes citadas</b>
													<ul className="pnl-fuentes">
														{m.fuentes.map((f) => (
															<li key={f.nombre}>
																<span className={`pnl-etq${f.doc_type === "jurisprudencia" ? "" : " ley"}`}>
																	{tipoDocumento(f.doc_type)}
																</span>
																{f.nombre}
															</li>
														))}
													</ul>
												</div>
											) : null}
										</div>
									) : null}
								</li>
							);
						})}
					</ol>
				</>
			) : null}
		</>
	);
}
