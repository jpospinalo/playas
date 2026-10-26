"use client";

import { useState } from "react";
import Link from "next/link";
import { diaMes, numero, type Resumen } from "@/lib/admin/panel";
import { EstadoCalificacion, IconoAviso } from "@/components/admin/panel/Estados";

const VISIBLES = 8;

/**
 * "Dónde falla ATLAS": preguntas sin norma que las respalde o respondidas
 * con norma pero calificadas "no me sirvió", agrupadas por pregunta y
 * ordenadas por las veces que se repitieron. Es la lista de trabajo de los
 * abogados: qué contenido falta en la base.
 */
export function Brechas({ datos }: { datos: Resumen }) {
	const [todas, setTodas] = useState(false);
	const lista = todas ? datos.brechas : datos.brechas.slice(0, VISIBLES);
	const porTema = datos.temas.filter((t) => t.brechas > 0).sort((a, b) => b.brechas - a.brechas);

	return (
		<section className="pnl-bloque" aria-labelledby="t-brechas">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-brechas">Dónde falla ATLAS</h2>
					<p>
						{datos.brechas_total
							? `${numero(datos.brechas_total)} ${datos.brechas_total === 1 ? "pregunta" : "preguntas"} sin norma que la respalde o que la persona calificó como “no me sirvió”. Las más repetidas primero.`
							: "Ninguna pregunta quedó sin norma ni fue calificada como “no me sirvió” en este periodo."}
					</p>
				</div>
			</div>
			{porTema.length ? (
				<ul className="pnl-chips" aria-label="Brechas por tema">
					{porTema.map((t) => (
						<li key={t.id}>
							{t.titulo}
							<b className="num">{numero(t.brechas)}</b>
						</li>
					))}
				</ul>
			) : null}
			{lista.length ? (
				<table className="pnl-lista">
					<thead>
						<tr>
							<th scope="col">Pregunta</th>
							<th scope="col" className="num">
								Veces
							</th>
							<th scope="col">Tema</th>
							<th scope="col">Motivo</th>
							<th scope="col">Última vez</th>
							<th scope="col">
								<span className="sr">Acción</span>
							</th>
						</tr>
					</thead>
					<tbody>
						{lista.map((b) => (
							<tr key={`${b.conversation_id}-${b.pregunta}`}>
								<td className="preg">
									{b.pregunta}
									{b.esperaba ? <span className="pnl-esperaba">Esperaba: “{b.esperaba}”</span> : null}
								</td>
								<td data-l="Veces" className="num">
									{numero(b.veces)}
								</td>
								<td data-l="Tema">{b.tema_titulo}</td>
								<td data-l="Motivo">
									{b.motivo === "no_le_sirvio" ? (
										<EstadoCalificacion calificacion="no_util" />
									) : (
										<span className="pnl-estado ojo">
											<IconoAviso />
											Sin norma que la respalde
										</span>
									)}
								</td>
								<td data-l="Última vez" className="num">
									{diaMes(b.ultima)}
								</td>
								<td>
									<Link className="ver" href={`/admin/conversacion?id=${encodeURIComponent(b.conversation_id)}`}>
										Ver conversación
									</Link>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			) : null}
			{datos.brechas.length > VISIBLES ? (
				<button type="button" className="pnl-enlace" aria-expanded={todas} onClick={() => setTodas((t) => !t)}>
					{todas ? "Ver menos" : `Ver las ${numero(datos.brechas.length)} preguntas distintas`}
				</button>
			) : null}
		</section>
	);
}
