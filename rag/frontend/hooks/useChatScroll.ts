"use client";

import {
	type RefObject,
	useCallback,
	useEffect,
	useLayoutEffect,
	useRef,
	useState,
} from "react";

/** Distancia (px) al final a partir de la cual se ofrece "Ir al final". */
export const SCROLL_BUTTON_THRESHOLD = 160;
/** Margen (px) que se deja sobre la última pregunta al anclarla arriba. */
export const ANCHOR_OFFSET = 16;
/** Selector de las preguntas del usuario dentro del contenedor. */
export const USER_MESSAGE_SELECTOR = '[data-message-role="user"]';
/** Tolerancia (px) al comparar posiciones (el navegador redondea `scrollTop`). */
const OWN_SCROLL_TOLERANCE = 2;
/** Ventana (ms) tras rueda/teclado en la que un `scroll` cuenta como del usuario. */
const USER_INTENT_MS = 250;
/** Ventana (ms) de inercia tras soltar un gesto táctil. */
const TOUCH_MOMENTUM_MS = 1200;
/** Teclas que desplazan el contenedor cuando tiene el foco. */
const SCROLL_KEYS = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "]);

interface UseChatScrollOptions {
	/** Contenedor con `overflow-y: auto` (el `<main>` de la conversación). */
	containerRef: RefObject<HTMLElement | null>;
	/** Contenido que crece dentro del contenedor; se observa su tamaño. */
	contentRef: RefObject<HTMLElement | null>;
	/** Cambia cada vez que cambian los mensajes (dispara el seguimiento). */
	messages: unknown;
	/** `true` mientras se espera o se recibe una respuesta. */
	loading: boolean;
}

/**
 * Seguimiento del scroll de la conversación.
 *
 * Antes el chat llamaba a `scrollIntoView({ behavior: "smooth" })` en cada
 * fragmento recibido. El backend emite la respuesta completa en ráfaga
 * (trozos de 120 caracteres sin pausa), así que se encadenaban animaciones
 * de scroll suave mientras el contenido seguía creciendo. Los eventos
 * `scroll` intermedios de esas animaciones se interpretaban como si el
 * usuario se hubiera alejado del final: aparecía el botón "Ir al final"
 * encima del texto y del campo de escritura, y la vista saltaba al final de
 * una respuesta larga, dejando su comienzo fuera de pantalla.
 *
 * Ahora:
 * - Solo el usuario puede "despegar" la vista: cuentan solo los `scroll`
 *   precedidos de rueda, toque, teclado o arrastre de la barra. Los que
 *   provoca el hook, o el navegador al encogerse el contenido, se ignoran.
 * - Mientras la vista está "pegada", el destino es el final del contenido,
 *   pero nunca más abajo de la última pregunta anclada arriba: se ve la
 *   pregunta y el comienzo de la respuesta, y el lector baja a su ritmo.
 * - El tamaño del contenido se observa con `ResizeObserver`, así que el
 *   seguimiento también cubre fuentes, tablas o avisos que aparecen después.
 * - El botón "Ir al final" no aparece mientras llega una respuesta.
 */
