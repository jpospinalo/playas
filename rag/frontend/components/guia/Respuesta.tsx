"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SourceFragment, SourceGroup } from "@/lib/types";
import { lecturaRespuesta, markdownATexto, ordenarRespuesta, type RespuestaOrdenada } from "@/lib/guia/respuesta";
import { Atencion, Curvas, FlechaVolver } from "@/components/guia/iconos";
import { Escuchar } from "@/components/guia/Escuchar";
import { CajaPregunta } from "@/components/guia/Pantallas";
import { Fuente } from "@/components/guia/Fuente";
import { agruparRepetidas } from "@/lib/guia/fuentes";
import { nombreFuente } from "@/lib/referencia";
import { YA_CALIFICADO } from "@/lib/api";
import { TXT } from "@/lib/guia/textos";

const TXT_NO_GUARDADA =
	"Esta respuesta no se pudo guardar. Puede seguir leyéndola. Para que quede registrada, toque «Guardar otra vez».";

export type Calificacion = { util: boolean; comentario?: string };

/** Una pregunta anterior del mismo tema, con su respuesta completa. */
export interface TurnoAnterior {
	/** id del mensaje de respuesta (para calificarla). */
	id: string;
	pregunta: string;
	playa: string | null;
	texto: string;
	fuentes: SourceGroup[];
	/** Ya la calificó en esta visita: true = le sirvió, false = no. */
	calificada?: boolean;
	puedeCalificar: boolean;
}

interface RespuestaProps {
	pregunta: string;
	playa: string | null;
	texto: string;
	fuentes: SourceGroup[];
	/** La respuesta aún no quedó guardada: no se puede calificar todavía. */
	puedeCalificar: boolean;
	onCalificar: (c: Calificacion) => Promise<void>;
	/** Ya calificó esta respuesta antes (al volver con "atrás" no se pregunta otra vez). */
	calificada?: boolean;
	onVolver: () => void;
	onOtraPregunta: () => void;
	/** Encuesta de percepción al terminar (momento 3 del ejercicio). */
	onTerminar?: () => void;
	/** J5-5: tras la primera respuesta, invitación corta a la encuesta. */
	invitarEncuesta?: boolean;
	onEscribirDeNuevo: () => void;
	/** Lo escrito en la caja de seguimiento (vive afuera, como el borrador del inicio). */
	seguimiento: string;
	onCambioSeguimiento: (texto: string) => void;
	/** Pregunta de seguimiento: sigue la misma conversación. */
	onSeguir: (texto: string) => void;
	/** Ya van varias respuestas seguidas: aviso sobre lo que ATLAS recuerda. */
	muchasSeguidas: boolean;
	/** false si la conversación ya no está abierta (respuesta guardada tras recargar). */
	puedeSeguir?: boolean;
	/** Preguntas anteriores del mismo tema (hilo), de la primera a la última. */
	anteriores?: TurnoAnterior[];
	onCalificarAnterior?: (id: string, c: Calificacion) => Promise<void>;
	/** Estado del guardado de la respuesta (UX-02; sin valor = no aplica, p. ej. recuperada). */
	guardado?: "ok" | "guardando" | "fallo";
	onGuardarOtraVez?: () => void;
	tituloRef: React.RefObject<HTMLHeadingElement | null>;
}

