"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { useChat } from "@/hooks/useChat";
import { useRutaGuia } from "@/hooks/useRutaGuia";
import { NETWORK_ERROR_MESSAGE } from "@/lib/httpTimeout";
import { buscarTema, preguntaConPlaya } from "@/lib/guia/temas";
import type { TipoError } from "@/lib/guia/textos";
import { Entrar } from "@/components/guia/Entrar";
import {
	PantallaError,
	PantallaEspera,
	PantallaInicio,
	PantallaPlaya,
	PantallaTema,
	esTactil,
} from "@/components/guia/Pantallas";
import { Respuesta, type Calificacion } from "@/components/guia/Respuesta";
import { PantallaOpinion } from "@/components/guia/Opinion";
import { ConPrivacidad } from "@/components/guia/Privacidad";
import { VentanaParticipante } from "@/components/guia/Ventana";
import { pedirEncuesta } from "@/lib/admin/calendario";
import { detenerVoz } from "@/lib/voz";
import { forgetEmail } from "@/lib/auth";
import type { Message, SourceGroup } from "@/lib/types";

/**
 * ATLAS para el público (diseño v3): flujo guiado de una pregunta por
 * pantalla. Usa el mismo inicio de sesión, el mismo `useChat` y el mismo
 * streaming SSE del chat (/chat); cada pregunta queda guardada como una
 * conversación propia.
 */
export function GuiaApp() {
	const { user, loading } = useAuth();
	const salir = useSalir();
	const tituloRef = useRef<HTMLHeadingElement>(null);
	const router = useRouter();
	// Semilleristas y comité solo evalúan: al entrar van directo a Evaluación (PQ-62).
	const evalua = user?.role === "evaluador" || user?.role === "comite";
	useEffect(() => {
		if (evalua) router.replace("/admin/evaluacion");
	}, [evalua, router]);

	return (
		<div className="guia">
			<Encabezado />
			<main id="main-content" className="guia-main" tabIndex={-1}>
				{loading ? (
					<p role="status" className="pista">
						Cargando…
					</p>
				) : user && evalua ? (
					<p role="status" className="pista">
						Abriendo Evaluación…
					</p>
				) : user ? (
					// Primer ingreso: aviso de privacidad y autorización (Ley 1581).
					<ConPrivacidad key={user.user_id} tituloRef={tituloRef} onSalir={() => salir()}>
						<Flujo />
					</ConPrivacidad>
				) : (
					<Entrar tituloRef={tituloRef} />
				)}
			</main>
		</div>
	);
}

/**
 * Cerrar sesión desde el flujo guiado. Celular compartido (QA E2-11): además
 * del token se borra lo que el flujo guarda en la pestaña (última respuesta y
 * borrador), para que la siguiente persona no vea la pregunta ni la respuesta
 * anterior. "Terminar y dejar el celular para otra persona" también olvida el
 * correo recordado en la pantalla de ingreso.
 */
function useSalir() {
	const { signOut } = useAuth();
	return (opciones?: { olvidarCorreo?: boolean }) => {
		detenerVoz();
		guardar(null);
		guardarBorrador("");
		if (opciones?.olvidarCorreo) forgetEmail();
		void signOut();
	};
}

