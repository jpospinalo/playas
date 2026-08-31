"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "@/components/providers/AuthProvider";
import { AuthModal } from "@/components/common/AuthModal";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatInput } from "@/components/chat/ChatInput";
import { ContextWarning } from "@/components/chat/ContextWarning";
import { EmptyState } from "@/components/chat/EmptyState";
import { FeedbackButton } from "@/components/chat/FeedbackButton";
import { FeedbackModal } from "@/components/chat/FeedbackModal";
import { LoadingBubble } from "@/components/chat/LoadingBubble";
import { MessageList } from "@/components/chat/MessageList";

const SCROLL_THRESHOLD = 100; // px from bottom to consider "at bottom"
const SIDEBAR_STORAGE_KEY = "rag-playas:chat-sidebar-expanded";
const MOBILE_SIDEBAR_QUERY = "(max-width: 767px)";

/**
 * Límite de autenticación del chat.
 *
 * Solo consulta `useAuth()`. Mientras no haya sesión válida, muestra el modal
 * de login obligatorio y no monta nada del árbol autenticado (`useChat`,
 * `useConversations`, etc.), para que ningún estado de conversación pueda
 * sobrevivir a un cambio de cuenta.
 *
 * `AuthenticatedChat` se monta con `key={user.user_id}`: React lo desmonta y
 * vuelve a montar por completo cada vez que cambia el usuario autenticado
 * (login, logout o cambio de cuenta sin recargar la página), descartando
 * mensajes, conversación activa, referencias y el AbortController de
 * cualquier sesión anterior.
 */
export function ChatInterface() {
	const { user, loading: authLoading } = useAuth();

	if (authLoading || !user) {
		return (
			// Este estado (sin sesión) también necesita su propio landmark
			// `<main id="main-content">`, igual que el resto de las vistas, para
			// que el enlace de salto y la estructura de landmarks sean
			// consistentes en toda la app.
			<main
				id="main-content"
				className="relative flex flex-1 overflow-hidden"
			>
				<AuthModal open={!authLoading} dismissible={false} onClose={() => {}} />
			</main>
		);
	}

	return <AuthenticatedChat key={user.user_id} />;
}

