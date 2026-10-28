"use client";

import { useEffect, useState } from "react";
import {
	cuantas,
	mensajeError,
	numero,
	pedirResumen,
	textoPorcentaje,
	textoTasa,
	type FiltroResultado,
	type Resumen,
} from "@/lib/admin/panel";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { Periodo } from "@/components/admin/panel/Periodo";
import { Recientes, type OpcionFiltro } from "@/components/admin/panel/Recientes";
import { AparecerSi } from "@/components/admin/panel/Aparece";

const OPCIONES: OpcionFiltro[] = [
	{ valor: "calificadas", texto: "Todas las opiniones" },
	{ valor: "le_sirvio", texto: "Le sirvió" },
	{ valor: "no_le_sirvio", texto: "No le sirvió" },
	{ valor: "con_esperaba", texto: "Dijo lo que esperaba" },
];

/**
 * Opiniones sobre cada respuesta ("¿Esta respuesta le sirvió?"): cada una con
 * la pregunta, el tema, lo que la persona esperaba y el enlace a la
 * conversación (PQ-28). Filtro simple en vez de pertinencia/precisión
 * mín/máx (PQ-38); nombre de registro, nunca el correo (PQ-05).
 */
export default function PaginaOpiniones() {
	const [dias, setDias] = useState(0); // "Todo" por defecto (PQ-69)
	const [resultado, setResultado] = useState<FiltroResultado>("calificadas");
	const [resumen, setResumen] = useState<Resumen | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		pedirResumen(dias, "")
			.then((r) => {
				if (vigente) {
					setResumen(r);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las cifras."));
			});
		return () => {
			vigente = false;
		};
	}, [dias]);

	const c = resumen?.cifras;

	return (
		<div className="pnl-pag">
			<title>Opiniones sobre cada respuesta: panel de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Opiniones sobre cada respuesta</h1>
					<p className="pnl-sub">Lo que contestó cada persona en “¿Esta respuesta le sirvió?”.</p>
				</div>
				<div className="pnl-controles">
					<Periodo dias={dias} onCambio={setDias} />
				</div>
			</div>

			<AparecerSi valor={error}>
				{(error) => (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudieron cargar las cifras.</b>
							<p>{error}</p>
						</div>
					</div>
				)}
			</AparecerSi>

			{c ? (
				<dl className="pnl-cifras pnl-cifras-4">
					<div className="pnl-cifra">
						<dt>Opiniones</dt>
						<dd>
							<span className="pnl-valor num">{numero(c.calificaciones)}</span>
							<span className="pnl-det">
								De {cuantas(c.respuestas, "respuesta", "respuestas")} ({textoPorcentaje(c.calificaciones, c.respuestas)})
							</span>
						</dd>
					</div>
					<div className="pnl-cifra">
						<dt>Le sirvió</dt>
						<dd>
							<span className="pnl-valor num">{numero(c.le_sirvio)}</span>
							<span className="pnl-det">{textoTasa(c.le_sirvio, c.calificaciones)} de las opiniones</span>
						</dd>
					</div>
					<div className="pnl-cifra">
						<dt>No le sirvió</dt>
						<dd>
							<span className="pnl-valor num">{numero(c.no_le_sirvio)}</span>
							<span className="pnl-det">{textoTasa(c.no_le_sirvio, c.calificaciones)} de las opiniones</span>
						</dd>
					</div>
					{/* Estrellas del chat del equipo con nota 3: así las tres partes suman el total (PQ-43). */}
					<div className="pnl-cifra">
						<dt>Le sirvió a medias</dt>
						<dd>
							<span className="pnl-valor num">
								{numero(c.calificaciones - c.le_sirvio - c.no_le_sirvio)}
							</span>
							<span className="pnl-det">
								{textoTasa(c.calificaciones - c.le_sirvio - c.no_le_sirvio, c.calificaciones)} de
								las opiniones
							</span>
						</dd>
					</div>
				</dl>
			) : null}

			<Recientes
				key={dias}
				dias={dias}
				tema=""
				resultado={resultado}
				onResultado={setResultado}
				volver="/admin/message-feedback"
				titulo="Opiniones"
				descripcion="La pregunta, cómo respondió ATLAS, si le sirvió y lo que esperaba la persona."
				opciones={OPCIONES}
			/>
		</div>
	);
}