function Encabezado() {
	const { user } = useAuth();
	const salir = useSalir();
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
								salir();
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
const CLAVE_BORRADOR = "atlas:borrador";

/** Lo escrito en la caja del inicio, para no perderlo si la pestaña se recarga. */
function leerBorrador(): string {
	try {
		return window.sessionStorage.getItem(CLAVE_BORRADOR) ?? "";
	} catch {
		return "";
	}
}

function guardarBorrador(texto: string): void {
	try {
		if (texto) window.sessionStorage.setItem(CLAVE_BORRADOR, texto);
		else window.sessionStorage.removeItem(CLAVE_BORRADOR);
	} catch {
		// Sin almacenamiento: solo se pierde esta comodidad.
	}
}

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

/** Una pregunta con su respuesta ya completa, en el orden de la conversación. */
interface Turno {
	pregunta: PreguntaActual;
	mensaje: Message;
}

/** Desde esta cantidad de respuestas seguidas se sugiere empezar de nuevo (3 seguimientos). */
const TOPE_SEGUIMIENTO = 4;

function Flujo() {
	const { ruta, ir, volver } = useRutaGuia();
	const tituloRef = useRef<HTMLHeadingElement>(null);
	// Caja de pregunta del inicio, y si al llegar al inicio el cursor va ahí
	// ("Otra cosa: escribir mi pregunta") en vez de al título.
	const cajaRef = useRef<HTMLTextAreaElement>(null);
	const enfocarCaja = useRef(false);
	const chat = useChat();
	const salir = useSalir();
	// J5-5: si ya llenó la encuesta de percepción, no se le vuelve a ofrecer.
	const [encuestaHecha, setEncuestaHecha] = useState(true);
	useEffect(() => {
		let vigente = true;
		pedirEncuesta()
			.then((r) => {
				if (vigente) setEncuestaHecha(r.respondida);
			})
			.catch(() => {
				if (vigente) setEncuestaHecha(false);
			});
		return () => {
			vigente = false;
		};
	}, []);
	const { messages, loading, error, stage, generationFinished, persistingMessageIds } = chat;

	const [pregunta, setPregunta] = useState<PreguntaActual | null>(null);
	// Cómo se muestra cada pregunta enviada (lo que se envía puede llevar la
	// playa al final). Clave: el texto enviado.
	const [mostradas, setMostradas] = useState<Record<string, PreguntaActual>>({});
	// Pregunta que espera para enviarse (ver efecto de abajo): una nueva
	// espera a que el chat quede vacío; un seguimiento, a que termine lo que
	// estuviera en curso. Va en una ref; `turnoEnvio` solo dispara el efecto.
	const pendienteRef = useRef<{ envio: string; nueva: boolean } | null>(null);
	const [turnoEnvio, setTurnoEnvio] = useState(0);
	const [sinSenal, setSinSenal] = useState(false);
	const [borrador, setBorrador] = useState(() => (typeof window === "undefined" ? "" : leerBorrador()));
	useEffect(() => guardarBorrador(borrador), [borrador]);
	const [seguimiento, setSeguimiento] = useState("");
	// Veces que se tocó "Intentar otra vez" sin señal (para que se note que intentó).
	const [intentos, setIntentos] = useState(0);
	const [guardada, setGuardada] = useState<RespuestaGuardada | null>(() =>
		typeof window === "undefined" ? null : leerGuardada(),
	);

	const pantalla = ruta[0] ?? "inicio";

	// Respuestas completas de esta conversación, cada una con la pregunta
	// que la antecede.
	const turnos = useMemo(() => {
		const lista: Turno[] = [];
		let ultima: string | null = null;
		for (const m of messages) {
			if (m.role === "user") ultima = m.text;
			else if (m.role === "assistant" && m.text && ultima !== null) {
				lista.push({
					pregunta: mostradas[ultima] ?? { texto: ultima, envio: ultima, playa: null },
					mensaje: m,
				});
			}
		}
		return lista;
	}, [messages, mostradas]);
	// Lo escrito en la caja de seguimiento se borra solo cuando llega la
	// respuesta a esa misma pregunta: si falla o se cancela, sigue escrito
	// al volver. Se ajusta al pintar (sin efecto), como recomienda React.
	const [turnosVistos, setTurnosVistos] = useState(turnos.length);
	if (turnos.length !== turnosVistos) {
		setTurnosVistos(turnos.length);
		const llegada = turnos[turnos.length - 1];
		if (turnos.length > turnosVistos && llegada && llegada.pregunta.envio === seguimiento.trim()) {
			setSeguimiento("");
		}
	}
	// La respuesta a la última pregunta enviada (si ya llegó).
	const ultimo = messages[messages.length - 1];
	const nueva = ultimo?.role === "assistant" && ultimo.text ? ultimo : null;

	// Cuando la respuesta terminó de llegar, se pasa a la pantalla de respuesta
	// (reemplazando "espera", para que "atrás" no vuelva a la espera). Cada
	// respuesta tiene su número (`#respuesta/2`): "atrás" vuelve a la anterior.
	// Va antes del efecto de envío: con una pregunta pendiente no se salta.
	useEffect(() => {
		if (pendienteRef.current) return;
		if (pantalla === "espera" && nueva && (generationFinished || !loading) && !error) {
			ir(`respuesta/${turnos.length}`, { reemplazar: true });
		}
	}, [pantalla, nueva, turnos.length, generationFinished, loading, error, ir]);

	const { submit } = chat;
	useEffect(() => {
		const p = pendienteRef.current;
		if (!p || loading) return;
		if (p.nueva && messages.length > 0) return;
		pendienteRef.current = null;
		void submit(p.envio);
	}, [turnoEnvio, messages.length, loading, submit]);

	// Respuesta que se ve: la del número en la dirección (sin número, la última).
	const numero = Number(ruta[1]) || turnos.length;
	const vista = pantalla === "respuesta" ? (turnos[numero - 1] ?? null) : null;

	// La respuesta completa se guarda en la pestaña (sessionStorage): si la
	// persona recarga sin querer (jalar hacia abajo en el celular), la vuelve a ver.
	useEffect(() => {
		if (!vista || loading || error) return;
		guardar({ pregunta: vista.pregunta, texto: vista.mensaje.text, fuentes: vista.mensaje.sources ?? [] });
	}, [vista, loading, error]);

	// Al cambiar de pantalla: arriba del todo, foco en el título (los
	// lectores de pantalla lo anuncian) y título de la pestaña.
	const clave = ruta.join("/");
	// Estado de la pantalla ya atendido (null = recién abierta). En
	// desarrollo React corre el efecto dos veces: la segunda no mueve el foco.
	const atendida = useRef<string | null>(null);
	useEffect(() => {
		const estado = `${clave}|${sinSenal}|${error}`;
		if (atendida.current === estado) return;
		const primera = atendida.current === null;
		atendida.current = estado;
		detenerVoz();
		window.scrollTo(0, 0);
		const caja = cajaRef.current;
		if (primera) {
			// Al abrir, en el computador el cursor queda listo en la caja. En
			// el celular no: el teclado taparía los temas.
			if (caja && !esTactil()) caja.focus();
		} else if (enfocarCaja.current && caja) {
			caja.focus();
		} else {
			tituloRef.current?.focus();
		}
		enfocarCaja.current = false;
		// El nombre de la pestaña sale de la pantalla que de verdad se ve (una
		// dirección sin datos muestra el inicio y debe decir eso).
		const enRespuesta = !!tituloRef.current?.closest(".guia-veredicto");
		const t = enRespuesta ? "Respuesta a su pregunta" : tituloRef.current?.textContent;
		document.title = t ? `ATLAS: ${t}` : "ATLAS";
	}, [clave, sinSenal, error]);

	/** Envía la pregunta (o la deja pendiente si no hay señal) y pasa a la espera. */
	function enviar(p: PreguntaActual, esNueva: boolean) {
		setPregunta(p);
		setMostradas((m) => ({ ...(esNueva ? {} : m), [p.envio]: p }));
		setIntentos(0);
		if (typeof navigator !== "undefined" && navigator.onLine === false) {
			setSinSenal(true);
			pendienteRef.current = null;
		} else {
			setSinSenal(false);
			pendienteRef.current = { envio: p.envio, nueva: esNueva };
			setTurnoEnvio((n) => n + 1);
		}
		ir("espera");
	}

	/** Pregunta nueva: empieza una conversación propia. */
	function preguntar(texto: string, envio: string, playa: string | null) {
		chat.resetChat();
		enviar({ texto, envio, playa }, true);
	}

	/** Pregunta de seguimiento: sigue la misma conversación (el backend recuerda lo anterior). */
	function seguir(texto: string) {
		enviar({ texto, envio: texto, playa: null }, false);
	}

	// ¿La pregunta en curso sigue una conversación que ya tiene respuestas?
	const esSeguimiento = !!pregunta && turnos.length > 0 && !!chat.conversationId;

	function reintentar() {
		if (!pregunta) {
			ir("inicio");
			return;
		}
		if (!esSeguimiento) chat.resetChat();
		if (navigator.onLine === false) {
			setSinSenal(true);
			setIntentos((n) => n + 1);
			return;
		}
		setSinSenal(false);
		setIntentos(0);
		pendienteRef.current = { envio: pregunta.envio, nueva: !esSeguimiento };
		setTurnoEnvio((n) => n + 1);
	}

	function cancelarYVolver() {
		pendienteRef.current = null;
		setSinSenal(false);
		// En un seguimiento solo se detiene esta pregunta: "atrás" vuelve a la
		// respuesta anterior, que sigue abierta.
		if (esSeguimiento) chat.cancel();
		else chat.resetChat();
		window.history.back();
	}

	function otraPregunta() {
		// La respuesta que se deja queda guardada: si la persona toca "atrás"
		// desde el inicio, la vuelve a ver (QA-15) en vez de un inicio repetido.
		if (vista) {
			setGuardada({ pregunta: vista.pregunta, texto: vista.mensaje.text, fuentes: vista.mensaje.sources ?? [] });
		}
		chat.resetChat();
		setMostradas({});
		setPregunta(null);
		setBorrador("");
		setSeguimiento("");
		setSinSenal(false);
		ir("inicio");
	}

	/** Lleva a la caja del inicio con el cursor puesto. */
	function irACaja(atras: boolean) {
		enfocarCaja.current = true;
		if (atras) volver("inicio");
		else ir("inicio");
	}

	async function calificar(id: string, c: Calificacion) {
		const nota = c.util ? 5 : 1;
		await chat.rateMessage(id, { pertinence: nota, accuracy: nota }, c.comentario);
	}

	const tema = buscarTema(ruta[1]);

	if (pantalla === "tema" && tema) {
		return (
			<PantallaTema
				tema={tema}
				tituloRef={tituloRef}
				onVolver={() => volver("inicio")}
				onEscribir={() => irACaja(true)}
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
		return <PantallaEspera tituloRef={tituloRef} etapa={stage} onVolver={cancelarYVolver} />;
	}

	if (pantalla === "respuesta" && vista) {
		const { mensaje } = vista;
		return (
			<Respuesta
				// Cada respuesta es una pantalla nueva: "¿Le sirvió?" empieza de cero.
				key={numero}
				pregunta={vista.pregunta.texto}
				playa={vista.pregunta.playa}
				texto={mensaje.text}
				fuentes={mensaje.sources ?? []}
				onVolver={() => volver("inicio")}
				puedeCalificar={
					!loading &&
					!!chat.conversationId &&
					mensaje.persistenceStatus !== "failed" &&
					!persistingMessageIds.has(mensaje.id)
				}
				onCalificar={(c) => calificar(mensaje.id, c)}
				onOtraPregunta={otraPregunta}
				onTerminar={encuestaHecha ? undefined : () => ir(`opinion/${numero}`)}
				invitarEncuesta={!encuestaHecha && numero === 1}
				onEscribirDeNuevo={() => {
					setBorrador(vista.pregunta.texto);
					irACaja(false);
				}}
				seguimiento={seguimiento}
				onCambioSeguimiento={setSeguimiento}
				onSeguir={seguir}
				muchasSeguidas={turnos.length >= TOPE_SEGUIMIENTO}
				tituloRef={tituloRef}
			/>
		);
	}

	// Encuesta de percepción (al terminar): queda ligada a la última conversación.
	if (pantalla === "opinion") {
		return (
			<PantallaOpinion
				tituloRef={tituloRef}
				conversationId={chat.conversationId ?? null}
				onVolver={() => window.history.back()}
				onOtraPregunta={otraPregunta}
				onSalir={() => salir({ olvidarCorreo: true })}
				onEnviada={() => setEncuestaHecha(true)}
			/>
		);
	}

	// Respuesta guardada (tras recargar la página): se muestra igual, pero sin
	// "¿Le sirvió?", porque la conversación ya no está abierta en el chat.
	if (pantalla === "respuesta" && !loading && guardada) {
		return (
			<Respuesta
				key="guardada"
				pregunta={guardada.pregunta.texto}
				playa={guardada.pregunta.playa}
				texto={guardada.texto}
				fuentes={guardada.fuentes}
				puedeCalificar={false}
				onCalificar={async () => {}}
				onVolver={() => volver("inicio")}
				onOtraPregunta={otraPregunta}
				onEscribirDeNuevo={() => {
					setBorrador(guardada.pregunta.texto);
					irACaja(false);
				}}
				// La conversación ya no está abierta: un seguimiento iría sin
				// contexto, así que solo se ofrece empezar de nuevo.
				puedeSeguir={false}
				seguimiento={seguimiento}
				onCambioSeguimiento={setSeguimiento}
				onSeguir={seguir}
				muchasSeguidas={false}
				tituloRef={tituloRef}
			/>
		);
	}

	// Inicio (y cualquier dirección que ya no tiene datos, p. ej. al recargar
	// en la pantalla de respuesta, o el antiguo `#escribir`: la caja está aquí).
	return (
		<>
			<PantallaInicio
				tituloRef={tituloRef}
				cajaRef={cajaRef}
				borrador={borrador}
				onCambio={setBorrador}
				onPreguntar={(texto) => {
					setBorrador(texto);
					preguntar(texto, texto, null);
				}}
				onTema={(t) => ir(`tema/${t.id}`)}
			/>
			<VentanaParticipante />
		</>
	);
}
