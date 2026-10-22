"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SourceFragment, SourceGroup } from "@/lib/types";
import { lecturaRespuesta, markdownATexto, ordenarRespuesta, type RespuestaOrdenada } from "@/lib/guia/respuesta";
import { Atencion, Curvas, FlechaVolver } from "@/components/guia/iconos";
import { Escuchar } from "@/components/guia/Escuchar";

export type Calificacion = { util: boolean; comentario?: string };

interface RespuestaProps {
	pregunta: string;
	playa: string | null;
	texto: string;
	fuentes: SourceGroup[];
	/** La respuesta aún no quedó guardada: no se puede calificar todavía. */
	puedeCalificar: boolean;
	onCalificar: (c: Calificacion) => Promise<void>;
	onVolver: () => void;
	onOtraPregunta: () => void;
	onEscribirDeNuevo: () => void;
	tituloRef: React.RefObject<HTMLHeadingElement | null>;
}

const LARGO_CITA = 420;

/** `[docN]` → enlace interno que el componente convierte en "(fuente N)". */
function prepararCitas(md: string): string {
	return md
		// Bloques de código o estilo que mande el backend: fuera con su
		// contenido (skipHtml solo quita las etiquetas y dejaría el texto).
		.replace(/<(script|style|iframe|object|embed|noscript)\b[\s\S]*?<\/\1\s*>/gi, "")
		.replace(/\[doc(\d+)\]/gi, (_m, n) => `[(fuente ${n})](#fuente-${n})`);
}

function tipoDeFuente(grupo: SourceGroup): string {
	const tipo = grupo.doc_type ?? grupo.metadata?.doc_type;
	return tipo === "normativa" ? "Norma" : "Sentencia";
}

function recortar(texto: string): string {
	const t = texto.replace(/\s+/g, " ").trim();
	return t.length > LARGO_CITA ? `${t.slice(0, LARGO_CITA).trimEnd()}…` : t;
}

