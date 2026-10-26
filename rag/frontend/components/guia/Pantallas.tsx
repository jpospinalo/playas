"use client";

import { useEffect, useRef, useState } from "react";
import { MAX_QUESTION_CHARS } from "@/lib/contracts";
import { PLAYAS, TEMAS, type Tema } from "@/lib/guia/temas";
import {
	EJEMPLOS,
	ETAPAS,
	TXT,
	lecturaEspera,
	lecturaError,
	lecturaInicio,
	lecturaPlaya,
	lecturaTema,
	mensajeError,
	type TipoError,
} from "@/lib/guia/textos";
import { Aviso, Boya, Flecha, FlechaVolver, IconoDeTema } from "@/components/guia/iconos";
import { Escuchar } from "@/components/guia/Escuchar";

type TituloRef = React.RefObject<HTMLHeadingElement | null>;

export function Volver({ onClick, children = "Volver" }: { onClick: () => void; children?: string }) {
	return (
		<button type="button" className="guia-volver" onClick={onClick}>
			<FlechaVolver />
			{children}
		</button>
	);
}

/** "Volver" repetido al final de listas largas, cerca del pulgar. */
function VolverAbajo({ onClick }: { onClick: () => void }) {
	return (
		<div className="guia-volver-abajo">
			<Volver onClick={onClick} />
		</div>
	);
}

function Cabeza({
	titulo,
	tituloRef,
	lectura,
	children,
}: {
	titulo: string;
	tituloRef: TituloRef;
	lectura: () => string;
	children?: React.ReactNode;
}) {
	return (
		<div className="guia-cabeza">
			<div>
				{children}
				<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
					{titulo}
				</h1>
			</div>
			<Escuchar texto={lectura} />
		</div>
	);
}

/** Muestra en itálica los nombres de playa dentro de un texto (p. ej. un ejemplo). */
function conLugares(texto: string): React.ReactNode {
	const playa = PLAYAS.find((p) => texto.includes(p));
	if (!playa) return texto;
	const [antes, despues] = texto.split(playa);
	return (
		<>
			{antes}
			<span className="lugar">{playa}</span>
			{despues}
		</>
	);
}

export function PantallaInicio({
	tituloRef,
	cajaRef,
	borrador,
	onCambio,
	onPreguntar,
	onTema,
}: {
	tituloRef: TituloRef;
	cajaRef: React.RefObject<HTMLTextAreaElement | null>;
	/** Lo escrito en la caja: vive fuera de la pantalla para no perderlo al ir a un tema y volver. */
	borrador: string;
	onCambio: (texto: string) => void;
	onPreguntar: (texto: string) => void;
	onTema: (t: Tema) => void;
}) {
	return (
		<div className="guia-inicio">
			<section className="guia-hero" aria-labelledby="titulo">
				<div className="guia-hero-in">
					<picture>
						<source srcSet="/brand/atlas-logo-inicio.webp" type="image/webp" />
						{/* Logo de 22 KB (webp) o 74 KB (png), sin optimizador de imágenes. */}
						<img className="logo" src="/brand/atlas-logo-inicio.png" alt="" width={132} height={121} />
					</picture>
					<h1 id="titulo" ref={tituloRef} tabIndex={-1}>
						{TXT.inicioTitulo}
					</h1>
					<div className="guia-hero-escuchar">
						<Escuchar texto={lecturaInicio} />
					</div>
					<CajaPregunta
						id="texto"
						cajaRef={cajaRef}
						valor={borrador}
						onCambio={onCambio}
						onPreguntar={onPreguntar}
						pista={TXT.cajaPista}
						describe="inicio-nota"
					/>
					<p className="guia-nota" id="inicio-nota">
						{/* En celular chico solo queda "Pruebe con:" para que los temas asomen. */}
						<span className="largo">{TXT.inicioNota} </span>
						{TXT.inicioEjemplos}
					</p>
					<ul className="guia-ejemplos" aria-labelledby="inicio-nota">
						{EJEMPLOS.map((e) => (
							<li key={e}>
								<button
									type="button"
									onClick={() => {
										onCambio(e);
										// Llena la caja y deja el cursor al final; no envía.
										requestAnimationFrame(() => {
											const caja = cajaRef.current;
											if (!caja) return;
											caja.focus();
											caja.setSelectionRange(e.length, e.length);
										});
									}}
								>
									{conLugares(e)}
								</button>
							</li>
						))}
					</ul>
				</div>
			</section>
			<section className="guia-guiar" aria-labelledby="guiar-titulo">
				<h2 id="guiar-titulo">{TXT.guiarTitulo}</h2>
				<p className="pista">{TXT.guiarPista}</p>
				<ul className="guia-opciones guia-temas">
					{TEMAS.map((t) => (
						<li key={t.id}>
							<button type="button" className="guia-opcion" onClick={() => onTema(t)}>
								<span className="ico">
									<IconoDeTema icono={t.icono} />
								</span>
								<span className="txt">
									<b>{t.titulo}</b>
									<small>{t.detalle}</small>
								</span>
								<Flecha />
							</button>
						</li>
					))}
				</ul>
				<p className="pie">{TXT.pie}</p>
			</section>
		</div>
	);
}