/** `[docN]` → enlace interno que el componente convierte en "(fuente N)". */
function prepararCitas(md: string, prefijo = ""): string {
	return md
		// Bloques de código o estilo que mande el backend: fuera con su
		// contenido (skipHtml solo quita las etiquetas y dejaría el texto).
		.replace(/<(script|style|iframe|object|embed|noscript)\b[\s\S]*?<\/\1\s*>/gi, "")
		.replace(/\[doc(\d+)\]/gi, (_m, n) => `[(fuente ${n})](#${prefijo}fuente-${n})`)
		// QA-F10: "construcción/ocupación" no tiene dónde partirse y, con letra
		// grande, se salía o se cortaba a mitad de palabra. Un corte invisible
		// después de la barra deja partir ahí (solo entre letras: no toca
		// fechas, y las palabras que son enlaces quedan intactas).
		.split(/(\s+)/)
		.map((t) => (/https?:|www\.|\]\(|#/i.test(t) ? t : t.replace(/(\p{L})\/(?=\p{L})/gu, "$1/\u200B")))
		.join("");
}

function tipoDeFuente(grupo: SourceGroup): string {
	const tipo = grupo.doc_type ?? grupo.metadata?.doc_type;
	return tipo === "normativa" ? "Norma" : "Sentencia";
}

/**
 * Cuerpo de una respuesta: veredicto, partes y fuentes. Completo para la
 * respuesta actual (h1, h2 y fuentes que se abren) y compacto dentro del
 * hilo (sin h1, títulos h4, fuentes en lista: no se anida un "details" dentro
 * de otro). `prefijo` separa los ids de las fuentes de cada respuesta.
 */
function Contenido({
	texto,
	fuentes,
	prefijo,
	compacto,
	tituloRef,
	pie,
}: {
	texto: string;
	fuentes: SourceGroup[];
	prefijo: string;
	compacto: boolean;
	tituloRef?: React.RefObject<HTMLHeadingElement | null>;
	/** Lo que va justo después del veredicto (p. ej. "Escuchar"). */
	pie?: ReactNode;
}) {
	const ordenada = useMemo<RespuestaOrdenada>(() => ordenarRespuesta(texto), [texto]);
	const fuentesRef = useRef<HTMLDetailsElement>(null);
	const [marcada, setMarcada] = useState<number | null>(null);

	const fragmentos = useMemo(() => {
		const lista: Array<{ grupo: SourceGroup; fragmento: SourceFragment }> = [];
		for (const grupo of fuentes) for (const fragmento of grupo.fragments) lista.push({ grupo, fragmento });
		return lista.sort((a, b) => a.fragmento.index - b.fragmento.index);
	}, [fuentes]);
	const indices = useMemo(() => new Set(fragmentos.map((f) => f.fragmento.index)), [fragmentos]);
	// Dos fuentes con el mismo párrafo se muestran una vez ("también aparece
	// como fuente N"); una cita a la repetida abre la que quedó.
	const { unicas, canonica } = useMemo(() => agruparRepetidas(fragmentos, nombreFuente), [fragmentos]);
	// QA-F08: en la lista corta del hilo, varios fragmentos del mismo
	// documento parecían la misma fuente repetida. Ahí se agrupan por
	// documento ("Fuentes 1, 3 y 4. Decreto…") y una cita a cualquiera de
	// ellos lleva a esa línea.
	const porDocumento = useMemo(() => {
		const grupos: Array<{ nombre: string; tipo: string; primero: number; indices: number[] }> = [];
		const destino = new Map<number, number>();
		for (const u of unicas) {
			const nombre = nombreFuente(u.grupo);
			let g = grupos.find((x) => x.nombre === nombre);
			if (!g) {
				g = { nombre, tipo: tipoDeFuente(u.grupo), primero: u.fragmento.index, indices: [] };
				grupos.push(g);
			}
			for (const n of [u.fragmento.index, ...u.tambien.map((t) => t.indice)]) {
				g.indices.push(n);
				destino.set(n, g.primero);
			}
		}
		for (const g of grupos) g.indices.sort((a, b) => a - b);
		return { grupos, destino };
	}, [unicas]);
	const destinoDe = useCallback(
		(cita: number) => {
			const n = canonica.get(cita) ?? cita;
			return compacto ? (porDocumento.destino.get(n) ?? n) : n;
		},
		[canonica, compacto, porDocumento],
	);

	const abrirFuente = useCallback(
		(cita: number) => {
			const n = destinoDe(cita);
			if (fuentesRef.current) fuentesRef.current.open = true;
			setMarcada(n);
			requestAnimationFrame(() => {
				document.getElementById(`${prefijo}fuente-${n}`)?.focus();
			});
		},
		[prefijo, destinoDe],
	);

	const componentes = useMemo<Components>(
		() => ({
			a({ href, children }) {
				const m = href ? /^#(?:t\d+-)?fuente-(\d+)$/.exec(href) : null;
				if (m) {
					const n = Number(m[1]);
					// Una cita a un fragmento que no llegó no se muestra como enlace.
					if (!indices.has(n)) return null;
					// Enlace en línea (no botón) para poder darle un área de toque
					// alta con relleno sin mover el renglón (ver .guia-cita).
					return (
						<a
							href={`#${prefijo}fuente-${destinoDe(n)}`}
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
		[indices, abrirFuente, prefijo, destinoDe],
	);

	const md = (contenido: string, extra?: string): ReactNode => (
		<div className={`guia-md${extra ? ` ${extra}` : ""}`}>
			{/* skipHtml: si el backend manda HTML (<script>, <iframe>…) no se
			    muestra ni como código ni como elemento. */}
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={componentes} skipHtml>
				{prepararCitas(contenido, prefijo)}
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
	const titulo = (
		<ReactMarkdown remarkPlugins={[remarkGfm]} components={tituloEnLinea} skipHtml>
			{prepararCitas(ordenada.titulo, prefijo)}
		</ReactMarkdown>
	);
	// En el hilo los títulos bajan un nivel bajo el h3 de cada pregunta.
	const H = compacto ? "h4" : "h2";

	return (
		<>
			{compacto ? (
				<div className="guia-veredicto compacto">
					<p className="titulo">{titulo}</p>
					{ordenada.resumen ? md(ordenada.resumen, "resumen") : null}
				</div>
			) : (
				<section className="guia-veredicto" aria-labelledby="titulo">
					<Curvas />
					<h1 id="titulo" ref={tituloRef} tabIndex={-1} className={tituloLargo ? "largo" : undefined}>
						{titulo}
					</h1>
					{ordenada.resumen ? md(ordenada.resumen, "resumen") : null}
				</section>
			)}

			{pie}

			{ordenada.secciones.map((s, i) =>
				s.clase === "ojo" ? (
					// <div> y no <section> con nombre: el backend puede repetir
					// títulos y dos regiones con el mismo nombre confunden al
					// lector de pantalla (axe landmark-unique).
					<div key={i} className="guia-ojo">
						<Atencion />
						<div>
							<H>{s.titulo}</H>
							{md(s.cuerpo)}
						</div>
					</div>
				) : (
					<div key={i}>
						<H>{s.titulo}</H>
						{s.cuerpo ? md(s.cuerpo, s.clase === "acudir" ? "acudir" : undefined) : null}
					</div>
				),
			)}

			{fragmentos.length === 0 ? null : compacto ? (
				<div className="guia-fuentes compacto">
					<H>De dónde sale esta respuesta</H>
					<ol>
						{porDocumento.grupos.map((g) => (
							<li
								key={g.primero}
								id={`${prefijo}fuente-${g.primero}`}
								tabIndex={-1}
								className={`guia-fuente${marcada === g.primero ? " marcada" : ""}`}
							>
								<span className="num">
									{g.indices.length > 1
										? `Fuentes ${g.indices.slice(0, -1).join(", ")} y ${g.indices[g.indices.length - 1]}.`
										: `Fuente ${g.primero}.`}
								</span>{" "}
								{g.nombre}
								<span className="tipo">
									{g.tipo}
									{g.indices.length > 1 ? `. ${g.indices.length} partes del mismo documento` : ""}
								</span>
							</li>
						))}
					</ol>
				</div>
			) : (
				<details className="guia-fuentes" ref={fuentesRef}>
					<summary>Ver de dónde sale esta respuesta</summary>
					<ol>
						{/* UX-01: nombre completo, datos de identificación, fragmento
						    entero a pedido y "Copiar la referencia". */}
						{unicas.map(({ grupo, fragmento, tambien }) => (
							<Fuente
								key={fragmento.index}
								grupo={grupo}
								fragmento={fragmento}
								marcada={marcada === fragmento.index}
								tambien={tambien}
							/>
						))}
					</ol>
				</details>
			)}
		</>
	);
}

/** Lo que ya preguntó sobre este tema: una línea por pregunta, se abre al tocarla. */
function Hilo({
	anteriores,
	onCalificar,
}: {
	anteriores: TurnoAnterior[];
	onCalificar?: (id: string, c: Calificacion) => Promise<void>;
}) {
	// QA-F12: con más de 3 preguntas anteriores, en el celular había que
	// pasar ~850 px de tarjetas antes de la respuesta actual. Se muestran las
	// 2 últimas y un botón para ver las demás (la numeración no cambia).
	const [todas, setTodas] = useState(false);
	const ocultas = !todas && anteriores.length > 3 ? anteriores.length - 2 : 0;
	return (
		<section className="guia-hilo" aria-labelledby="hilo-titulo">
			<h2 id="hilo-titulo">Lo que ya preguntó sobre este tema</h2>
			{ocultas > 0 ? (
				<button
					type="button"
					className="guia-btn-sec guia-hilo-mas"
					aria-expanded={false}
					onClick={(e) => {
						const seccion = e.currentTarget.closest(".guia-hilo");
						setTodas(true);
						// El botón desaparece: el foco pasa a la primera pregunta.
						requestAnimationFrame(() => seccion?.querySelector<HTMLElement>("summary")?.focus());
					}}
				>
					Ver las {ocultas} preguntas anteriores
				</button>
			) : null}
			<ol start={ocultas + 1}>
				{anteriores.slice(ocultas).map((t, j) => {
					const i = j + ocultas;
					const n = i + 1;
					const firme = ordenarRespuesta(t.texto).tipo === "normal";
					return (
						<li key={t.id}>
							<details>
								<summary>
									<span className="n" aria-hidden="true">
										{n}
									</span>
									<span className="q">
										<span className="sr">Pregunta {n}: </span>
										{t.pregunta}
										{t.playa ? (
											<>
												, en <span className="lugar">{t.playa}</span>
											</>
										) : null}
									</span>
									<span className="abrir" aria-hidden="true" />
								</summary>
								<div className="cuerpo">
									<Contenido texto={t.texto} fuentes={t.fuentes} prefijo={`t${n}-`} compacto />
									{firme && onCalificar ? (
										<Sirvio
											puedeCalificar={t.puedeCalificar}
											calificada={t.calificada}
											onCalificar={(c) => onCalificar(t.id, c)}
										/>
									) : null}
								</div>
							</details>
						</li>
					);
				})}
			</ol>
		</section>
	);
}

export function Respuesta({
	pregunta,
	playa,
	texto,
	fuentes,
	puedeCalificar,
	onCalificar,
	calificada,
	onVolver,
	onOtraPregunta,
	onTerminar,
	invitarEncuesta = false,
	onEscribirDeNuevo,
	seguimiento,
	onCambioSeguimiento,
	onSeguir,
	muchasSeguidas,
	puedeSeguir = true,
	anteriores = [],
	onCalificarAnterior,
	guardado,
	onGuardarOtraVez,
	tituloRef,
}: RespuestaProps) {
	const ordenada = useMemo<RespuestaOrdenada>(() => ordenarRespuesta(texto), [texto]);
	const textoParaLeer = () => lecturaRespuesta(ordenada);
	const sinRespuestaFirme = ordenada.tipo !== "normal";
	const numero = anteriores.length + 1;
	// Se puede seguir en el mismo tema con una respuesta firme, cuando ATLAS
	// pidió más datos (se contestan aquí mismo) y cuando no hubo respuesta
	// segura (precisar la pregunta sin perder lo conversado, QA-F02). "Fuera
	// de tema" solo dentro de un hilo (QA-F01: un seguimiento mal entendido no
	// corta el tema). Un saludo: no.
	const seguirAqui =
		puedeSeguir &&
		(ordenada.tipo === "normal" ||
			ordenada.tipo === "aclaracion" ||
			ordenada.tipo === "sin-evidencia" ||
			(ordenada.tipo === "fuera-de-tema" && anteriores.length > 0));

	// "Escribir la pregunta de otra forma": si se puede seguir aquí, la
	// pregunta va a la caja de esta misma pantalla (mismo tema, con lo ya
	// conversado). Si no, empieza de cero en el inicio y el botón lo dice.
	function escribirDeOtraForma() {
		if (!seguirAqui) {
			onEscribirDeNuevo();
			return;
		}
		onCambioSeguimiento(pregunta);
		requestAnimationFrame(() => {
			const caja = document.getElementById("seguimiento") as HTMLTextAreaElement | null;
			caja?.scrollIntoView({ block: "center" });
			caja?.focus();
		});
	}

	return (
		<>
			<button type="button" className="guia-volver" onClick={onVolver}>
				<FlechaVolver />
				Volver
			</button>

			{anteriores.length > 0 ? <Hilo anteriores={anteriores} onCalificar={onCalificarAnterior} /> : null}

			<p className="usted">
				{numero > 1 ? <span className="numero">Pregunta {numero} de este tema. </span> : null}
				Usted preguntó: <q>{pregunta}</q>
				{playa ? (
					<>
						, en <span className="lugar">{playa}</span>
					</>
				) : null}
			</p>

			<Contenido
				texto={texto}
				fuentes={fuentes}
				prefijo=""
				compacto={false}
				tituloRef={tituloRef}
				pie={<Escuchar texto={textoParaLeer} etiqueta="Escuchar la respuesta" />}
			/>

			{guardado === "fallo" || guardado === "guardando" ? (
				<div className="guia-aviso-guardado" role="status">
					<p>{guardado === "guardando" ? "Guardando la respuesta…" : TXT_NO_GUARDADA}</p>
					{guardado === "fallo" && onGuardarOtraVez ? (
						<button type="button" className="guia-btn-sec" onClick={onGuardarOtraVez}>
							Guardar otra vez
						</button>
					) : null}
				</div>
			) : null}

			{sinRespuestaFirme ? (
				<div className="guia-acciones">
					<button type="button" className="guia-btn-sec" onClick={escribirDeOtraForma}>
						{seguirAqui ? "Escribir la pregunta de otra forma" : "Escribir la pregunta de otra forma (empieza de cero)"}
					</button>
				</div>
			) : (
				<Sirvio puedeCalificar={puedeCalificar} calificada={calificada} onCalificar={onCalificar} />
			)}
			{invitarEncuesta && onTerminar ? (
				<div className="guia-invita">
					<p>¿Ya va a terminar por hoy? Cuéntenos cómo le fue (3 preguntas).</p>
					<button type="button" className="guia-btn-sec" onClick={onTerminar}>
						Dar mi opinión
					</button>
				</div>
			) : null}

			{/* Seguimiento: misma conversación; la respuesta nueva llega en otra
			    pantalla con todo lo anterior plegado arriba. */}
			{!seguirAqui ? null : (
				<section className="guia-seguir" aria-labelledby="seguir-titulo">
					<h2 id="seguir-titulo">{TXT.seguirTitulo}</h2>
					<p id="seguir-recuerda" className="pista">
						{TXT.seguirRecuerda}
					</p>
					{muchasSeguidas ? (
						<p className="guia-tope" role="note">
							{TXT.seguirTope}
						</p>
					) : null}
					<CajaPregunta
						id="seguimiento"
						valor={seguimiento}
						onCambio={onCambioSeguimiento}
						onPreguntar={onSeguir}
						pista={TXT.seguirPista}
						etiqueta={TXT.seguirTitulo}
						describe="seguir-recuerda"
					/>
				</section>
			)}

			<div className="guia-final">
				<button
					type="button"
					className={seguirAqui ? "guia-btn-sec" : "guia-btn"}
					onClick={onOtraPregunta}
				>
					{TXT.empezarDeNuevo}
				</button>
				{onTerminar ? (
					<button type="button" className="guia-btn-sec" onClick={onTerminar}>
						Terminar y dar mi opinión
					</button>
				) : null}
			</div>
		</>
	);
}

function Sirvio({
	puedeCalificar,
	calificada,
	onCalificar,
}: {
	puedeCalificar: boolean;
	calificada?: boolean;
	onCalificar: (c: Calificacion) => Promise<void>;
}) {
	const [paso, setPaso] = useState<"preguntar" | "que-falto" | "enviando" | "gracias" | "error" | "ya">(
		"preguntar",
	);
	const [comentario, setComentario] = useState("");
	// Varios "¿Le sirvió?" en la misma pantalla (uno por respuesta del hilo):
	// ids propios para que cada etiqueta apunte a lo suyo.
	const id = useId();
	const idPregunta = `${id}-sirvio`;
	const idFalto = `${id}-que-falto`;
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
		if (paso === "gracias" || paso === "error" || paso === "ya") mensajeRef.current?.focus();
		if (paso === "que-falto") document.getElementById(idFalto)?.focus();
	}, [paso, idFalto]);

	// QA-F06a: un "No" tocado se guarda aunque la persona no toque "Enviar".
	// Si sigue a otra pantalla (o cierra la página) con "¿Qué le faltó?"
	// abierto, el "No" se manda sin comentario. Solo una vez.
	const noPendiente = useRef(false);
	const calificarRef = useRef(onCalificar);
	useEffect(() => {
		calificarRef.current = onCalificar;
	});
	useEffect(() => {
		const mandarNo = () => {
			if (!noPendiente.current) return;
			noPendiente.current = false;
			void calificarRef.current({ util: false }).catch(() => {});
		};
		window.addEventListener("pagehide", mandarNo);
		return () => {
			window.removeEventListener("pagehide", mandarNo);
			mandarNo();
		};
	}, []);

	async function enviar(c: Calificacion) {
		noPendiente.current = false;
		fijarAlto();
		setPaso("enviando");
		try {
			await onCalificar(c);
			setPaso("gracias");
		} catch (e) {
			// Ya la había calificado antes (p. ej. antes de recargar): no es un
			// error, su opinión ya está guardada.
			setPaso(e instanceof Error && e.message === YA_CALIFICADO ? "ya" : "error");
		}
	}

	// Ya la calificó (en esta pantalla u otra del mismo tema): no se pregunta otra vez.
	if (calificada !== undefined && paso === "preguntar") {
		return (
			<div className="guia-sirvio">
				<p className="gracias">Ya respondió: {calificada ? "le sirvió" : "no le sirvió"}.</p>
			</div>
		);
	}

	if (!puedeCalificar) return null;

	return (
		<div className="guia-sirvio" ref={cajaRef} style={altoMinimo ? { minHeight: altoMinimo } : undefined}>
			{paso === "preguntar" || paso === "enviando" ? (
				<>
					<p id={idPregunta}>¿Esta respuesta le sirvió?</p>
					<div className="guia-acciones" role="group" aria-labelledby={idPregunta}>
						<button
							type="button"
							className="guia-btn-sec si"
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
								noPendiente.current = true;
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
					<label className="grande" htmlFor={idFalto} style={{ marginTop: 0 }}>
						¿Qué le faltó? (si quiere)
					</label>
					<textarea
						id={idFalto}
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
			{paso === "ya" ? (
				<p className="gracias" role="status" ref={mensajeRef} tabIndex={-1}>
					Ya había respondido sobre esta respuesta. Su opinión quedó guardada.
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
