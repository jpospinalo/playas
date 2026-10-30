"use client";

import { useId, useState } from "react";
import type { SourceFragment, SourceGroup } from "@/lib/types";
import { copiarTexto, datosFuente, nombreFuente, referenciaTexto, tipoDe } from "@/lib/referencia";

/** Hasta este largo el fragmento se muestra entero; si es más largo, se abre a pedido. */
export const LARGO_VISIBLE = 420;

interface FuenteProps {
	grupo: SourceGroup;
	fragmento: SourceFragment;
	marcada: boolean;
	/** Otras fuentes con el mismo párrafo (no se repiten en la lista). */
	tambien?: Array<{ indice: number; nombre: string }>;
}

/**
 * Una fuente de la respuesta (UX-01 con los datos que ya llegan): nombre
 * completo, datos de identificación sin cortar, el fragmento entero (con
 * "Ver todo el fragmento" si es largo) y "Copiar la referencia".
 */
export function Fuente({ grupo, fragmento, marcada, tambien = [] }: FuenteProps) {
	const [completo, setCompleto] = useState(false);
	const [copiado, setCopiado] = useState<"" | "ok" | "error">("");
	const idTexto = useId();

	const textoLimpio = fragmento.content.replace(/\s+/g, " ").trim();
	const largo = textoLimpio.length > LARGO_VISIBLE;
	const visible = largo && !completo ? `${textoLimpio.slice(0, LARGO_VISIBLE).trimEnd()}…` : textoLimpio;
	const datos = datosFuente(grupo, fragmento);

	async function copiar() {
		const ok = await copiarTexto(referenciaTexto(grupo, fragmento));
		setCopiado(ok ? "ok" : "error");
	}

	return (
		<li
			id={`fuente-${fragmento.index}`}
			tabIndex={-1}
			className={`guia-fuente${marcada ? " marcada" : ""}`}
		>
			<span className="num">Fuente {fragmento.index}.</span> {nombreFuente(grupo)}
			<span className="tipo">{tipoDe(grupo) === "normativa" ? "Norma" : "Sentencia"}</span>
			{tambien.length > 0 ? (
				<p className="tambien">
					El mismo párrafo aparece también como{" "}
					{tambien.map((t, i) => (
						<span key={t.indice}>
							{i > 0 ? "; " : ""}fuente {t.indice} ({t.nombre})
						</span>
					))}
					.
				</p>
			) : null}
			{datos.length > 0 ? (
				// E2-12: solo los datos que trae la fuente; el título aclara que
				// pueden faltar otros (no es una ficha oficial completa).
				<>
					<p className="datos-titulo">Datos disponibles de esta fuente:</p>
					<dl className="datos">
						{datos.map((d) => (
							<div key={d.etiqueta}>
								<dt>{d.etiqueta}:</dt> <dd>{d.valor}</dd>
							</div>
						))}
					</dl>
				</>
			) : null}
			<blockquote id={idTexto}>{visible}</blockquote>
			<div className="guia-fuente-acciones">
				{largo ? (
					<button
						type="button"
						className="guia-btn-sec"
						aria-expanded={completo}
						aria-controls={idTexto}
						onClick={() => setCompleto((c) => !c)}
					>
						{completo ? "Ver menos" : "Ver todo el fragmento"}
					</button>
				) : null}
				<button type="button" className="guia-btn-sec" onClick={() => void copiar()}>
					Copiar la referencia
				</button>
			</div>
			<p className="copiado" role="status">
				{copiado === "ok"
					? `Copiado: ${referenciaTexto(grupo, fragmento)}`
					: copiado === "error"
						? "No se pudo copiar. Puede seleccionar el texto y copiarlo a mano."
						: ""}
			</p>
		</li>
	);
}