export function PantallaTema({
	tema,
	tituloRef,
	onVolver,
	onOpcion,
	onEscribir,
}: {
	tema: Tema;
	tituloRef: TituloRef;
	onVolver: () => void;
	onOpcion: (indice: number) => void;
	onEscribir: () => void;
}) {
	return (
		<>
			<Volver onClick={onVolver} />
			<Cabeza titulo={tema.pantalla} tituloRef={tituloRef} lectura={() => lecturaTema(tema)}>
				<p className="miga">{tema.titulo}</p>
			</Cabeza>
			<ul className="guia-opciones">
				{tema.opciones.map((o, i) => (
					<li key={o.texto}>
						<button type="button" className="guia-opcion" onClick={() => onOpcion(i)}>
							<span className="txt">
								<b>{o.texto}</b>
							</span>
							<Flecha />
						</button>
					</li>
				))}
				<li>
					<button type="button" className="guia-opcion" onClick={onEscribir}>
						<span className="txt">
							<b>{TXT.otraCosa}</b>
						</span>
						<Flecha />
					</button>
				</li>
			</ul>
			<VolverAbajo onClick={onVolver} />
		</>
	);
}

export function PantallaPlaya({
	tema,
	tituloRef,
	onVolver,
	onPlaya,
}: {
	tema: Tema;
	tituloRef: TituloRef;
	onVolver: () => void;
	onPlaya: (playa: string | null) => void;
}) {
	return (
		<>
			<Volver onClick={onVolver} />
			<Cabeza titulo={TXT.playaTitulo} tituloRef={tituloRef} lectura={lecturaPlaya}>
				<p className="miga">{tema.titulo}</p>
			</Cabeza>
			<p className="pista">{TXT.playaPista}</p>
			<ul className="guia-opciones guia-playas">
				{PLAYAS.map((p) => (
					<li key={p}>
						<button type="button" className="guia-opcion" onClick={() => onPlaya(p)}>
							<span className="txt">
								<b>{p}</b>
							</span>
							<Flecha />
						</button>
					</li>
				))}
				<li>
					<button type="button" className="guia-opcion" onClick={() => onPlaya(null)}>
						<span className="txt">
							<b className="normal">{TXT.otraPlaya}</b>
						</span>
						<Flecha />
					</button>
				</li>
			</ul>
			<VolverAbajo onClick={onVolver} />
		</>
	);
}

/** En celular (pantalla táctil) Enter hace otro renglón; en el computador envía. */
export function esTactil(): boolean {
	return typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;
}

/**
 * Caja de pregunta (inicio y seguimiento al final de la respuesta). Mínimo
 * 5 letras; los errores dicen qué falta. Lo escrito vive afuera (`valor` /
 * `onCambio`) para que sobreviva al cambiar de pantalla.
 */
