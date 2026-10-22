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
	PantallaSeguir,
	PantallaTema,
} from "@/components/guia/Pantallas";
import { Respuesta, type Calificacion } from "@/components/guia/Respuesta";
import { detenerVoz } from "@/lib/voz";
import {
	exponerEnConsola,
	iniciarMedicion,
	marcarEtapa,
	marcarPrimerTexto,
	terminarMedicion,
	transcurrido,
} from "@/lib/medicion";
import { borrarPendiente, guardarPendiente, leerPendiente } from "@/lib/guia/pendiente";

/** Borra lo que el flujo guarda en la pestaña (última respuesta y pregunta pendiente). */
function borrarDatosDeLaPestana(): void {
	guardar(null);
	borrarPendiente();
}
import type { SourceGroup } from "@/lib/types";

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
	// Un toque sin querer en "Salir" no debe sacar a nadie: se pide confirmar.
	const [confirmar, setConfirmar] = useState(false);
	const noRef = useRef<HTMLButtonElement>(null);
	const salirRef = useRef<HTMLButtonElement>(null);
	const abierta = useRef(false);
	useEffect(() => {
		if (confirmar) noRef.current?.focus();
		// Al cancelar, el foco vuelve a "Salir" (no se pierde en la página).
		else if (abierta.current) salirRef.current?.focus();
		abierta.current = confirmar;
	}, [confirmar]);
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
				{user && !confirmar ? (
					<button type="button" className="salir" ref={salirRef} onClick={() => setConfirmar(true)}>
						Salir
					</button>
				) : null}
			</div>
			{user && confirmar ? (
				<div
					className="guia-confirmar"
					role="group"
					aria-labelledby="confirmar-salir"
					// Escape = "No, seguir aquí".
					onKeyDown={(e) => {
						if (e.key === "Escape") setConfirmar(false);
					}}
				>
					<p id="confirmar-salir">¿Seguro que quiere salir de ATLAS?</p>
					<div className="guia-acciones">
						<button type="button" className="guia-btn-sec" ref={noRef} onClick={() => setConfirmar(false)}>
							No, seguir aquí
						</button>
						<button
							type="button"
							className="guia-btn-sec"
							onClick={() => {
								setConfirmar(false);
								// Celular compartido (E2-11): al salir no queda a la vista
								// la pregunta ni la respuesta de la persona anterior.
								borrarDatosDeLaPestana();
								void signOut();
							}}
						>
							Sí, salir
						</button>
					</div>
				</div>
			) : null}
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

const CLAVE_GUARDADA = "atlas:ultima-respuesta";

interface RespuestaGuardada {
	pregunta: PreguntaActual;
	texto: string;
	fuentes: SourceGroup[];
}

/** Última respuesta de esta pestaña, para no perderla si se recarga la página. */
function leerGuardada(): RespuestaGuardada | null {
	try {
		const crudo = window.sessionStorage.getItem(CLAVE_GUARDADA);
		return crudo ? (JSON.parse(crudo) as RespuestaGuardada) : null;
	} catch {
		return null;
	}
}

function guardar(r: RespuestaGuardada | null): void {
	try {
		if (r) window.sessionStorage.setItem(CLAVE_GUARDADA, JSON.stringify(r));
		else window.sessionStorage.removeItem(CLAVE_GUARDADA);
	} catch {
		// Sin almacenamiento (modo privado, etc.): solo se pierde esta comodidad.
	}
}

