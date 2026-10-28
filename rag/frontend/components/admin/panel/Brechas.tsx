"use client";

import { useState } from "react";
import Link from "next/link";
import { diaMes, enlaceConversacion, numero, recortar, type Resumen } from "@/lib/admin/panel";
import { EstadoCalificacion, IconoAviso } from "@/components/admin/panel/Estados";

const VISIBLES = 6;

/**
 * "Dónde falla ATLAS": preguntas sin norma que las respalde o respondidas
 * con norma pero calificadas "no me sirvió", agrupadas por pregunta y
 * ordenadas por las veces que se repitieron. Es la lista de trabajo de los
 * abogados: qué contenido falta en la base.
 */
export function Brechas({
	datos,
	volver,
	tema = "",
	onTema,
}: {
	datos: Resumen;
	volver: string;
	/** A11: el tema del filtro de arriba; tocar un tema filtra todo el resumen. */
	tema?: string;
	onTema?: (t: string) => void;
}) {
	const [todas, setTodas] = useState(false);
	const lista = todas ? datos.brechas : datos.brechas.slice(0, VISIBLES);
	const porTema = datos.temas.filter((t) => t.brechas > 0).sort((a, b) => b.brechas - a.brechas);

	return (
		<section className="pnl-bloque pnl-bloque-alerta" aria-labelledby="t-brechas">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-brechas">Dónde falla ATLAS</h2>
					<p>
						{datos.brechas_total
							? `${numero(datos.brechas_total)} ${datos.brechas_total === 1 ? "pregunta quedó" : "preguntas quedaron"} sin respuesta segura o la persona dijo que no le sirvió. Las más repetidas primero; no incluye preguntas fuera del tema de playas.`
							: "Ninguna pregunta quedó sin respuesta segura ni fue calificada como “no me sirvió” en este periodo."}
					</p>
				</div>
			</div>
			{porTema.length ? (
				<div className="pnl-chips-w">
					<p id="brechas-tema" className="pnl-chips-tit">
						{onTema ? "Por tema (toque uno para filtrar)" : "Por tema"}
					</p>
					<ul className={onTema ? "pnl-chips pnl-chips-filtro" : "pnl-chips"} aria-labelledby="brechas-tema">
						{porTema.map((t) => (
							<li key={t.id}>
								{onTema ? (
									<button
										type="button"
										aria-pressed={tema === t.id}
										onClick={() => onTema(tema === t.id ? "" : t.id)}
									>
										{t.titulo}
										<b className="num">{numero(t.brechas)}</b>
									</button>
								) : (
									<>
										{t.titulo}
										<b className="num">{numero(t.brechas)}</b>
									</>
								)}
							</li>
						))}
					</ul>
					{onTema && tema ? (
						<button type="button" className="pnl-enlace" onClick={() => onTema("")}>
							Quitar filtro de tema
						</button>
					) : null}
				</div>
			) : null}
			{lista.length ? (
				<div className="pnl-filas-cab" aria-hidden="true">
					<span>Pregunta</span>
					<span className="lado">
						<span>Veces</span>
						<span>Problema</span>
					</span>
				</div>
			) : null}
			{lista.length ? (
				<ol className="pnl-filas" aria-label="Preguntas donde falla ATLAS">
					{lista.map((b) => (
						<li key={`${b.conversation_id}-${b.pregunta}`} className="pnl-fila">
							<div className="pnl-fila-q">
								<Link href={enlaceConversacion(b.conversation_id, volver)}>
									{recortar(b.pregunta, 220)}
								</Link>
								<p className="pnl-fila-meta">
									<span className="pnl-etq">{b.tema_titulo}</span>
									<span>Última vez: {diaMes(b.ultima)}</span>
								</p>
								{b.esperaba ? <p className="pnl-esperaba">Esperaba: “{b.esperaba}”</p> : null}
							</div>
							<dl className="pnl-fila-estado pnl-dos">
								<div>
									<dt>Se repitió</dt>
									<dd className="pnl-veces">
										{numero(b.veces)} {b.veces === 1 ? "vez" : "veces"}
									</dd>
								</div>
								<div>
									<dt>Problema</dt>
									<dd>
										{b.motivo === "no_le_sirvio" ? (
											<EstadoCalificacion calificacion="no_util" />
										) : (
											<span className="pnl-estado ojo">
												<IconoAviso />
												Sin respuesta segura
											</span>
										)}
									</dd>
								</div>
							</dl>
						</li>
					))}
				</ol>
			) : null}
			{datos.brechas.length > VISIBLES ? (
				<button type="button" className="pnl-enlace" aria-expanded={todas} onClick={() => setTodas((t) => !t)}>
					{todas ? "Ver menos" : `Ver las ${numero(datos.brechas.length)} preguntas distintas`}
				</button>
			) : null}
		</section>
	);
}