export function CajaPregunta({
	id,
	cajaRef,
	valor,
	onCambio,
	onPreguntar,
	pista,
	etiqueta = "Su pregunta",
	describe,
	clase,
}: {
	id: string;
	cajaRef?: React.RefObject<HTMLTextAreaElement | null>;
	valor: string;
	onCambio: (texto: string) => void;
	onPreguntar: (texto: string) => void;
	pista?: string;
	/** Nombre de la caja para el lector de pantalla (no se ve). */
	etiqueta?: string;
	/** id de un texto que la describe (p. ej. la nota con ejemplos). */
	describe?: string;
	clase?: string;
}) {
	const [error, setError] = useState<string | null>(null);
	const formRef = useRef<HTMLFormElement>(null);
	const idError = `${id}-error`;
	const describeIds = [error ? idError : null, describe ?? null].filter(Boolean).join(" ") || undefined;

	return (
		<form
			ref={formRef}
			className={`guia-caja${clase ? ` ${clase}` : ""}`}
			noValidate
			onSubmit={(e) => {
				e.preventDefault();
				const limpio = valor.trim();
				if (limpio.length < 5) {
					setError(limpio.length === 0 ? TXT.escribirVacio : TXT.escribirCorta);
					document.getElementById(id)?.focus();
					return;
				}
				setError(null);
				onPreguntar(limpio);
			}}
		>
			<label className="sr" htmlFor={id}>
				{etiqueta}
			</label>
			<div className="guia-buscador">
				<textarea
					id={id}
					ref={cajaRef}
					name="texto"
					rows={2}
					value={valor}
					placeholder={pista}
					maxLength={MAX_QUESTION_CHARS}
					aria-describedby={describeIds}
					aria-invalid={error ? true : undefined}
					onChange={(e) => onCambio(e.target.value)}
					onKeyDown={(e) => {
						if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing || esTactil()) return;
						e.preventDefault();
						formRef.current?.requestSubmit();
					}}
				/>
				<button className="guia-btn" type="submit">
					Preguntar
				</button>
			</div>
			{error ? (
				<p className="guia-error" role="alert" id={idError}>
					<Aviso />
					<span>{error}</span>
				</p>
			) : null}
		</form>
	);
}

export function PantallaEspera({
	tituloRef,
	etapa,
	onVolver,
}: {
	tituloRef: TituloRef;
	etapa: string | null;
	onVolver: () => void;
}) {
	return (
		<>
			<Volver onClick={onVolver}>Cancelar y volver</Volver>
			<Cabeza titulo={TXT.esperaTitulo} tituloRef={tituloRef} lectura={lecturaEspera} />
			<div className="guia-espera">
				<Boya />
				<p>
					{TXT.esperaTexto}
					{/* Solo la etapa es región viva: el lector anuncia "Buscando…"
					    sin repetir la frase fija en cada cambio. */}
					<span className="etapa" role="status">
						{etapa && ETAPAS[etapa] ? ETAPAS[etapa] : ""}
					</span>
				</p>
			</div>
		</>
	);
}

export function PantallaError({
	tituloRef,
	tipo,
	detalle,
	intentos,
	onReintentar,
	onVolver,
}: {
	tituloRef: TituloRef;
	tipo: TipoError;
	/** Detalle técnico: solo va a la consola, nunca a la pantalla del público. */
	detalle: string | null;
	/** Reintentos sin señal (0 = ninguno todavía). */
	intentos: number;
	onReintentar: () => void;
	onVolver: () => void;
}) {
	useEffect(() => {
		// Para el equipo (consola del navegador); el público no lo necesita.
		if (detalle) console.warn("[ATLAS] error al traer la respuesta:", detalle);
	}, [detalle]);
	return (
		<>
			<Volver onClick={onVolver} />
			<Cabeza titulo={TXT.errorTitulo} tituloRef={tituloRef} lectura={() => lecturaError(tipo)} />
			<p className="guia-error" role="alert">
				<Aviso />
				<span>{mensajeError(tipo)}</span>
			</p>
			{intentos > 0 ? (
				<p className="aviso-intento" role="status">
					Todavía no hay señal (intento {intentos + 1}).
				</p>
			) : null}
			<div className="guia-acciones">
				<button type="button" className="guia-btn" onClick={onReintentar}>
					Intentar otra vez
				</button>
			</div>
		</>
	);
}