function Flujo() {
	const { ruta, ir, volver } = useRutaGuia();
	const tituloRef = useRef<HTMLHeadingElement>(null);
	const chat = useChat();
	const { messages, loading, error, stage, isStreaming, generationFinished, persistingMessageIds } = chat;

	const [pregunta, setPregunta] = useState<PreguntaActual | null>(null);
	// Pregunta que espera a que el chat quede vacío para enviarse (ver efecto
	// de abajo). Va en una ref; `turnoEnvio` solo dispara el efecto.
	const pendienteRef = useRef<string | null>(null);
	const [turnoEnvio, setTurnoEnvio] = useState(0);
	const [sinSenal, setSinSenal] = useState(false);
	const [borrador, setBorrador] = useState("");
	// Veces que se tocó "Intentar otra vez" sin señal (para que se note que intentó).
	const [intentos, setIntentos] = useState(0);
	const [guardada, setGuardada] = useState<RespuestaGuardada | null>(() =>
		typeof window === "undefined" ? null : leerGuardada(),
	);
	// Pregunta que quedó sin respuesta (se cerró la sesión o se recargó la
	// página mientras se esperaba): al volver se ofrece seguir con ella.
	const [retomar, setRetomar] = useState<PreguntaActual | null>(() =>
		typeof window === "undefined" ? null : leerPendiente(),
	);
	const [segundos, setSegundos] = useState(0);

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
			terminarMedicion("ok");
			borrarPendiente();
			ir("respuesta", { reemplazar: true });
		}
	}, [pantalla, respuesta, generationFinished, loading, error, ir]);

	// Medición del tiempo hasta la respuesta útil (UX-02): etapas del backend,
	// primer texto y error. Solo tiempos; nunca el texto de la pregunta.
	useEffect(() => exponerEnConsola(), []);
	useEffect(() => {
		if (stage) marcarEtapa(stage);
	}, [stage]);
	// El backend manda todo el texto de una vez (ya validado): "primer texto"
	// se marca cuando aparece texto de la respuesta, aunque React agrupe los trozos.
	const hayTexto = !!respuesta?.text;
	useEffect(() => {
		if (isStreaming || hayTexto) marcarPrimerTexto();
	}, [isStreaming, hayTexto]);
	useEffect(() => {
		if (error) terminarMedicion("error");
	}, [error]);

	// Contador de segundos en la espera (se actualiza 1 vez por segundo).
	const esperando = pantalla === "espera" && !!pregunta && !error && !sinSenal;
	useEffect(() => {
		if (!esperando) return;
		const id = window.setInterval(() => {
			setSegundos(Math.floor((transcurrido() ?? 0) / 1000));
		}, 1000);
		return () => window.clearInterval(id);
	}, [esperando]);

	// La respuesta completa se guarda en la pestaña (sessionStorage): si la
	// persona recarga sin querer (jalar hacia abajo en el celular), la vuelve a ver.
	const respuestaLista = respuesta && !loading && !error ? respuesta : null;
	useEffect(() => {
		if (pantalla !== "respuesta" || !respuestaLista || !pregunta) return;
		guardar({ pregunta, texto: respuestaLista.text, fuentes: respuestaLista.sources ?? [] });
	}, [pantalla, respuestaLista, pregunta]);

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
		// El nombre de la pestaña sale de la pantalla que de verdad se ve (una
		// dirección sin datos muestra el inicio y debe decir eso).
		const enRespuesta = !!tituloRef.current?.closest(".guia-veredicto");
		const t = enRespuesta ? "Respuesta a su pregunta" : tituloRef.current?.textContent;
		document.title = t ? `ATLAS: ${t}` : "ATLAS";
	}, [clave, sinSenal, error]);

	function preguntar(texto: string, envio: string, playa: string | null) {
		setPregunta({ texto, envio, playa });
		setIntentos(0);
		setSegundos(0);
		setRetomar(null);
		guardarPendiente({ texto, envio, playa });
		chat.resetChat();
		if (typeof navigator !== "undefined" && navigator.onLine === false) {
			setSinSenal(true);
			pendienteRef.current = null;
		} else {
			setSinSenal(false);
			iniciarMedicion();
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
			setIntentos((n) => n + 1);
			return;
		}
		setSinSenal(false);
		setIntentos(0);
		setSegundos(0);
		iniciarMedicion();
		pendienteRef.current = pregunta.envio;
		setTurnoEnvio((n) => n + 1);
	}

	function cancelarYVolver() {
		terminarMedicion("cancelada");
		borrarPendiente();
		chat.resetChat();
		pendienteRef.current = null;
		setSinSenal(false);
		window.history.back();
	}

	function otraPregunta() {
		// La respuesta que se deja queda guardada: si la persona toca "atrás"
		// desde el inicio, la vuelve a ver (QA-15) en vez de un inicio repetido.
		if (pregunta && respuestaLista) {
			setGuardada({ pregunta, texto: respuestaLista.text, fuentes: respuestaLista.sources ?? [] });
		}
		chat.resetChat();
		borrarPendiente();
		setPregunta(null);
		setBorrador("");
		setSinSenal(false);
		ir("inicio");
	}

	async function calificar(c: Calificacion) {
		if (!respuesta) return;
		const nota = c.util ? 5 : 1;
		await chat.rateMessage(respuesta.id, { pertinence: nota, accuracy: nota }, c.comentario);
	}

	const tema = buscarTema(ruta[1]);

	// Al volver a entrar (o recargar) con una pregunta sin responder.
	if (retomar && !pregunta) {
		return (
			<PantallaSeguir
				tituloRef={tituloRef}
				pregunta={retomar.texto}
				playa={retomar.playa}
				onSeguir={() => preguntar(retomar.texto, retomar.envio, retomar.playa)}
				onEmpezar={() => {
					borrarPendiente();
					setRetomar(null);
					ir("inicio", { reemplazar: true });
				}}
			/>
		);
	}

	if (pantalla === "tema" && tema) {
		return (
			<PantallaTema
				tema={tema}
				tituloRef={tituloRef}
				onVolver={() => volver("inicio")}
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
				onVolver={() => volver(`tema/${tema.id}`)}
				onPlaya={(playa) => preguntar(o.texto, preguntaConPlaya(o.pregunta, playa), playa)}
			/>
		);
	}

	if (pantalla === "escribir") {
		return (
			<PantallaEscribir
				tituloRef={tituloRef}
				inicial={borrador}
				onCambio={setBorrador}
				onVolver={() => volver("inicio")}
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
					intentos={sinSenal ? intentos : 0}
					onReintentar={reintentar}
					onVolver={cancelarYVolver}
				/>
			);
		}
		return (
			<PantallaEspera tituloRef={tituloRef} etapa={stage} segundos={segundos} onVolver={cancelarYVolver} />
		);
	}

	// Respuesta guardada (tras recargar la página): se muestra igual, pero sin
	// "¿Le sirvió?", porque la conversación ya no está abierta en el chat.
	if (pantalla === "respuesta" && !(pregunta && respuesta) && guardada) {
		return (
			<Respuesta
				pregunta={guardada.pregunta.texto}
				playa={guardada.pregunta.playa}
				texto={guardada.texto}
				fuentes={guardada.fuentes}
				puedeCalificar={false}
				onCalificar={calificar}
				onVolver={() => volver("inicio")}
				onOtraPregunta={otraPregunta}
				onEscribirDeNuevo={() => {
					setBorrador(guardada.pregunta.texto);
					ir("escribir");
				}}
				tituloRef={tituloRef}
			/>
		);
	}

	if (pantalla === "respuesta" && pregunta && respuesta) {
		return (
			<Respuesta
				pregunta={pregunta.texto}
				playa={pregunta.playa}
				texto={respuesta.text}
				fuentes={respuesta.sources ?? []}
				onVolver={() => volver("inicio")}
				puedeCalificar={
					!loading &&
					!!chat.conversationId &&
					respuesta.persistenceStatus !== "failed" &&
					!persistingMessageIds.has(respuesta.id)
				}
				guardado={
					persistingMessageIds.has(respuesta.id)
						? "guardando"
						: respuesta.persistenceStatus === "failed"
							? "fallo"
							: "ok"
				}
				onGuardarOtraVez={() => void chat.retryPersistMessage(respuesta.id)}
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
