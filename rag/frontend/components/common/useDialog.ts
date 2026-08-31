"use client";

import { useEffect, useId, useRef } from "react";

const FOCUSABLE_SELECTOR =
	'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface UseDialogOptions {
	/** true mientras el diálogo está abierto. */
	open: boolean;
	/** Se invoca para cerrar (Escape). Nunca se llama mientras `closeBlocked` sea true. */
	onClose: () => void;
	/**
	 * Bloquea el cierre por Escape mientras una operación crítica está en
	 * curso (p. ej. un envío). El backdrop y el botón de cierre explícito de
	 * cada consumidor deben respetar el mismo valor por su cuenta.
	 */
	closeBlocked?: boolean;
	/** Enfocar este elemento al abrir, en vez del primer elemento focusable del panel. */
	initialFocusRef?: React.RefObject<HTMLElement | null>;
}

export interface UseDialogResult {
	/**
	 * Debe colocarse en el contenedor del panel (el elemento con
	 * role="dialog"). El consumidor debe darle también `tabIndex={-1}`: es
	 * el respaldo de foco cuando el panel no tiene ningún control habilitado
	 * (p. ej. durante un envío) y el objetivo al que este hook recupera el
	 * foco si, por cualquier razón, queda fuera del panel.
	 */
	panelRef: React.RefObject<HTMLDivElement | null>;
	/** Id único (vía `useId`) para `aria-labelledby` en el panel y `id` en el título visible. */
	titleId: string;
}

/**
 * Primitiva local compartida de comportamiento de diálogo modal.
 *
 * Cubre exactamente lo que hoy está duplicado (de forma parcial e
 * inconsistente) entre `AuthModal`, `FeedbackModal`, `MessageRatingPopover`,
 * `ConversationSearchDialog` y el modal administrativo de usuarios: atrapa
 * el foco dentro del panel (Tab/Shift+Tab), cierra con Escape, enfoca el
 * panel al abrir y devuelve el foco al elemento que lo disparó al cerrar.
 *
 * No impone marcado, estilos ni animación — cada consumidor conserva su
 * propio backdrop/panel/transición de Motion tal cual está hoy; solo debe
 * envolver su panel con `panelRef` (más `tabIndex={-1}`, ver arriba) y usar
 * `titleId` para `aria-labelledby` en el panel y como `id` del título
 * visible. El cierre por click en el backdrop y el botón de cierre
 * explícito quedan a cargo de cada consumidor (según si aplica
 * `closeOnBackdrop`/`dismissible` en ese caso), ya que su marcado ya varía
 * entre ellos.
 */
export function useDialog({
	open,
	onClose,
	closeBlocked = false,
	initialFocusRef,
}: UseDialogOptions): UseDialogResult {
	const titleId = useId();
	const panelRef = useRef<HTMLDivElement>(null);
	const triggerRef = useRef<Element | null>(null);

	// Foco inicial al abrir, y retorno del foco al disparador al cerrar (o al
	// desmontar mientras estaba abierto).
	useEffect(() => {
		if (!open) return;
		triggerRef.current = document.activeElement;
		const target =
			initialFocusRef?.current ??
			panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
			panelRef.current;
		target?.focus();
		return () => {
			if (triggerRef.current instanceof HTMLElement) {
				triggerRef.current.focus();
			}
		};
		// Solo debe re-ejecutarse cuando cambia `open`: `initialFocusRef` es una
		// ref estable y no debe disparar un nuevo ciclo de foco.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [open]);

	// Escape para cerrar, y Tab/Shift+Tab contenidos dentro del panel.
	useEffect(() => {
		if (!open) return;

		function handleKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape") {
				if (closeBlocked) return;
				event.preventDefault();
				onClose();
				return;
			}
			if (event.key !== "Tab") return;
			const panel = panelRef.current;
			if (!panel) return;
			const focusable = Array.from(
				panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
			);

			// Sin ningún control habilitado (p. ej. todo el formulario
			// deshabilitado durante un envío), no hay nada a lo que atrapar el
			// foco: se mantiene en el propio panel (que el consumidor vuelve
			// focuseable con `tabIndex={-1}`).
			if (focusable.length === 0) {
				event.preventDefault();
				panel.focus();
				return;
			}

			const first = focusable[0];
			const last = focusable[focusable.length - 1];
			const active = document.activeElement;

			// Si el foco quedó fuera del panel (por ejemplo, el control que
			// tenía el foco desapareció al cambiar de una rama de contenido a
			// otra dentro del mismo diálogo, como formulario → éxito, y el
			// navegador lo movió a `<body>`), Tab/Shift+Tab ya no encontraría
			// nunca `first`/`last` como `document.activeElement` y el atrapado
			// de foco se rompería en silencio. Se recupera explícitamente hacia
			// el primer o último control según la dirección.
			const focusIsInsidePanel = active instanceof Node && panel.contains(active);
			if (!focusIsInsidePanel) {
				event.preventDefault();
				(event.shiftKey ? last : first).focus();
				return;
			}

			if (event.shiftKey && active === first) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && active === last) {
				event.preventDefault();
				first.focus();
			}
		}

		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [open, closeBlocked, onClose]);

	return { panelRef, titleId };
}
