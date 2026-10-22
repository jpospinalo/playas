"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useChat } from "@/hooks/useChat";
import { useRutaGuia } from "@/hooks/useRutaGuia";
import { NETWORK_ERROR_MESSAGE } from "@/lib/httpTimeout";
import { buscarTema, preguntaConPlaya } from "@/lib/guia/temas";
import type { TipoError } from "@/lib/guia/textos";
import { Entrar } from "@/components/guia/Entrar";
import {
	PantallaError,
	PantallaEscribir,
	PantallaEspera,
	PantallaInicio,
	PantallaPlaya,
	PantallaTema,
} from "@/components/guia/Pantallas";
import { Respuesta, type Calificacion } from "@/components/guia/Respuesta";
import { detenerVoz } from "@/lib/voz";

/**
 * ATLAS para el público (diseño v3): flujo guiado de una pregunta por
 * pantalla. Usa el mismo inicio de sesión, el mismo `useChat` y el mismo
 * streaming SSE del chat (/chat); cada pregunta queda guardada como una
 * conversación propia.
 */
export function GuiaApp() {
	const { user, loading } = useAuth();
	const tituloRef = useRef<HTMLHeadingElement>(null);

	return (
		<div className="guia">
			<Encabezado />
			<main id="main-content" className="guia-main" tabIndex={-1}>
				{loading ? (
					<p role="status" className="pista">
						Cargando…
					</p>
				) : user ? (
					<Flujo key={user.user_id} />
				) : (
					<Entrar tituloRef={tituloRef} />
				)}
			</main>
		</div>
	);
}

function Encabezado() {
	const { user, signOut } = useAuth();
	return (
		<header className="guia-encabezado">
			<div className="guia-barra">
				{/* eslint-disable-next-line @next/next/no-img-element -- logo de 12 KB, sin optimizador */}
				<img src="/brand/atlas-96.png" alt="" width={40} height={40} />
				<div>
					<span className="nombre">ATLAS</span>
					<span className="zona">
						<span className="largo">Preguntas sobre las playas de </span>
						<span className="corto">Playas de </span>
						<span className="lugar">Santa Marta</span>
					</span>
				</div>
				{user ? (
					<button type="button" className="salir" onClick={() => void signOut()}>
						Salir
					</button>
				) : null}
			</div>
		</header>
	);
}

interface PreguntaActual {
	texto: string;
	/** Lo que se envía al RAG (puede llevar la playa al final). */
	envio: string;
	playa: string | null;
}

function tipoDeError(error: string | null): TipoError {
	if (error === "sin-senal") return "sin-senal";
	if (error === NETWORK_ERROR_MESSAGE || (error ?? "").toLowerCase().includes("conexión")) return "red";
	return "otro";
}

