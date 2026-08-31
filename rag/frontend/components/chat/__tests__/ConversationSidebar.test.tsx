import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import type { Conversation } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
	useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const STABLE_USER = {
	user_id: "u1",
	email: "ana@example.com",
	display_name: "Ana",
	role: "user",
};

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER, role: "user", signOut: vi.fn() }),
}));

function baseProps(overrides: Record<string, unknown> = {}) {
	return {
		conversations: [] as Conversation[],
		activeConversationId: null,
		loading: false,
		isExpanded: true,
		mobileOpen: true,
		transitionEnabled: false,
		onSelectConversation: vi.fn().mockResolvedValue(undefined),
		onNewChat: vi.fn(),
		onToggleSidebar: vi.fn(),
		onCloseMobile: vi.fn(),
		onConversationsRefresh: vi.fn().mockResolvedValue(undefined),
		...overrides,
	};
}

/**
 * Reproduce la relación real con el componente padre (ChatInterface): un
 * botón externo visible y enfocable (el equivalente al botón de hamburguesa
 * de ChatHeader) controla `mobileOpen` de verdad, en vez de un mock estático
 * que deja ese valor congelado sin importar cuántas veces se invoque
 * `onCloseMobile`. Indispensable para probar la secuencia real de cierre del
 * panel/apertura de la búsqueda y el retorno de foco a ese botón externo.
 */
function ParentHarness({
	initialMobileOpen = false,
	...overrides
}: {
	initialMobileOpen?: boolean;
} & Record<string, unknown>) {
	const [mobileOpen, setMobileOpen] = useState(initialMobileOpen);
	return (
		<div>
			<button type="button" onClick={() => setMobileOpen(true)}>
				Abrir panel móvil
			</button>
			<ConversationSidebar
				{...baseProps({
					mobileOpen,
					onCloseMobile: () => setMobileOpen(false),
					...overrides,
				})}
			/>
		</div>
	);
}

