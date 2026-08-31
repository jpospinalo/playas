import { useRef, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useDialog } from "@/components/common/useDialog";

/**
 * Arnés de prueba que reproduce cómo lo usan los consumidores reales
 * (AuthModal, FeedbackModal, MessageRatingPopover, ConversationSearchDialog,
 * el modal administrativo de usuarios y `MobileSidebar`): un disparador
 * externo que abre el panel, y el panel mismo montado
 * condicionalmente sobre `open` (nunca oculto con CSS), tal como exige el
 * hook para que `panelRef.current` exista al momento de enfocar.
 */
function Harness({
	closeBlocked = false,
	useInitialFocusRef = false,
}: {
	closeBlocked?: boolean;
	useInitialFocusRef?: boolean;
}) {
	const [open, setOpen] = useState(false);
	const specialRef = useRef<HTMLButtonElement>(null);
	const { panelRef, titleId } = useDialog({
		open,
		onClose: () => setOpen(false),
		closeBlocked,
		initialFocusRef: useInitialFocusRef ? specialRef : undefined,
	});

	return (
		<div>
			<button type="button" onClick={() => setOpen(true)}>
				Abrir
			</button>
			{open && (
				<div ref={panelRef} tabIndex={-1} role="dialog" aria-labelledby={titleId}>
					<h2 id={titleId}>Diálogo de prueba</h2>
					<button type="button">Primero</button>
					{useInitialFocusRef && (
						<button type="button" ref={specialRef}>
							Especial
						</button>
					)}
					<button type="button">Segundo</button>
					<button type="button">Último</button>
				</div>
			)}
		</div>
	);
}

/** Panel sin ningún control habilitado (todo deshabilitado, como durante
 *  un envío en curso). */
function NoFocusableHarness() {
	const [open, setOpen] = useState(false);
	const { panelRef, titleId } = useDialog({ open, onClose: () => setOpen(false) });

	return (
		<div>
			<button type="button" onClick={() => setOpen(true)}>
				Abrir
			</button>
			{open && (
				<div ref={panelRef} tabIndex={-1} role="dialog" aria-labelledby={titleId}>
					<h2 id={titleId}>Diálogo sin controles habilitados</h2>
					<button type="button" disabled>
						Deshabilitado
					</button>
				</div>
			)}
		</div>
	);
}

/** El control enfocado desaparece al pasar de una rama de contenido a
 *  otra dentro del mismo diálogo (formulario → éxito), tal como ocurre
 *  en FeedbackModal/MessageRatingPopover. */