function AuthenticatedChat() {
	const {
		conversations,
		loading: conversationsLoading,
		error: conversationsError,
		refresh: refreshConversations,
	} = useConversations();
	const [sidebarOpen, setSidebarOpen] = useState(true);
	// Estado del panel off-canvas móvil, deliberadamente independiente de
	// `sidebarOpen` (que persiste la preferencia de colapso del riel de
	// escritorio en localStorage): el panel móvil siempre arranca cerrado y
	// este estado nunca se lee de ni se escribe en localStorage.
	const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
	// "Presencia modal" del panel móvil off-canvas: a diferencia de
	// `mobileSidebarOpen` (que solo indica si el panel está entrando o
	// saliendo), esta bandera sigue en `true` durante toda su animación de
	// salida y solo baja a `false` cuando `ConversationSidebar` confirma,
	// vía `onMobileExitComplete`, que el panel ya terminó de salir. La usa
	// el `inert` del área principal del chat, más abajo: debe seguir
	// bloqueada mientras el panel sigue montado y visible, no solo
	// mientras `mobileSidebarOpen` es `true`.
	const [mobileSidebarPresent, setMobileSidebarPresent] =
		useState(mobileSidebarOpen);
	const [prevMobileSidebarOpen, setPrevMobileSidebarOpen] =
		useState(mobileSidebarOpen);
	const [sidebarTransitionEnabled, setSidebarTransitionEnabled] =
		useState(false);
	const [showFeedbackModal, setShowFeedbackModal] = useState(false);

	const {
		messages,
		input,
		loading,
		isStreaming,
		stageMessage,
		error,
		contextPercent,
		conversationId,
		ratedMessageIds,
		persistingMessageIds,
		canCancel,
		generationStopped,
		generationFinished,
		setInput,
		submit,
		resetChat,
		loadConversation,
		retryPersistMessage,
		cancel,
		rateMessage,
	} = useChat({ onConversationChanged: refreshConversations });

	// El panel vuelve a entrar: su presencia se activa de inmediato (no hay
	// que esperar ninguna animación para empezar a bloquear el área
	// principal). Se ajusta durante el render, comparando con el valor
	// anterior guardado en estado (mismo patrón que `ConversationSidebar`
	// usa para su propia "presencia modal").
	if (mobileSidebarOpen !== prevMobileSidebarOpen) {
		setPrevMobileSidebarOpen(mobileSidebarOpen);
		if (mobileSidebarOpen) {
			setMobileSidebarPresent(true);
		}
	}

	useEffect(() => {
		const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
		let transitionFrame = 0;

		const preferenceFrame = window.requestAnimationFrame(() => {
			if (stored !== null) {
				setSidebarOpen(stored === "true");
			}
			transitionFrame = window.requestAnimationFrame(() => {
				setSidebarTransitionEnabled(true);
			});
		});

		return () => {
			window.cancelAnimationFrame(preferenceFrame);
			if (transitionFrame) window.cancelAnimationFrame(transitionFrame);
		};
	}, []);

	// Si el viewport deja de ser móvil (p. ej. al redimensionar la ventana o
	// rotar el dispositivo) mientras el panel off-canvas sigue abierto, se
	// cierra automáticamente: de lo contrario `mobileSidebarOpen` quedaría en
	// `true` indefinidamente (ni el botón que lo cierra, visible solo con
	// `md:hidden`, ni el backdrop, también `md:hidden`, ver
	// ConversationSidebar, seguirían siendo alcanzables en el nuevo viewport
	// de escritorio), mientras el `inert` que ese estado activa sobre el
	// área principal del chat sí permanecería.
	useEffect(() => {
		const mql = window.matchMedia(MOBILE_SIDEBAR_QUERY);
		function handleViewportChange(event: MediaQueryListEvent) {
			if (!event.matches) {
				// Ya no coincide con el query móvil: el viewport pasó a
				// escritorio.
				setMobileSidebarOpen(false);
			}
		}
		mql.addEventListener("change", handleViewportChange);
		return () => mql.removeEventListener("change", handleViewportChange);
	}, []);

	// Según el viewport activo al momento del click, alterna el riel de
	// escritorio (persistido) o el panel móvil (no persistido). El mismo
	// botón de hamburguesa (`ChatHeader`, solo visible con `md:hidden`) y el
	// mismo botón "×"/riel colapsado de `ConversationSidebar` (solo visibles
	// en su propio viewport) funcionan sin cambios: cada uno solo es
	// alcanzable en el viewport para el que tiene sentido.
	const toggleSidebar = useCallback(() => {
		if (window.matchMedia(MOBILE_SIDEBAR_QUERY).matches) {
			setMobileSidebarOpen((current) => !current);
			return;
		}
		setSidebarOpen((current) => {
			const next = !current;
			window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
			return next;
		});
	}, []);

	// Cierre explícito del panel móvil (backdrop, botón de cierre, Escape
	// vía `useDialog` dentro de `ConversationSidebar`).
	const closeMobileSidebar = useCallback(() => {
		setMobileSidebarOpen(false);
	}, []);

	const closeSidebarOnMobile = useCallback(() => {
		if (window.matchMedia(MOBILE_SIDEBAR_QUERY).matches) {
			setMobileSidebarOpen(false);
		}
	}, []);

	// `ConversationSidebar` la invoca cuando el panel móvil (y su backdrop)
	// ya terminaron por completo su animación de salida — nunca antes. Solo
	// entonces se suelta el `inert` del área principal del chat.
	const handleMobileSidebarExitComplete = useCallback(() => {
		setMobileSidebarPresent(false);
	}, []);

	/*
	 * textareaRef lives here so ChatInterface can focus the input
	 * when the user selects an example question.
	 */
	const textareaRef = useRef<HTMLTextAreaElement>(null);

	// Scroll container and sentinel refs
	const scrollContainerRef = useRef<HTMLElement>(null);
	const messagesEndRef = useRef<HTMLDivElement>(null);

	// Track whether user is pinned to the bottom. Using a ref avoids
	// re-renders on every scroll event; only the button visibility needs state.
	const isAtBottomRef = useRef(true);
	const [showScrollButton, setShowScrollButton] = useState(false);

	// Passive scroll listener — detects when user has scrolled away from bottom.
	useEffect(() => {
		const container = scrollContainerRef.current;
		if (!container) return;

		function handleScroll() {
			const distanceFromBottom =
				container!.scrollHeight -
				container!.scrollTop -
				container!.clientHeight;
			const atBottom = distanceFromBottom < SCROLL_THRESHOLD;

			if (isAtBottomRef.current !== atBottom) {
				isAtBottomRef.current = atBottom;
				setShowScrollButton(!atBottom);
			}
		}

		container.addEventListener("scroll", handleScroll, { passive: true });
		return () => container.removeEventListener("scroll", handleScroll);
	}, []);

	// Auto-scroll to bottom when messages or loading state change,
	// but only when the user is already pinned to the bottom.
	useEffect(() => {
		if (isAtBottomRef.current) {
			messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
		}
	}, [messages, loading]);

	const scrollToBottom = useCallback(() => {
		isAtBottomRef.current = true;
		setShowScrollButton(false);
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, []);

	function handleSubmit(question: string) {
		// Always snap to bottom when the user sends a new message.
		isAtBottomRef.current = true;
		setShowScrollButton(false);
		submit(question);
	}

	const showEmptyState = messages.length === 0 && !loading && !error;

	// Región de estado angosta y dedicada para el progreso de la generación
	// (etapa mientras se espera el primer token, luego "generando
	// respuesta"), en vez de anunciar todo el `<main>` con `aria-live`, lo
	// que convertiría cualquier cambio dentro del área de conversación
	// (incluida cada actualización de la respuesta en streaming) en un
	// anuncio para el lector de pantalla. Los avisos de error y de
	// "Generación detenida" ya son regiones vivas propias (`role="alert"` /
	// `role="status"`), así que no dependen de este texto.
	//
	// `generationFinished` tiene prioridad sobre `loading`: el
	// streaming puede terminar (y `generationFinished` pasar a `true`,
	// ver `useChat.submit()`) mientras `loading` sigue en `true` durante
	// el guardado posterior de la respuesta — una persistencia lenta ya
	// no retiene el anuncio de "Generando respuesta…" después de que el
	// usuario ya vio la respuesta completa en pantalla. `generationFinished`
	// solo pasa a `true` para la operación vigente y solo tras un
	// streaming que sí completó con éxito (nunca tras un error o una
	// cancelación, que ya tienen sus propias regiones vivas), y se
	// limpia de nuevo al iniciar la siguiente operación — así que ni un
	// reinicio del chat, un cambio de conversación, ni una operación
	// obsoleta que termine tarde pueden anunciar un final que no
	// corresponde a la respuesta vigente. Antes del primer token (y
	// antes del primer evento de estado del servidor), `stageMessage`
	// todavía es `null`: sin una etapa por defecto, la región quedaba
	// vacía justo cuando el envío recién empieza.
	const streamingStatus = generationFinished
		? "Respuesta finalizada."
		: loading
			? isStreaming
				? "Generando respuesta…"
				: (stageMessage ?? "Procesando consulta…")
			: "";

	return (
		<div className="relative flex flex-1 overflow-hidden">
			{/* Sidebar de conversaciones */}
			<ConversationSidebar
				conversations={conversations}
				activeConversationId={conversationId}
				loading={conversationsLoading}
				loadError={conversationsError}
				isExpanded={sidebarOpen}
				mobileOpen={mobileSidebarOpen}
				transitionEnabled={sidebarTransitionEnabled}
				onSelectConversation={async (conv) => {
					closeSidebarOnMobile();
					await loadConversation(conv);
				}}
				onNewChat={() => {
					resetChat();
					closeSidebarOnMobile();
				}}
				onToggleSidebar={toggleSidebar}
				onCloseMobile={closeMobileSidebar}
				onMobileExitComplete={handleMobileSidebarExitComplete}
				onConversationsRefresh={refreshConversations}
			/>

			{/* Área principal del chat: `inert` mientras el panel móvil sigue
			    montado (abierto o todavía animando su salida), para sacarla del
			    árbol de tabulación y ocultarla de la tecnología de asistencia,
			    igual que el resto de la página detrás de un overlay modal (el
			    propio panel y su backdrop viven fuera de este `<div>`, así que
			    no se ven afectados). Usa `mobileSidebarPresent`, no
			    `mobileSidebarOpen` directamente: debe seguir bloqueada durante
			    toda la animación de salida, no solo mientras el panel está
			    nominalmente "abierto" (ver `onMobileExitComplete` arriba). */}
			<div
				className="flex flex-1 flex-col overflow-hidden"
				inert={mobileSidebarPresent}
			>
				<FeedbackModal
					open={showFeedbackModal}
					conversationId={conversationId}
					onClose={() => setShowFeedbackModal(false)}
				/>
				<ChatHeader
					onToggleSidebar={toggleSidebar}
					sidebarOpen={mobileSidebarOpen}
				/>

				<main
					ref={scrollContainerRef}
					id="main-content"
					className="flex flex-1 flex-col overflow-y-auto"
					aria-label="Conversación"
				>
					<div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
						{streamingStatus}
					</div>

					{showEmptyState ? (
						<EmptyState
							input={input}
							loading={loading}
							textareaRef={textareaRef}
							onChange={setInput}
							onSubmit={handleSubmit}
						/>
					) : (
						<div className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-4 py-6">
							<MessageList
								messages={messages}
								ratedMessageIds={ratedMessageIds}
								persistingMessageIds={persistingMessageIds}
								onRetryPersist={retryPersistMessage}
								onMessageRate={rateMessage}
							/>

							{/* Show loading bubble only while waiting for the first token */}
							<AnimatePresence>
								{loading && !isStreaming && (
									<LoadingBubble label={stageMessage} />
								)}
							</AnimatePresence>

							<AnimatePresence>
								{error && (
									<motion.div
										role="alert"
										className="rounded-xl border border-danger/30 bg-danger-bg px-4 py-3 text-sm text-danger"
										initial={{ opacity: 0, y: 8 }}
										animate={{ opacity: 1, y: 0 }}
										exit={{ opacity: 0, y: -4 }}
										transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
									>
										{error}
									</motion.div>
								)}
							</AnimatePresence>

							{/* A6 — aviso breve y no persistente tras detener una
							    generación con "Detener": nunca se trata como un
							    error de red. */}
							<AnimatePresence>
								{generationStopped && (
									<motion.div
										role="status"
										className="rounded-xl border border-border bg-elevated/60 px-4 py-3 text-sm text-muted"
										initial={{ opacity: 0, y: 8 }}
										animate={{ opacity: 1, y: 0 }}
										exit={{ opacity: 0, y: -4 }}
										transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
									>
										Generación detenida.
									</motion.div>
								)}
							</AnimatePresence>

							{/* Scroll-to-bottom sentinel */}
							<div ref={messagesEndRef} aria-hidden="true" />
						</div>
					)}
				</main>

				{/* Floating scroll-to-bottom button — visible when user has scrolled up */}
				{showScrollButton && messages.length > 0 && (
					<div className="pointer-events-none absolute bottom-0 left-0 right-0 z-10 flex justify-center pb-20">
						<button
							onClick={scrollToBottom}
							aria-label="Ir al final de la conversación"
							className="animate-scroll-btn-in pointer-events-auto flex items-center gap-1.5 rounded-full border border-border bg-surface px-3.5 py-2 text-xs font-medium text-muted shadow-md transition-colors duration-150 hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="13"
								height="13"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2.5"
								strokeLinecap="round"
								strokeLinejoin="round"
								aria-hidden="true"
							>
								<path d="m6 9 6 6 6-6" />
							</svg>
							Ir al final
						</button>
					</div>
				)}

				<ContextWarning percent={contextPercent} onNewChat={resetChat} />

				{!showEmptyState && (
					<ChatInput
						value={input}
						loading={loading}
						canCancel={canCancel}
						onCancel={cancel}
						textareaRef={textareaRef}
						onChange={setInput}
						onSubmit={() => handleSubmit(input)}
						sideSlot={
							messages.length > 0 ? (
								<FeedbackButton onClick={() => setShowFeedbackModal(true)} />
							) : undefined
						}
					/>
				)}
			</div>
		</div>
	);
}