describe("ConversationSidebar — secuencia entre la salida del panel móvil y la apertura de búsqueda", () => {
	it("abre la búsqueda solo después de que el panel móvil termina de salir, sin que coexistan como dos diálogos modales", async () => {
		const user = userEvent.setup();
		render(<ParentHarness />);

		await user.click(screen.getByRole("button", { name: "Abrir panel móvil" }));
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});

		await user.click(
			within(mobileDialog).getByRole("button", { name: "Buscar conversaciones" }),
		);

		// Justo después del click que solicita el cierre: la búsqueda todavía
		// no debe existir (su apertura queda pospuesta hasta que el panel
		// móvil confirme, vía `onExitComplete`, que ya terminó de salir).
		expect(
			screen.queryByRole("dialog", { name: "Buscar conversaciones" }),
		).not.toBeInTheDocument();

		// Se espera la animación de salida real (sin manipular el DOM a mano):
		// cuando el panel móvil termina de salir, la búsqueda se abre sola.
		await waitFor(() => {
			expect(
				screen.getByRole("dialog", { name: "Buscar conversaciones" }),
			).toBeInTheDocument();
		});

		// Y para ese momento el diálogo móvil ya no existe: en ningún punto
		// observable coexistieron dos elementos `role="dialog"
		// aria-modal="true"` activos a la vez.
		expect(
			screen.queryByRole("dialog", { name: "Historial de conversaciones" }),
		).not.toBeInTheDocument();
	});

	it("si el panel móvil se reabre antes de terminar de salir, la búsqueda pospuesta se cancela", async () => {
		const user = userEvent.setup();
		render(<ParentHarness />);

		const openButton = screen.getByRole("button", { name: "Abrir panel móvil" });
		await user.click(openButton);
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});

		// `fireEvent` (a diferencia de `userEvent`) despacha de forma
		// síncrona, sin ceder el control a la cola de temporizadores entre un
		// click y el siguiente: es necesario aquí para reabrir el panel
		// mientras la salida anterior sigue en curso, sin depender de cuánto
		// tarde en resolverse la animación real en este entorno.
		fireEvent.click(
			within(mobileDialog).getByRole("button", { name: "Buscar conversaciones" }),
		);
		fireEvent.click(openButton);

		// Aunque se espere más tiempo del que dura la animación de salida, la
		// búsqueda pospuesta ya no debe abrirse: quedó cancelada.
		await new Promise((resolve) => setTimeout(resolve, 500));
		expect(
			screen.queryByRole("dialog", { name: "Buscar conversaciones" }),
		).not.toBeInTheDocument();
		expect(
			screen.getByRole("dialog", { name: "Historial de conversaciones" }),
		).toBeInTheDocument();
	});

	it("Tab y Shift+Tab permanecen dentro del diálogo de búsqueda abierto desde móvil", async () => {
		const user = userEvent.setup();
		render(
			<ParentHarness
				conversations={[
					{
						id: "c1",
						threadId: "t1",
						title: "Conversación 1",
						createdAt: new Date(),
						updatedAt: new Date(),
						messageCount: 1,
					} as Conversation,
				]}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Abrir panel móvil" }));
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});
		await user.click(
			within(mobileDialog).getByRole("button", { name: "Buscar conversaciones" }),
		);

		const searchDialog = await screen.findByRole("dialog", {
			name: "Buscar conversaciones",
		});
		const focusable = within(searchDialog).getAllByRole("button");
		expect(focusable.length).toBeGreaterThan(0);

		// El campo de búsqueda recibe el foco inicial (initialFocusRef).
		const searchInput = within(searchDialog).getByPlaceholderText(
			"Buscar conversaciones…",
		);
		expect(searchInput).toHaveFocus();

		// Shift+Tab desde el primer elemento enfocable envuelve al último,
		// sin escaparse del panel (contrato genérico ya cubierto por
		// useDialog.test.tsx; aquí se confirma en este flujo concreto).
		await user.tab({ shift: true });
		expect(searchDialog.contains(document.activeElement)).toBe(true);
	});

	it("seleccionar un resultado desde la búsqueda abierta vía móvil sigue funcionando", async () => {
		const user = userEvent.setup();
		const onSelectConversation = vi.fn().mockResolvedValue(undefined);
		const conv = {
			id: "c1",
			threadId: "t1",
			title: "Conversación de prueba",
			createdAt: new Date(),
			updatedAt: new Date(),
			messageCount: 1,
		} as Conversation;
		render(
			<ParentHarness
				conversations={[conv]}
				onSelectConversation={onSelectConversation}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Abrir panel móvil" }));
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});
		await user.click(
			within(mobileDialog).getByRole("button", { name: "Buscar conversaciones" }),
		);

		const searchDialog = await screen.findByRole("dialog", {
			name: "Buscar conversaciones",
		});
		await user.click(within(searchDialog).getByText("Conversación de prueba"));

		expect(onSelectConversation).toHaveBeenCalledWith(conv);
	});

	it("desde escritorio, abrir la búsqueda no cierra ni altera el panel móvil (que ya estaba cerrado)", async () => {
		const user = userEvent.setup();
		render(<ParentHarness initialMobileOpen={false} />);

		expect(
			screen.queryByRole("dialog", { name: "Historial de conversaciones" }),
		).not.toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "Buscar conversaciones" }));

		// mobileOpen ya era `false`: la búsqueda se abre de inmediato, sin
		// pasar por el circuito de espera del panel móvil.
		expect(
			screen.getByRole("dialog", { name: "Buscar conversaciones" }),
		).toBeInTheDocument();
	});
});

describe("ConversationSidebar — contrato de foco al abrir búsqueda desde móvil", () => {
	it("al cerrar la búsqueda abierta desde móvil, el foco vuelve exactamente al botón externo que abrió el panel (no a document.body ni a un nodo desconectado)", async () => {
		const user = userEvent.setup();
		render(<ParentHarness />);

		const openButton = screen.getByRole("button", { name: "Abrir panel móvil" });
		await user.click(openButton);
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});
		await user.click(
			within(mobileDialog).getByRole("button", { name: "Buscar conversaciones" }),
		);

		const searchDialog = await screen.findByRole("dialog", {
			name: "Buscar conversaciones",
		});
		// Foco inicial: el campo de búsqueda (initialFocusRef), no el propio
		// panel ni el primer botón focuseable.
		expect(within(searchDialog).getByPlaceholderText("Buscar conversaciones…")).toHaveFocus();

		await user.keyboard("{Escape}");

		// El foco debe quedar exactamente en el botón externo, visible y
		// conectado que originalmente abrió el panel móvil — no en
		// `document.body` (que no es un resultado válido de restauración) ni
		// en ningún nodo desconectado del documento.
		expect(document.activeElement).toBe(openButton);
		expect(openButton.isConnected).toBe(true);
	});
});