function Flujo() {
	const { ruta, ir } = useRutaGuia();
	const tituloRef = useRef<HTMLHeadingElement>(null);
	const chat = useChat();
	const { messages, loading, error, stage, generationFinished, persistingMessageIds } = chat;

	const [pregunta, setPregunta] = useState<PreguntaActual | null>(null);
	// Pregunta que espera a que el chat quede vacío para enviarse (ver efecto
	// de abajo). Va en una ref; `turnoEnvio` solo dispara el efecto.
	const pendienteRef = useRef<string | null>(null);
	const [turnoEnvio, setTurnoEnvio] = useState(0);
	const [sinSenal, setSinSenal] = useState(false);
	const [borrador, setBorrador] = useState("");

	const pantalla = ruta[0] ?? "inicio";
	const respuesta = [...messages].reverse().find((m) => m.role === "assistant" && m.text);

	// Envía la pregunta pendiente una vez que el chat quedó vacío
	// (`resetChat`): así `submit` ve un chat sin mensajes y crea una
	// conversación nueva para esta pregunta.
	const { submit } = chat;
	useEffect(() => {
		const q = pendienteRef.current;
		if (q && messages.length === 0 && !loading) {
			pendienteRef.current = null;
			void submit(q);
		}
	}, [turnoEnvio, messages.length, loading, submit]);

	// Cuando la respuesta terminó de llegar, se pasa a la pantalla de respuesta
	// (reemplazando "espera", para que "atrás" no vuelva a la espera).
	useEffect(() => {
		if (pantalla === "espera" && respuesta && (generationFinished || !loading) && !error) {
			ir("respuesta", { reemplazar: true });
		}
	}, [pantalla, respuesta, generationFinished, loading, error, ir]);

	// Al cambiar de pantalla: arriba del todo, foco en el título (los
	// lectores de pantalla lo anuncian) y título de la pestaña.
	const clave = ruta.join("/");
	const primera = useRef(true);
	useEffect(() => {
		detenerVoz();
		window.scrollTo(0, 0);
		if (primera.current) {
			primera.current = false;
		} else {
			tituloRef.current?.focus();
		}
		const t = tituloRef.current?.textContent;
		document.title = t ? `ATLAS: ${t}` : "ATLAS";
	}, [clave, sinSenal, error]);

	function preguntar(texto: string, envio: string, playa: string | null) {
		setPregunta({ texto, envio, playa });
		setBorrador("");
		chat.resetChat();
		if (typeof navigator !== "undefined" && navigator.onLine === false) {
			setSinSenal(true);
			pendienteRef.current = null;
		} else {
			setSinSenal(false);
			pendienteRef.current = envio;
			setTurnoEnvio((n) => n + 1);
		}
		ir("espera");
	}

	function reintentar() {
		if (!pregunta) {
			ir("inicio");
			return;
		}
		chat.resetChat();
		if (navigator.onLine === false) {
			setSinSenal(true);
			return;
		}
		setSinSenal(false);
		pendienteRef.current = pregunta.envio;
		setTurnoEnvio((n) => n + 1);
	}

	function cancelarYVolver() {
		chat.resetChat();
		pendienteRef.current = null;
		setSinSenal(false);
		window.history.back();
	}

	function otraPregunta() {
		chat.resetChat();
		setPregunta(null);
		setSinSenal(false);
		ir("inicio");
	}

	async function calificar(c: Calificacion) {
		if (!respuesta) return;
		const nota = c.util ? 5 : 1;
		await chat.rateMessage(respuesta.id, { pertinence: nota, accuracy: nota }, c.comentario);
	}

	const tema = buscarTema(ruta[1]);

	if (pantalla === "tema" && tema) {
		return (
			<PantallaTema
				tema={tema}
				tituloRef={tituloRef}
				onVolver={() => ir("inicio")}
				onEscribir={() => ir("escribir")}
				onOpcion={(i) => {
					const o = tema.opciones[i];
					if (o.pidePlaya) ir(`playa/${tema.id}/${i}`);
					else preguntar(o.texto, o.pregunta, null);
				}}
			/>
		);
	}

	if (pantalla === "playa" && tema) {
		const o = tema.opciones[Number(ruta[2]) || 0] ?? tema.opciones[0];
		return (
			<PantallaPlaya
				tema={tema}
				tituloRef={tituloRef}
				onVolver={() => ir(`tema/${tema.id}`)}
				onPlaya={(playa) => preguntar(o.texto, preguntaConPlaya(o.pregunta, playa), playa)}
			/>
		);
	}

	if (pantalla === "escribir") {
		return (
			<PantallaEscribir
				tituloRef={tituloRef}
				inicial={borrador}
				onVolver={() => window.history.back()}
				onPreguntar={(texto) => {
					setBorrador(texto);
					preguntar(texto, texto, null);
				}}
			/>
		);
	}

	if (pantalla === "espera" && pregunta) {
		if (sinSenal || error) {
			return (
				<PantallaError
					tituloRef={tituloRef}
					tipo={sinSenal ? "sin-senal" : tipoDeError(error)}
					detalle={error}
					onReintentar={reintentar}
					onVolver={cancelarYVolver}
				/>
			);
		}
		return <PantallaEspera tituloRef={tituloRef} etapa={stage} onVolver={cancelarYVolver} />;
	}

	if (pantalla === "respuesta" && pregunta && respuesta) {
		return (
			<Respuesta
				pregunta={pregunta.texto}
				playa={pregunta.playa}
				texto={respuesta.text}
				fuentes={respuesta.sources ?? []}
				puedeCalificar={
					!loading &&
					!!chat.conversationId &&
					respuesta.persistenceStatus !== "failed" &&
					!persistingMessageIds.has(respuesta.id)
				}
				onCalificar={calificar}
				onOtraPregunta={otraPregunta}
				onEscribirDeNuevo={() => {
					setBorrador(pregunta.texto);
					ir("escribir");
				}}
				tituloRef={tituloRef}
			/>
		);
	}

	// Inicio (y cualquier dirección que ya no tiene datos, p. ej. al recargar
	// en la pantalla de respuesta).
	return (
		<PantallaInicio
			tituloRef={tituloRef}
			onTema={(t) => ir(`tema/${t.id}`)}
			onEscribir={() => ir("escribir")}
		/>
	);
}
