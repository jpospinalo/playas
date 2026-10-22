"use client";

import { useEffect, useState } from "react";
import { MAX_QUESTION_CHARS } from "@/lib/contracts";
import { PLAYAS, TEMAS, type Tema } from "@/lib/guia/temas";
import {
	ETAPAS,
	TXT,
	lecturaEscribir,
	lecturaEspera,
	lecturaError,
	lecturaInicio,
	lecturaPlaya,
	lecturaTema,
	mensajeError,
	type TipoError,
} from "@/lib/guia/textos";
import { Boya, Flecha, FlechaVolver, IconoDeTema } from "@/components/guia/iconos";
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

export function PantallaInicio({
	tituloRef,
	onTema,
	onEscribir,
}: {
	tituloRef: TituloRef;
	onTema: (t: Tema) => void;
	onEscribir: () => void;
}) {
	return (
		<>
			<Cabeza titulo={TXT.inicioTitulo} tituloRef={tituloRef} lectura={lecturaInicio} />
			<p className="pista">{TXT.inicioPista}</p>
			<ul className="guia-opciones">
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
			<div className="guia-otra">
				<p>{TXT.otraCaso}</p>
				<button type="button" className="guia-btn-sec" onClick={onEscribir}>
					{TXT.escribirBoton}
				</button>
			</div>
			<p className="pie">{TXT.pie}</p>
		</>
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

export function PantallaEscribir({
	tituloRef,
	inicial,
	onCambio,
	onVolver,
	onPreguntar,
}: {
	tituloRef: TituloRef;
	inicial: string;
	/** Guarda lo escrito fuera de la pantalla, para no perderlo al volver. */
	onCambio: (texto: string) => void;
	onVolver: () => void;
	onPreguntar: (texto: string) => void;
}) {
	const [texto, setTexto] = useState(inicial);
	const [error, setError] = useState<string | null>(null);

	return (
		<>
			<Volver onClick={onVolver} />
			<Cabeza titulo={TXT.escribirTitulo} tituloRef={tituloRef} lectura={lecturaEscribir} />
			<p className="pista">{TXT.escribirPista}</p>
			<form
				noValidate
				onSubmit={(e) => {
					e.preventDefault();
					const limpio = texto.trim();
					if (limpio.length < 5) {
						setError(TXT.escribirVacio);
						document.getElementById("texto")?.focus();
						return;
					}
					setError(null);
					onPreguntar(limpio);
				}}
			>
				<label className="grande" htmlFor="texto">
					Su pregunta
				</label>
				<textarea
					id="texto"
					name="texto"
					rows={5}
					value={texto}
					maxLength={MAX_QUESTION_CHARS}
					aria-describedby={error ? "texto-error texto-ejemplo" : "texto-ejemplo"}
					aria-invalid={error ? true : undefined}
					onChange={(e) => {
						setTexto(e.target.value);
						onCambio(e.target.value);
					}}
				/>
				<p className="ejemplo" id="texto-ejemplo">
					Por ejemplo: <i>{TXT.escribirEjemplo}</i>
				</p>
				{error ? (
					<p className="guia-error" role="alert" id="texto-error">
						{error}
					</p>
				) : null}
				<div className="guia-acciones">
					<button className="guia-btn" type="submit">
						Preguntar
					</button>
				</div>
			</form>
		</>
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
				{mensajeError(tipo)}
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