export function Respuesta({
	pregunta,
	playa,
	texto,
	fuentes,
	puedeCalificar,
	onCalificar,
	onVolver,
	onOtraPregunta,
	onEscribirDeNuevo,
	tituloRef,
}: RespuestaProps) {
	const ordenada = useMemo<RespuestaOrdenada>(() => ordenarRespuesta(texto), [texto]);
	const fuentesRef = useRef<HTMLDetailsElement>(null);
	const [marcada, setMarcada] = useState<number | null>(null);

	const fragmentos = useMemo(() => {
		const lista: Array<{ grupo: SourceGroup; fragmento: SourceFragment }> = [];
		for (const grupo of fuentes) for (const fragmento of grupo.fragments) lista.push({ grupo, fragmento });
		return lista.sort((a, b) => a.fragmento.index - b.fragmento.index);
	}, [fuentes]);
	const indices = useMemo(() => new Set(fragmentos.map((f) => f.fragmento.index)), [fragmentos]);

	const abrirFuente = useCallback((n: number) => {
		const det = fuentesRef.current;
		if (!det) return;
		det.open = true;
		setMarcada(n);
		requestAnimationFrame(() => {
			const item = document.getElementById(`fuente-${n}`);
			item?.focus();
		});
	}, []);

	const componentes = useMemo<Components>(
		() => ({
			a({ href, children }) {
				const m = href ? /^#fuente-(\d+)$/.exec(href) : null;
				if (m) {
					const n = Number(m[1]);
					// Una cita a un fragmento que no llegó no se muestra como enlace.
					if (!indices.has(n)) return null;
					// Enlace en línea (no botón) para poder darle un área de toque
					// alta con relleno sin mover el renglón (ver .guia-cita).
					return (
						<a
							href={`#fuente-${n}`}
							className="guia-cita"
							onClick={(e) => {
								e.preventDefault();
								abrirFuente(n);
							}}
						>
							{children}
						</a>
					);
				}
				// Solo enlaces web de verdad, en la misma pestaña (abrir pestañas
				// nuevas pierde a la persona; "atrás" vuelve a la respuesta
				// guardada). Cualquier otro (javascript:, vacío…) queda como texto.
				if (!href || !/^https?:\/\//i.test(href)) return <>{children}</>;
				return <a href={href}>{children}</a>;
			},
			table({ children }) {
				return (
					<div className="tabla">
						<table>{children}</table>
					</div>
				);
			},
			h1: ({ children }) => <p><strong>{children}</strong></p>,
			h2: ({ children }) => <p><strong>{children}</strong></p>,
			h3: ({ children }) => <p><strong>{children}</strong></p>,
			img: () => null,
		}),
		[indices, abrirFuente],
	);

	const md = (contenido: string, extra?: string): ReactNode => (
		<div className={`guia-md${extra ? ` ${extra}` : ""}`}>
			{/* skipHtml: si el backend manda HTML (<script>, <iframe>…) no se
			    muestra ni como código ni como elemento. */}
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={componentes} skipHtml>
				{prepararCitas(contenido)}
			</ReactMarkdown>
		</div>
	);

	// El título puede traer citas: se muestra con el mismo renderizador, en línea.
	const tituloEnLinea: Components = {
		...componentes,
		p: ({ children }) => <>{children}</>,
	};
	// Los títulos fijos de la interfaz (no salen de la respuesta) van un
	// poco más chicos que un "Sí." o "No." del backend.
	const tituloLargo = !/[.!?]$/.test(ordenada.titulo) || markdownATexto(ordenada.titulo).length > 40;
	const resumen = ordenada.resumen;

	const textoParaLeer = () => lecturaRespuesta(ordenada);

	const sinRespuestaFirme = ordenada.tipo !== "normal";

	return (
		<>
			<button type="button" className="guia-volver" onClick={onVolver}>
				<FlechaVolver />
				Volver
			</button>
			<p className="usted">
				Usted preguntó: <q>{pregunta}</q>
				{playa ? (
					<>
						, en <span className="lugar">{playa}</span>
					</>
				) : null}
			</p>

			<section className="guia-veredicto" aria-labelledby="titulo">
				<Curvas />
				<h1 id="titulo" ref={tituloRef} tabIndex={-1} className={tituloLargo ? "largo" : undefined}>
					<ReactMarkdown remarkPlugins={[remarkGfm]} components={tituloEnLinea} skipHtml>
						{prepararCitas(ordenada.titulo)}
					</ReactMarkdown>
				</h1>
				{resumen ? md(resumen, "resumen") : null}
			</section>

			<Escuchar texto={textoParaLeer} etiqueta="Escuchar la respuesta" />

			{ordenada.secciones.map((s, i) =>
				s.clase === "ojo" ? (
					// <div> y no <section> con nombre: el backend puede repetir
					// títulos y dos regiones con el mismo nombre confunden al
					// lector de pantalla (axe landmark-unique).
					<div key={i} className="guia-ojo">
						<Atencion />
						<div>
							<h2>{s.titulo}</h2>
							{md(s.cuerpo)}
						</div>
					</div>
				) : (
					<div key={i}>
						<h2>{s.titulo}</h2>
						{s.cuerpo ? md(s.cuerpo, s.clase === "acudir" ? "acudir" : undefined) : null}
					</div>
				),
			)}

			{fragmentos.length > 0 ? (
				<details className="guia-fuentes" ref={fuentesRef}>
					<summary>Ver de dónde sale esta respuesta</summary>
					<ol>
						{fragmentos.map(({ grupo, fragmento }) => (
							<li
								key={fragmento.index}
								id={`fuente-${fragmento.index}`}
								tabIndex={-1}
								className={`guia-fuente${marcada === fragmento.index ? " marcada" : ""}`}
							>
								<span className="num">Fuente {fragmento.index}.</span> {grupo.title || grupo.source}
								<span className="tipo">{tipoDeFuente(grupo)}</span>
								<blockquote>{recortar(fragmento.content)}</blockquote>
							</li>
						))}
					</ol>
				</details>
			) : null}

			{sinRespuestaFirme ? (
				<div className="guia-acciones">
					<button type="button" className="guia-btn-sec" onClick={onEscribirDeNuevo}>
						Escribir la pregunta de otra forma
					</button>
				</div>
			) : (
				<Sirvio puedeCalificar={puedeCalificar} onCalificar={onCalificar} />
			)}

			<div className="guia-final">
				<button type="button" className="guia-btn" onClick={onOtraPregunta}>
					Hacer otra pregunta
				</button>
			</div>
		</>
	);
}

function Sirvio({
	puedeCalificar,
	onCalificar,
}: {
	puedeCalificar: boolean;
	onCalificar: (c: Calificacion) => Promise<void>;
}) {
	const [paso, setPaso] = useState<"preguntar" | "que-falto" | "enviando" | "gracias" | "error">(
		"preguntar",
	);
	const [comentario, setComentario] = useState("");
	// Al cambiar el contenido del recuadro, el foco pasa al mensaje nuevo
	// (si no, se perdería en el <body> al desaparecer el botón tocado).
	const mensajeRef = useRef<HTMLParagraphElement>(null);
	// Alto mínimo del recuadro: al cambiar a "Gracias" no se encoge, así lo
	// que está debajo ("Hacer otra pregunta") no sube hasta el dedo de quien
	// tocó dos veces seguidas.
	const cajaRef = useRef<HTMLDivElement>(null);
	const [altoMinimo, setAltoMinimo] = useState<number | undefined>(undefined);
	function fijarAlto() {
		const alto = cajaRef.current?.offsetHeight;
		if (alto) setAltoMinimo((a) => Math.max(a ?? 0, alto));
	}
	useEffect(() => {
		if (paso === "gracias" || paso === "error") mensajeRef.current?.focus();
		if (paso === "que-falto") document.getElementById("que-falto")?.focus();
	}, [paso]);

	async function enviar(c: Calificacion) {
		fijarAlto();
		setPaso("enviando");
		try {
			await onCalificar(c);
			setPaso("gracias");
		} catch {
			setPaso("error");
		}
	}

	if (!puedeCalificar) return null;

	return (
		<div className="guia-sirvio" ref={cajaRef} style={altoMinimo ? { minHeight: altoMinimo } : undefined}>
			{paso === "preguntar" || paso === "enviando" ? (
				<>
					<p id="sirvio-pregunta">¿Esta respuesta le sirvió?</p>
					<div className="guia-acciones" role="group" aria-labelledby="sirvio-pregunta">
						<button
							type="button"
							className="guia-btn-sec"
							disabled={paso === "enviando"}
							onClick={() => enviar({ util: true })}
						>
							Sí
						</button>
						<button
							type="button"
							className="guia-btn-sec"
							disabled={paso === "enviando"}
							onClick={() => {
								fijarAlto();
								setPaso("que-falto");
							}}
						>
							No
						</button>
					</div>
				</>
			) : null}
			{paso === "que-falto" ? (
				<form
					onSubmit={(e) => {
						e.preventDefault();
						void enviar({ util: false, comentario: comentario.trim() || undefined });
					}}
				>
					<label className="grande" htmlFor="que-falto" style={{ marginTop: 0 }}>
						¿Qué le faltó? (si quiere)
					</label>
					<textarea
						id="que-falto"
						value={comentario}
						maxLength={1000}
						onChange={(e) => setComentario(e.target.value)}
					/>
					<div className="guia-acciones">
						<button type="submit" className="guia-btn">
							Enviar
						</button>
					</div>
				</form>
			) : null}
			{paso === "gracias" ? (
				<p className="gracias" role="status" ref={mensajeRef} tabIndex={-1}>
					Gracias. Su respuesta nos ayuda a mejorar ATLAS.
				</p>
			) : null}
			{paso === "error" ? (
				<p className="gracias" role="alert" ref={mensajeRef} tabIndex={-1}>
					No se pudo guardar su opinión. La respuesta de arriba sigue siendo válida.
				</p>
			) : null}
		</div>
	);
}