describe("ConversationSidebar — el fondo permanece bloqueado mientras el panel móvil sigue visible saliendo", () => {
	it("justo después de pedir el cierre, con el diálogo todavía montado, el backdrop sigue presente y el foco no puede escapar del panel; recién tras onExitComplete desaparecen panel y backdrop juntos y el foco vuelve al botón externo", async () => {
		const user = userEvent.setup();
		render(<ParentHarness />);

		const openButton = screen.getByRole("button", { name: "Abrir panel móvil" });
		await user.click(openButton);
		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});
		const backdrop = () => document.querySelector(".fixed.inset-0.z-30");
		expect(backdrop()).toBeInTheDocument();

		// Se pide el cierre por la misma ruta que backdrop/botón "×": Escape,
		// vía `useDialog`. Disparado con `fireEvent` (síncrono) para observar
		// el DOM en el instante exacto posterior a la solicitud, sin darle
		// tiempo real a la animación de salida para avanzar.
		fireEvent.keyDown(document, { key: "Escape" });

		// El diálogo sigue montado (la salida real toma su tiempo) y,
		// mientras sea así, el backdrop no debe haber desaparecido.
		expect(
			screen.getByRole("dialog", { name: "Historial de conversaciones" }),
		).toBe(mobileDialog);
		expect(backdrop()).toBeInTheDocument();

		// El foco sigue contenido dentro del panel: Tab no debe poder
		// escapar hacia el fondo (en el problema original, el `inert` y el
		// backdrop ya se habían retirado en este mismo instante).
		expect(mobileDialog.contains(document.activeElement)).toBe(true);
		fireEvent.keyDown(document, { key: "Tab" });
		expect(mobileDialog.contains(document.activeElement)).toBe(true);

		// Se espera la salida real (sin manipular el DOM a mano). Recién
		// ahí desaparecen panel y backdrop juntos, y el foco vuelve
		// exactamente al botón externo, visible y conectado, que abrió el
		// panel — nunca antes.
		await waitFor(() => {
			expect(
				screen.queryByRole("dialog", { name: "Historial de conversaciones" }),
			).not.toBeInTheDocument();
		});
		expect(backdrop()).not.toBeInTheDocument();
		expect(document.activeElement).toBe(openButton);
		expect(openButton.isConnected).toBe(true);
	});
});

describe("ConversationSidebar — panel móvil, menú de perfil anidado", () => {
	it("con el menú de perfil abierto desde el panel móvil, Escape cierra primero el menú, no el panel completo", async () => {
		const user = userEvent.setup();
		const onCloseMobile = vi.fn();
		render(<ConversationSidebar {...baseProps({ onCloseMobile })} />);

		const mobileDialog = screen.getByRole("dialog", {
			name: "Historial de conversaciones",
		});
		const profileTrigger = within(mobileDialog).getByRole("button", {
			name: "Abrir menú de perfil",
		});
		await user.click(profileTrigger);
		expect(profileTrigger).toHaveAttribute("aria-expanded", "true");

		// Primer Escape: solo debe cerrar el menú de perfil (su propio
		// listener, independiente de useDialog — ver SidebarUserMenu). Se
		// comprueba vía `aria-expanded` (una prop de React síncrona) en vez
		// de esperar a que el popover termine su animación de salida
		// (AnimatePresence/motion, sin temporización real en jsdom).
		await user.keyboard("{Escape}");
		expect(profileTrigger).toHaveAttribute("aria-expanded", "false");
		expect(onCloseMobile).not.toHaveBeenCalled();
		expect(
			screen.getByRole("dialog", { name: "Historial de conversaciones" }),
		).toBeInTheDocument();

		// Segundo Escape: ahora sí cierra el panel.
		await user.keyboard("{Escape}");
		expect(onCloseMobile).toHaveBeenCalledTimes(1);
	});

	it("sin overlays anidados abiertos, Escape sigue cerrando el panel móvil normalmente", async () => {
		const user = userEvent.setup();
		const onCloseMobile = vi.fn();
		render(<ConversationSidebar {...baseProps({ onCloseMobile })} />);

		expect(
			screen.getByRole("dialog", { name: "Historial de conversaciones" }),
		).toBeInTheDocument();

		await user.keyboard("{Escape}");
		expect(onCloseMobile).toHaveBeenCalledTimes(1);
	});
});