function TransitionHarness() {
	const [open, setOpen] = useState(false);
	const [phase, setPhase] = useState<"form" | "success">("form");
	const { panelRef, titleId } = useDialog({ open, onClose: () => setOpen(false) });

	return (
		<div>
			<button
				type="button"
				onClick={() => {
					setPhase("form");
					setOpen(true);
				}}
			>
				Abrir
			</button>
			{open && (
				<div ref={panelRef} tabIndex={-1} role="dialog" aria-labelledby={titleId}>
					<h2 id={titleId}>Diálogo con transición</h2>
					{phase === "form" ? (
						// `key` distinto por fase: fuerza a React a desmontar este
						// subárbol entero (en vez de reconciliar "Enviar" con
						// "Reintentar" en la misma posición y conservar el nodo
						// enfocado con una etiqueta nueva) — así se reproduce
						// fielmente que el control enfocado desaparece de verdad,
						// igual que en FeedbackModal/MessageRatingPopover con su
						// `AnimatePresence mode="wait"` por fase.
						<div key="form">
							<button type="button">Primero</button>
							<button type="button" onClick={() => setPhase("success")}>
								Enviar
							</button>
						</div>
					) : (
						<div key="success">
							<button type="button">Reintentar</button>
							<button type="button">Cerrar</button>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

describe("useDialog — primitiva local de diálogo", () => {
	it("al abrir sin initialFocusRef, el foco entra al primer elemento focusable del panel", async () => {
		const user = userEvent.setup();
		render(<Harness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));

		expect(screen.getByRole("button", { name: "Primero" })).toHaveFocus();
	});

	it("con initialFocusRef, el foco entra a ese elemento en vez del primero", async () => {
		const user = userEvent.setup();
		render(<Harness useInitialFocusRef />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));

		expect(screen.getByRole("button", { name: "Especial" })).toHaveFocus();
		expect(screen.getByRole("button", { name: "Primero" })).not.toHaveFocus();
	});

	it("Tab en el último elemento focusable vuelve al primero (trampa de foco)", async () => {
		const user = userEvent.setup();
		render(<Harness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));
		expect(screen.getByRole("button", { name: "Primero" })).toHaveFocus();

		await user.tab(); // Primero -> Segundo (orden normal, sin intervención del hook)
		expect(screen.getByRole("button", { name: "Segundo" })).toHaveFocus();

		await user.tab(); // Segundo -> Último
		expect(screen.getByRole("button", { name: "Último" })).toHaveFocus();

		await user.tab(); // Último -> vuelve a Primero (trampa)
		expect(screen.getByRole("button", { name: "Primero" })).toHaveFocus();
	});

	it("Shift+Tab en el primero va al último (trampa de foco en reversa)", async () => {
		const user = userEvent.setup();
		render(<Harness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));
		expect(screen.getByRole("button", { name: "Primero" })).toHaveFocus();

		await user.tab({ shift: true });
		expect(screen.getByRole("button", { name: "Último" })).toHaveFocus();
	});

	it("Escape cierra el diálogo y devuelve el foco al botón que lo abrió", async () => {
		const user = userEvent.setup();
		render(<Harness />);

		const trigger = screen.getByRole("button", { name: "Abrir" });
		await user.click(trigger);
		expect(screen.getByRole("dialog")).toBeInTheDocument();

		await user.keyboard("{Escape}");

		expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
		expect(trigger).toHaveFocus();
	});

	it("closeBlocked=true: Escape no cierra el diálogo", async () => {
		const user = userEvent.setup();
		render(<Harness closeBlocked />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));
		expect(screen.getByRole("dialog")).toBeInTheDocument();

		await user.keyboard("{Escape}");

		expect(screen.getByRole("dialog")).toBeInTheDocument();
	});

	it("sin controles habilitados, el foco inicial y Tab se quedan en el propio panel", async () => {
		const user = userEvent.setup();
		render(<NoFocusableHarness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));

		const panel = screen.getByRole("dialog");
		expect(panel).toHaveFocus();

		await user.tab();
		expect(panel).toHaveFocus();
	});

	it("si el control enfocado desaparece y el foco queda fuera del panel, Tab lo recupera hacia el primer control vigente", async () => {
		const user = userEvent.setup();
		render(<TransitionHarness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));
		await user.click(screen.getByRole("button", { name: "Enviar" }));

		// "Enviar" (que tenía el foco al hacer click) desapareció al cambiar de
		// fase; el navegador (y jsdom) mueven el foco a <body> cuando el
		// elemento enfocado se retira del documento — sin recuperación
		// explícita, el siguiente Tab escaparía del diálogo desde ahí.
		expect(screen.queryByRole("button", { name: "Enviar" })).not.toBeInTheDocument();
		expect(document.activeElement).toBe(document.body);

		// Se dispara el evento directamente (en vez de `user.tab()`) porque el
		// atrapado de foco de este hook es quien decide el destino — no el
		// orden de tabulación nativo simulado por userEvent — y partir de
		// `document.body` (sin una posición previa rastreable) puede hacer que
		// esa simulación no coincida con la dirección solicitada.
		fireEvent.keyDown(document, { key: "Tab", code: "Tab" });
		expect(screen.getByRole("button", { name: "Reintentar" })).toHaveFocus();
	});

	it("el mismo escenario con Shift+Tab recupera el foco hacia el último control vigente", async () => {
		const user = userEvent.setup();
		render(<TransitionHarness />);

		await user.click(screen.getByRole("button", { name: "Abrir" }));
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		expect(document.activeElement).toBe(document.body);

		fireEvent.keyDown(document, { key: "Tab", code: "Tab", shiftKey: true });
		expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus();
	});
});
