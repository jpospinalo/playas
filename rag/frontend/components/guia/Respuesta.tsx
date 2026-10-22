"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SourceFragment, SourceGroup } from "@/lib/types";
import { markdownATexto, ordenarRespuesta, type RespuestaOrdenada } from "@/lib/guia/respuesta";
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
	onOtraPregunta: () => void;
	onEscribirDeNuevo: () => void;
	tituloRef: React.RefObject<HTMLHeadingElement | null>;
}

const LARGO_CITA = 420;

/** `[docN]` → enlace interno que el componente convierte en "(fuente N)". */
function prepararCitas(md: string): string {
	return md.replace(/\[doc(\d+)\]/gi, (_m, n) => `[(fuente ${n})](#fuente-${n})`);
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
					return (
						<button type="button" className="guia-cita" onClick={() => abrirFuente(n)}>
							{children}
						</button>
					);
				}
				return (
					<a href={href} target="_blank" rel="noopener noreferrer">
						{children}
					</a>
				);
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
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={componentes}>
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
	// En "sin evidencia" el título ya dice lo mismo que la línea "Situación".
	const resumen = ordenada.tipo === "sin-evidencia" ? "" : ordenada.resumen;

	function textoParaLeer(): string {
		const partes = [ordenada.titulo, ordenada.resumen];
		for (const s of ordenada.secciones) partes.push(s.titulo, s.cuerpo);
		return partes.map((p) => markdownATexto(p)).filter(Boolean).join("\n");
	}

	const sinRespuestaFirme = ordenada.tipo !== "normal";

	return (
		<>
			<button type="button" className="guia-volver" onClick={onOtraPregunta}>
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
					<ReactMarkdown remarkPlugins={[remarkGfm]} components={tituloEnLinea}>
						{prepararCitas(ordenada.titulo)}
					</ReactMarkdown>
				</h1>
				{resumen ? md(resumen, "resumen") : null}
			</section>

			<Escuchar texto={textoParaLeer} etiqueta="Escuchar la respuesta" />

			{ordenada.secciones.map((s, i) =>
				s.clase === "ojo" ? (
					<section key={i} className="guia-ojo" aria-labelledby={`sec-${i}`}>
						<Atencion />
						<div>
							<h2 id={`sec-${i}`}>{s.titulo}</h2>
							{md(s.cuerpo)}
						</div>
					</section>
				) : (
					<section key={i} aria-labelledby={`sec-${i}`}>
						<h2 id={`sec-${i}`}>{s.titulo}</h2>
						{s.cuerpo ? md(s.cuerpo, s.clase === "acudir" ? "acudir" : undefined) : null}
					</section>
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
	useEffect(() => {
		if (paso === "gracias" || paso === "error") mensajeRef.current?.focus();
		if (paso === "que-falto") document.getElementById("que-falto")?.focus();
	}, [paso]);

	async function enviar(c: Calificacion) {
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
		<div className="guia-sirvio">
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
							onClick={() => setPaso("que-falto")}
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