export function useChatScroll({
	containerRef,
	contentRef,
	messages,
	loading,
}: UseChatScrollOptions) {
	const pinnedRef = useRef(true);
	// `true` cuando el lector eligió el final de todo (botón o scroll hasta
	// abajo): entonces se sigue el final, no la última pregunta.
	const followBottomRef = useRef(false);
	const [farFromBottom, setFarFromBottom] = useState(false);

	const targetTop = useCallback((container: HTMLElement) => {
		const bottom = Math.max(0, container.scrollHeight - container.clientHeight);
		if (followBottomRef.current) return bottom;
		const anchors = container.querySelectorAll<HTMLElement>(USER_MESSAGE_SELECTOR);
		const anchor = anchors[anchors.length - 1];
		if (!anchor) return bottom;
		const anchorTop =
			anchor.getBoundingClientRect().top -
			container.getBoundingClientRect().top +
			container.scrollTop -
			ANCHOR_OFFSET;
		return Math.max(0, Math.min(bottom, anchorTop));
	}, []);

	const updateButton = useCallback((container: HTMLElement) => {
		const distance =
			container.scrollHeight - container.scrollTop - container.clientHeight;
		setFarFromBottom(distance > SCROLL_BUTTON_THRESHOLD);
	}, []);

	const scrollTo = useCallback(
		(container: HTMLElement, top: number, smooth: boolean) => {
			if (Math.abs(container.scrollTop - top) <= OWN_SCROLL_TOLERANCE) return;
			if (smooth && typeof container.scrollTo === "function") {
				container.scrollTo({ top, behavior: "smooth" });
			} else {
				container.scrollTop = top;
			}
		},
		[],
	);

	const follow = useCallback(() => {
		const container = containerRef.current;
		if (!container) return;
		// El seguimiento automático solo baja, nunca sube: si el lector ya está
		// más abajo del destino (p. ej. pulsó "Ir al final"), se respeta.
		const target = targetTop(container);
		if (pinnedRef.current && target > container.scrollTop + OWN_SCROLL_TOLERANCE) {
			scrollTo(container, target, false);
		}
		updateButton(container);
	}, [containerRef, scrollTo, targetTop, updateButton]);

	// Eventos de scroll: solo los que provoca el usuario (rueda, toque,
	// teclado, arrastre de la barra) deciden si la vista sigue pegada. Los
	// demás —el propio seguimiento, el scroll suave del botón, o el ajuste que
	// hace el navegador cuando el contenido se encoge (p. ej. al desaparecer
	// el indicador de carga)— solo actualizan el botón.
	useEffect(() => {
		const container = containerRef.current;
		if (!container) return;
		let intentUntil = 0;
		let touching = false;
		let dragging = false;
		const markIntent = (ms: number) => {
			intentUntil = Math.max(intentUntil, Date.now() + ms);
		};
		const isUserScroll = () => touching || dragging || Date.now() < intentUntil;

		function handleScroll() {
			const el = container!;
			if (isUserScroll()) {
				const bottom = Math.max(0, el.scrollHeight - el.clientHeight);
				followBottomRef.current = el.scrollTop >= bottom - OWN_SCROLL_TOLERANCE;
				// Sigue pegada solo si el lector quedó en el destino o más abajo.
				pinnedRef.current = el.scrollTop >= targetTop(el) - OWN_SCROLL_TOLERANCE;
			}
			updateButton(el);
		}
		const onWheel = () => markIntent(USER_INTENT_MS);
		const onTouchStart = () => {
			touching = true;
		};
		const onTouchEnd = () => {
			touching = false;
			// La inercia del gesto sigue desplazando un rato después de soltar.
			markIntent(TOUCH_MOMENTUM_MS);
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (SCROLL_KEYS.has(event.key)) markIntent(USER_INTENT_MS * 4);
		};
		const onPointerDown = (event: PointerEvent) => {
			// Clic directo sobre el contenedor = barra de desplazamiento.
			if (event.target === container) dragging = true;
		};
		const onPointerUp = () => {
			if (dragging) markIntent(USER_INTENT_MS);
			dragging = false;
		};

		container.addEventListener("scroll", handleScroll, { passive: true });
		container.addEventListener("wheel", onWheel, { passive: true });
		container.addEventListener("touchstart", onTouchStart, { passive: true });
		container.addEventListener("touchend", onTouchEnd, { passive: true });
		container.addEventListener("touchcancel", onTouchEnd, { passive: true });
		container.addEventListener("keydown", onKeyDown);
		container.addEventListener("pointerdown", onPointerDown);
		window.addEventListener("pointerup", onPointerUp);
		return () => {
			container.removeEventListener("scroll", handleScroll);
			container.removeEventListener("wheel", onWheel);
			container.removeEventListener("touchstart", onTouchStart);
			container.removeEventListener("touchend", onTouchEnd);
			container.removeEventListener("touchcancel", onTouchEnd);
			container.removeEventListener("keydown", onKeyDown);
			container.removeEventListener("pointerdown", onPointerDown);
			window.removeEventListener("pointerup", onPointerUp);
		};
	}, [containerRef, targetTop, updateButton]);

	// Nuevos mensajes o cambio del estado de carga: seguir si está pegada.
	useLayoutEffect(() => {
		follow();
	}, [messages, loading, follow]);

	// Crecimiento del contenido que no pasa por `messages` (fuentes, tablas,
	// animaciones de entrada). El contenedor de contenido puede montarse
	// después (estado vacío → conversación), por eso depende de `messages`.
	useEffect(() => {
		const content = contentRef.current;
		if (!content || typeof ResizeObserver === "undefined") return;
		const observer = new ResizeObserver(() => follow());
		observer.observe(content);
		return () => observer.disconnect();
	}, [contentRef, follow, messages]);

	/** Llamar al enviar una pregunta: la vista vuelve a seguir la respuesta. */
	const pinToLatest = useCallback(() => {
		pinnedRef.current = true;
		followBottomRef.current = false;
		setFarFromBottom(false);
	}, []);

	/** Acción del botón "Ir al final". */
	const scrollToBottom = useCallback(() => {
		const container = containerRef.current;
		if (!container) return;
		// Al final de todo la vista queda pegada: si llega más contenido, lo sigue.
		pinnedRef.current = true;
		followBottomRef.current = true;
		setFarFromBottom(false);
		scrollTo(
			container,
			Math.max(0, container.scrollHeight - container.clientHeight),
			true,
		);
	}, [containerRef, scrollTo]);

	return {
		showScrollButton: farFromBottom && !loading,
		pinToLatest,
		scrollToBottom,
	};
}
