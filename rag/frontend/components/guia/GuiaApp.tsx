"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
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
	PantallaSeguir,
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
import {
	exponerEnConsola,
	iniciarMedicion,
	marcarEtapa,
	marcarPrimerTexto,
	terminarMedicion,
	transcurrido,
} from "@/lib/medicion";
import { borrarPendiente, guardarPendiente, leerPendiente } from "@/lib/guia/pendiente";
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
						<Flujo usuario={user.user_id} />
					</ConPrivacidad>
				) : (
					<Entrar tituloRef={tituloRef} />
				)}
			</main>
		</div>
	);
}

/**
 * Cerrar sesión desde el flujo guiado (encabezado, aviso de datos y "Terminar
 * y dejar el celular para otra persona"). Celular compartido: además del
 * token se borra lo que el flujo guarda en la pestaña (hilo, borrador y
 * pregunta pendiente, E2-11) y el correo recordado en el ingreso (E2-20).
 */
function useSalir() {
	const { signOut } = useAuth();
	return () => {
		detenerVoz();
		guardar(null);
		guardarBorrador("");
		borrarPendiente();
		// E2-20 (rama ux): al salir, la siguiente persona no ve el correo
		// anterior. Vale para toda salida, no solo "dejar el celular".
		forgetEmail();
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
				{/* El logo lleva al inicio (a los temas). Es un enlace real a "/" para
				    abrirlo en otra pestaña; con un toque normal avisa al flujo, que
				    vuelve al inicio sin recargar (igual que "Volver al inicio"). El
				    nombre accesible incluye el texto visible (WCAG 2.5.3). */}
				<Link
					href="/"
					className="marca"
					aria-label="ATLAS, preguntas sobre las Playas de Santa Marta: ir al inicio"
					onClick={(e) => {
						if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
						e.preventDefault();
						window.dispatchEvent(new Event(EVENTO_INICIO));
					}}
				>
					{/* eslint-disable-next-line @next/next/no-img-element -- logo de 12 KB, sin optimizador */}
					<img src="/brand/atlas-96.png" alt="" width={40} height={40} />
					<span>
						<span className="nombre">ATLAS</span>
						<span className="zona">
							<span className="largo">Preguntas sobre las playas de </span>
							<span className="corto">Playas de </span>
							<span className="lugar">Santa Marta</span>
						</span>
					</span>
				</Link>
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
/** Evento con que el logo del encabezado pide al flujo volver al inicio. */
const EVENTO_INICIO = "atlas:ir-inicio";
const CLAVE_BORRADOR = "atlas:borrador";

/**
 * Lo escrito en la caja del inicio, para no perderlo si la pestaña se recarga.
 * Se guarda con su dueño: si la sesión vence sin "Salir" y entra otra persona
 * en el mismo celular, el borrador se borra sin mostrarse (mismo criterio que
 * la pregunta pendiente y el hilo, E2-19).
 */
function leerBorrador(usuario: string): string {
	try {
		const crudo = window.sessionStorage.getItem(CLAVE_BORRADOR);
		if (!crudo) return "";
		const d = JSON.parse(crudo) as { usuario?: string; texto?: string };
		if (d.usuario !== usuario || typeof d.texto !== "string") {
			window.sessionStorage.removeItem(CLAVE_BORRADOR);
			return "";
		}
		return d.texto;
	} catch {
		// Formato anterior (texto suelto, sin dueño) o almacenamiento roto: no se muestra.
		try {
			window.sessionStorage.removeItem(CLAVE_BORRADOR);
		} catch {
			// nada que borrar
		}
		return "";
	}
}

function guardarBorrador(texto: string, usuario?: string): void {
	try {
		if (texto && usuario) window.sessionStorage.setItem(CLAVE_BORRADOR, JSON.stringify({ usuario, texto }));
		else window.sessionStorage.removeItem(CLAVE_BORRADOR);
	} catch {
		// Sin almacenamiento: solo se pierde esta comodidad.
	}
}

interface TurnoGuardado {
	/** id del mensaje de respuesta. */
	id: string;
	pregunta: PreguntaActual;
	texto: string;
	fuentes: SourceGroup[];
}

/**
 * El hilo de esta pestaña (todas las preguntas del tema con sus respuestas),
 * para no perderlo si se recarga la página. Con el id de la conversación,
 * al recargar se vuelve a abrir y se puede seguir preguntando.
 */
interface HiloGuardado {
	/** De quién es: solo se muestra a esa persona (E2-19, sesión vencida sin "Salir"). */
	usuario?: string;
	conversationId: string | null;
	threadId: string | null;
	turnos: TurnoGuardado[];
}

function leerGuardada(usuario: string): HiloGuardado | null {
	try {
		const crudo = window.sessionStorage.getItem(CLAVE_GUARDADA);
		if (!crudo) return null;
		const d = JSON.parse(crudo) as Partial<HiloGuardado> & Partial<Omit<TurnoGuardado, "id">>;
		// Si la sesión venció sin "Salir" y entra otra persona, el hilo
		// anterior se borra sin mostrarse (mismo criterio que la pregunta pendiente).
		if (d.usuario !== usuario) {
			window.sessionStorage.removeItem(CLAVE_GUARDADA);
			return null;
		}
		if (Array.isArray(d.turnos) && d.turnos.length > 0) {
			return { usuario, conversationId: d.conversationId ?? null, threadId: d.threadId ?? null, turnos: d.turnos };
		}
		// Formato anterior (una sola respuesta, sin conversación).
		if (d.pregunta && typeof d.texto === "string") {
			return {
				conversationId: null,
				threadId: null,
				turnos: [{ id: "guardada", pregunta: d.pregunta, texto: d.texto, fuentes: d.fuentes ?? [] }],
			};
		}
		return null;
	} catch {
		return null;
	}
}

function guardar(r: HiloGuardado | null): void {
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

function Flujo({ usuario }: { usuario: string }) {
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
	const { messages, loading, error, stage, isStreaming, generationFinished, persistingMessageIds } = chat;

	const [pregunta, setPregunta] = useState<PreguntaActual | null>(null);
	// Cómo se muestra cada pregunta enviada (lo que se envía puede llevar la
	// playa al final). Clave: el texto enviado.
	const [mostradas, setMostradas] = useState<Record<string, PreguntaActual>>(() => {
		// Al recargar con un hilo guardado, cada pregunta vuelve a mostrarse
		// como la vio la persona (con su playa), no como se envió.
		const g = typeof window === "undefined" ? null : leerGuardada(usuario);
		return Object.fromEntries((g?.turnos ?? []).map((t) => [t.pregunta.envio, t.pregunta]));
	});
	// "¿Le sirvió?" ya respondido en esta visita (id de la respuesta → le sirvió).
	// Así, al volver a una respuesta o al verla plegada en el hilo, no se pregunta otra vez.
	const [calificadas, setCalificadas] = useState<Record<string, boolean>>({});
	// Pregunta que espera para enviarse (ver efecto de abajo): una nueva
	// espera a que el chat quede vacío; un seguimiento, a que termine lo que
	// estuviera en curso. Va en una ref; `turnoEnvio` solo dispara el efecto.
	const pendienteRef = useRef<{ envio: string; nueva: boolean } | null>(null);
	const [turnoEnvio, setTurnoEnvio] = useState(0);
	const [sinSenal, setSinSenal] = useState(false);
	const [borrador, setBorrador] = useState(() => (typeof window === "undefined" ? "" : leerBorrador(usuario)));
	useEffect(() => guardarBorrador(borrador, usuario), [borrador, usuario]);
	const [seguimiento, setSeguimiento] = useState("");
	// Veces que se tocó "Intentar otra vez" sin señal (para que se note que intentó).
	const [intentos, setIntentos] = useState(0);
	const [guardada, setGuardada] = useState<HiloGuardado | null>(() =>
		typeof window === "undefined" ? null : leerGuardada(usuario),
	);
	// Pregunta que quedó sin respuesta (sesión vencida o recarga durante la
	// espera): al volver se ofrece seguir con ella (UX-02). Solo a su dueño.
	const [retomar, setRetomar] = useState<PreguntaActual | null>(() =>
		typeof window === "undefined" ? null : leerPendiente(usuario),
	);
	const [segundos, setSegundos] = useState(0);
	// Recargó la página en una respuesta: se vuelve a abrir la conversación
	// (el backend la recupera de la base) para poder seguir preguntando.
	const [cargandoHilo, setCargandoHilo] = useState(false);

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
			// El texto llega entero de una vez: si el efecto de "primer texto" no
			// alcanzó a correr, se marca aquí, antes de cerrar la medición (E2-22).
			marcarPrimerTexto();
			terminarMedicion("ok");
			borrarPendiente();
			ir(`respuesta/${turnos.length}`, { reemplazar: true });
		}
	}, [pantalla, nueva, turnos.length, generationFinished, loading, error, ir]);

	// Medición del tiempo hasta la respuesta útil (UX-02): etapas del backend,
	// primer texto y error. Solo tiempos; nunca el texto de la pregunta.
	useEffect(() => exponerEnConsola(), []);
	useEffect(() => {
		if (stage) marcarEtapa(stage);
	}, [stage]);
	const hayTexto = !!nueva?.text;
	useEffect(() => {
		if (isStreaming || hayTexto) marcarPrimerTexto();
	}, [isStreaming, hayTexto]);
	useEffect(() => {
		if (error) terminarMedicion("error");
	}, [error]);

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

	// Todo el hilo se guarda en la pestaña (sessionStorage): si la persona
	// recarga sin querer (jalar hacia abajo en el celular), lo vuelve a ver y
	// puede seguir preguntando. Se borra al salir (celular compartido, E2-11).
	const { conversationId, getThreadId, loadConversation } = chat;
	const hiloActual = useMemo<HiloGuardado | null>(
		() =>
			turnos.length === 0
				? null
				: {
						usuario,
						conversationId,
						threadId: getThreadId(),
						turnos: turnos.map((t) => ({
							id: t.mensaje.id,
							pregunta: t.pregunta,
							texto: t.mensaje.text,
							fuentes: t.mensaje.sources ?? [],
						})),
					},
		[turnos, conversationId, getThreadId, usuario],
	);
	useEffect(() => {
		if (!vista || loading || error || !hiloActual) return;
		guardar(hiloActual);
	}, [vista, loading, error, hiloActual]);

	// Contador de segundos en la espera (UX-02; se actualiza 1 vez por segundo).
	const esperando = pantalla === "espera" && !!pregunta && !error && !sinSenal;
	useEffect(() => {
		if (!esperando) return;
		const id = window.setInterval(() => {
			setSegundos(Math.floor((transcurrido() ?? 0) / 1000));
		}, 1000);
		return () => window.clearInterval(id);
	}, [esperando]);

	// Al abrir la página (recarga): si quedó en una respuesta con su
	// conversación guardada, se vuelve a abrir. Se decide en el primer pintado
	// y no después: "atrás" hacia un tema que ya se dejó no lo reabre.
	const aReabrir = useRef(pantalla === "respuesta" && guardada?.conversationId ? guardada : null);
	useEffect(() => {
		const g = aReabrir.current;
		if (!g?.conversationId) return;
		setCargandoHilo(true);
		const ahora = new Date();
		void loadConversation({
			id: g.conversationId,
			threadId: g.threadId ?? getThreadId(),
			title: null,
			createdAt: ahora,
			updatedAt: ahora,
			messageCount: g.turnos.length * 2,
		}).finally(() => setCargandoHilo(false));
		// Sin marca de "ya hecho": en desarrollo React monta dos veces y el
		// primer intento se cancela al desmontar; el segundo es el que vale.
		// eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir la página
	}, []);

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
		setSegundos(0);
		setRetomar(null);
		// Si la sesión vence a mitad de la espera, la pregunta no se pierde: al
		// volver a entrar la misma persona se le ofrece seguir (UX-02, E2-19).
		// Un seguimiento se guarda también; al retomarlo se envía como pregunta
		// nueva (la conversación ya no está abierta).
		guardarPendiente(p, usuario);
		if (typeof navigator !== "undefined" && navigator.onLine === false) {
			setSinSenal(true);
			pendienteRef.current = null;
		} else {
			setSinSenal(false);
			iniciarMedicion();
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
		setSegundos(0);
		iniciarMedicion();
		pendienteRef.current = { envio: pregunta.envio, nueva: !esSeguimiento };
		setTurnoEnvio((n) => n + 1);
	}

	function cancelarYVolver() {
		terminarMedicion("cancelada");
		borrarPendiente();
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
		if (vista && hiloActual) setGuardada(hiloActual);
		chat.resetChat();
		borrarPendiente();
		setMostradas({});
		setPregunta(null);
		setBorrador("");
		setSeguimiento("");
		setSinSenal(false);
		ir("inicio");
	}

	// El logo del encabezado (fuera de este componente) pide volver al inicio.
	const alInicio = useRef<() => void>(() => {});
	useEffect(() => {
		alInicio.current = () => {
			pendienteRef.current = null;
			otraPregunta();
		};
	});
	useEffect(() => {
		const f = () => alInicio.current();
		window.addEventListener(EVENTO_INICIO, f);
		return () => window.removeEventListener(EVENTO_INICIO, f);
	}, []);

	/** Lleva a la caja del inicio con el cursor puesto. */
	function irACaja(atras: boolean) {
		enfocarCaja.current = true;
		if (atras) volver("inicio");
		else ir("inicio");
	}

	async function calificar(id: string, c: Calificacion) {
		const nota = c.util ? 5 : 1;
		await chat.rateMessage(id, { pertinence: nota, accuracy: nota }, c.comentario);
		setCalificadas((m) => ({ ...m, [id]: c.util }));
	}

	/** ¿Esta respuesta ya quedó guardada y se puede calificar? */
	function sePuedeCalificar(m: Message): boolean {
		return (
			!loading && !!chat.conversationId && m.persistenceStatus !== "failed" && !persistingMessageIds.has(m.id)
		);
	}

	const tema = buscarTema(ruta[1]);

	// Al volver a entrar (o recargar) con una pregunta sin responder (UX-02).
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
		return (
			<PantallaEspera tituloRef={tituloRef} etapa={stage} segundos={segundos} onVolver={cancelarYVolver} />
		);
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
				puedeCalificar={sePuedeCalificar(mensaje)}
				onCalificar={(c) => calificar(mensaje.id, c)}
				guardado={
					persistingMessageIds.has(mensaje.id)
						? "guardando"
						: mensaje.persistenceStatus === "failed"
							? "fallo"
							: "ok"
				}
				onGuardarOtraVez={() => void chat.retryPersistMessage(mensaje.id)}
				calificada={calificadas[mensaje.id]}
				anteriores={turnos.slice(0, numero - 1).map((t) => ({
					id: t.mensaje.id,
					pregunta: t.pregunta.texto,
					playa: t.pregunta.playa,
					texto: t.mensaje.text,
					fuentes: t.mensaje.sources ?? [],
					calificada: calificadas[t.mensaje.id],
					puedeCalificar: sePuedeCalificar(t.mensaje),
				}))}
				onCalificarAnterior={calificar}
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
				onSalir={() => salir()}
				onEnviada={() => setEncuestaHecha(true)}
			/>
		);
	}

	// Hilo guardado (tras recargar, mientras se vuelve a abrir la
	// conversación, o al volver con "atrás" a un tema que ya se dejó): se
	// muestra igual, pero sin "¿Le sirvió?" ni caja para seguir, porque esa
	// conversación no está abierta.
	const turnoGuardado = guardada ? (guardada.turnos[numero - 1] ?? guardada.turnos[guardada.turnos.length - 1]) : null;
	if (pantalla === "respuesta" && (!loading || cargandoHilo) && guardada && turnoGuardado) {
		const indice = guardada.turnos.indexOf(turnoGuardado);
		return (
			<Respuesta
				key={`guardada-${indice}`}
				pregunta={turnoGuardado.pregunta.texto}
				playa={turnoGuardado.pregunta.playa}
				texto={turnoGuardado.texto}
				fuentes={turnoGuardado.fuentes}
				puedeCalificar={false}
				onCalificar={async () => {}}
				calificada={calificadas[turnoGuardado.id]}
				anteriores={guardada.turnos.slice(0, indice).map((t) => ({
					id: t.id,
					pregunta: t.pregunta.texto,
					playa: t.pregunta.playa,
					texto: t.texto,
					fuentes: t.fuentes,
					calificada: calificadas[t.id],
					puedeCalificar: false,
				}))}
				onVolver={() => volver("inicio")}
				onOtraPregunta={otraPregunta}
				onEscribirDeNuevo={() => {
					setBorrador(turnoGuardado.pregunta.texto);
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
