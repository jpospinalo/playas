import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatInterface } from "@/components/chat/ChatInterface";

const STABLE_USER = {
	user_id: "u1",
	email: "user@example.com",
	display_name: null,
	role: "user",
};

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER, loading: false }),
}));

vi.mock("@/hooks/useConversations", () => ({
	useConversations: () => ({
		conversations: [],
		loading: false,
		error: null,
		refresh: vi.fn(),
	}),
}));

const loadConversationMock = vi.fn();
const useChatMock = vi.fn();
vi.mock("@/hooks/useChat", () => ({
	useChat: (...args: unknown[]) => useChatMock(...args),
}));

// Se sustituye ConversationSidebar por un doble mínimo: lo que interesa
// verificar aquí es el ESTADO que ChatInterface le pasa (`mobileOpen`) y
// CUÁNDO invoca cada callback, no el marcado interno del sidebar real
// (ya cubierto, en lo que le corresponde, por su propio comportamiento
// de `useDialog`/`closeBlocked`).
vi.mock("@/components/chat/ConversationSidebar", () => ({
	ConversationSidebar: (props: {
		mobileOpen: boolean;
		onSelectConversation: (conv: { id: string; threadId: string; title: string; createdAt: Date; updatedAt: Date; messageCount: number }) => Promise<void>;
		// Opcional en el componente real (ver ConversationSidebarProps): el
		// doble solo la expone como botón cuando el test la necesita, para
		// simular —sin el `AnimatePresence` real— el momento exacto en que
		// el panel móvil real confirmaría que terminó de salir.
		onMobileExitComplete?: () => void;
	}) => (
		<div data-testid="mock-sidebar" data-mobile-open={String(props.mobileOpen)}>
			<button
				type="button"
				onClick={() =>
					props.onSelectConversation({
						id: "conv-1",
						threadId: "thread-1",
						title: "Conversación",
						createdAt: new Date(),
						updatedAt: new Date(),
						messageCount: 2,
					})
				}
			>
				Seleccionar conversación
			</button>
			{props.onMobileExitComplete && (
				<button type="button" onClick={props.onMobileExitComplete}>
					Simular fin de animación de salida
				</button>
			)}
		</div>
	),
}));

vi.mock("@/components/chat/EmptyState", () => ({
	EmptyState: () => <div data-testid="mock-empty-state" />,
}));

vi.mock("@/components/chat/ChatHeader", () => ({
	ChatHeader: (props: { onToggleSidebar: () => void }) => (
		<button type="button" onClick={props.onToggleSidebar}>
			Abrir sidebar
		</button>
	),
}));

function baseChatReturn(overrides: Partial<ReturnType<typeof makeChatReturn>> = {}) {
	return makeChatReturn(overrides);
}

function makeChatReturn(overrides: Record<string, unknown> = {}) {
	return {
		messages: [],
		input: "",
		loading: false,
		isStreaming: false,
		// Se anota explícitamente como `string | null` (no solo `null`) para
		// que `Partial<ReturnType<typeof makeChatReturn>>` acepte los valores
		// de texto que los tests de esta sección pasan en `overrides`.
		stageMessage: null as string | null,
		error: null,
		contextPercent: 0,
		conversationId: null,
		ratedMessageIds: new Set<string>(),
		persistingMessageIds: new Set<string>(),
		canCancel: false,
		generationStopped: false,
		generationFinished: false,
		setInput: vi.fn(),
		submit: vi.fn(),
		resetChat: vi.fn(),
		loadConversation: loadConversationMock,
		retryPersistMessage: vi.fn(),
		cancel: vi.fn(),
		rateMessage: vi.fn(),
		...overrides,
	};
}

/** Doble mínimo y controlable de `MediaQueryList`. */
function makeMatchMediaMock() {
	let matches = false;
	let changeListener: ((event: { matches: boolean }) => void) | null = null;
	const mql = {
		get matches() {
			return matches;
		},
		addEventListener: (_type: string, listener: (event: { matches: boolean }) => void) => {
			changeListener = listener;
		},
		removeEventListener: () => {
			changeListener = null;
		},
	};
	return {
		matchMediaFn: () => mql,
		setMatches(next: boolean) {
			matches = next;
		},
		fireChange(next: boolean) {
			matches = next;
			changeListener?.({ matches: next });
		},
	};
}

describe("ChatInterface — panel móvil", () => {
	beforeEach(() => {
		loadConversationMock.mockReset();
		useChatMock.mockReset();
		useChatMock.mockReturnValue(baseChatReturn());
	});

	it("cerrar automáticamente el panel móvil si el viewport deja de ser móvil (matchMedia change)", async () => {
		const user = userEvent.setup();
		const { matchMediaFn, fireChange } = makeMatchMediaMock();
		vi.stubGlobal("matchMedia", vi.fn(() => matchMediaFn()));

		render(<ChatInterface />);

		// Abre el panel móvil (el mock de matchMedia().matches empieza en
		// `false`, que es justo el valor que `toggleSidebar` consulta
		// SINCRÓNICAMENTE con su propia llamada a `window.matchMedia` — para
		// esta prueba se fuerza `matches: true` antes del click, simulando
		// que el usuario ya está en un viewport móvil).
		vi.stubGlobal(
			"matchMedia",
			vi.fn(() => {
				const m = matchMediaFn();
				Object.defineProperty(m, "matches", { get: () => true });
				return m;
			}),
		);
		await user.click(screen.getByRole("button", { name: "Abrir sidebar" }));

		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute(
			"data-mobile-open",
			"true",
		);

		// El viewport cruza a escritorio: el listener de `change` registrado
		// por el efecto de auto-cierre debe cerrar el panel automáticamente.
		act(() => {
			fireChange(false);
		});

		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute(
			"data-mobile-open",
			"false",
		);

		vi.unstubAllGlobals();
	});

	it("seleccionar una conversación cierra el panel móvil de inmediato, sin esperar a que termine loadConversation", async () => {
		const user = userEvent.setup();
		let resolveLoad: () => void = () => {};
		loadConversationMock.mockImplementation(
			() =>
				new Promise<void>((resolve) => {
					resolveLoad = resolve;
				}),
		);

		vi.stubGlobal(
			"matchMedia",
			vi.fn(() => {
				const m = { matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() };
				return m;
			}),
		);

		render(<ChatInterface />);

		await user.click(screen.getByRole("button", { name: "Abrir sidebar" }));
		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute(
			"data-mobile-open",
			"true",
		);

		await user.click(screen.getByRole("button", { name: "Seleccionar conversación" }));

		// El panel ya debe estar cerrado aunque `loadConversation` sigue sin
		// resolverse.
		expect(loadConversationMock).toHaveBeenCalledTimes(1);
		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute(
			"data-mobile-open",
			"false",
		);

		await act(async () => {
			resolveLoad();
			await Promise.resolve();
		});

		vi.unstubAllGlobals();
	});
});

describe("ChatInterface — inert del área principal durante el cierre del panel móvil", () => {
	beforeEach(() => {
		loadConversationMock.mockReset();
		useChatMock.mockReset();
		useChatMock.mockReturnValue(baseChatReturn());
	});

	function mainContent() {
		return document.querySelector(".flex.flex-1.flex-col.overflow-hidden");
	}

	it("inert se activa al abrir el panel móvil, sigue activo justo después de pedir el cierre, y solo se libera cuando el sidebar confirma (onMobileExitComplete) que la animación de salida terminó", async () => {
		const user = userEvent.setup();
		vi.stubGlobal(
			"matchMedia",
			vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
		);

		render(<ChatInterface />);
		expect(mainContent()).not.toHaveAttribute("inert");

		await user.click(screen.getByRole("button", { name: "Abrir sidebar" }));
		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute("data-mobile-open", "true");
		expect(mainContent()).toHaveAttribute("inert");

		// Se pide el cierre (el mismo botón alterna mobileOpen): el sidebar
		// mock ya reporta `mobileOpen=false`, pero el panel móvil real
		// seguiría todavía montado, animando su salida — el `inert` NO debe
		// soltarse en este instante (el problema original lo soltaba aquí
		// mismo, prematuramente).
		await user.click(screen.getByRole("button", { name: "Abrir sidebar" }));
		expect(screen.getByTestId("mock-sidebar")).toHaveAttribute("data-mobile-open", "false");
		expect(mainContent()).toHaveAttribute("inert");

		// Recién cuando el sidebar real confirmaría el fin de la animación
		// de salida (simulado aquí invocando `onMobileExitComplete`, ya que
		// el doble no anima) se libera el `inert`.
		await user.click(screen.getByRole("button", { name: "Simular fin de animación de salida" }));
		expect(mainContent()).not.toHaveAttribute("inert");

		vi.unstubAllGlobals();
	});
});

describe("ChatInterface — región de progreso: prioridad de generationFinished sobre loading", () => {
	beforeEach(() => {
		loadConversationMock.mockReset();
		useChatMock.mockReset();
		// ChatInterface siempre suscribe un listener de matchMedia (efecto de
		// auto-cierre del panel móvil); sin este doble mínimo, cualquier
		// render fallaría con `window.matchMedia is not a function` en jsdom.
		vi.stubGlobal("matchMedia", vi.fn(() => makeMatchMediaMock().matchMediaFn()));
		// jsdom no implementa scrollIntoView; el efecto de auto-scroll de
		// ChatInterface lo llama en cada cambio de `loading`.
		Element.prototype.scrollIntoView = vi.fn();
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("antes del primer evento de estado del servidor, anuncia 'Procesando consulta…' en vez de quedar vacía", () => {
		useChatMock.mockReturnValue(
			baseChatReturn({ loading: true, isStreaming: false, stageMessage: null }),
		);
		render(<ChatInterface />);

		expect(document.querySelector('[role="status"]')?.textContent).toBe(
			"Procesando consulta…",
		);
	});

	it("con un stageMessage del servidor, lo muestra tal cual (sin el valor por defecto)", () => {
		useChatMock.mockReturnValue(
			baseChatReturn({
				loading: true,
				isStreaming: false,
				stageMessage: "Buscando fuentes jurídicas relevantes…",
			}),
		);
		render(<ChatInterface />);

		expect(document.querySelector('[role="status"]')?.textContent).toBe(
			"Buscando fuentes jurídicas relevantes…",
		);
	});

	it("mientras llegan tokens, anuncia 'Generando respuesta…'", () => {
		useChatMock.mockReturnValue(
			baseChatReturn({ loading: true, isStreaming: true }),
		);
		render(<ChatInterface />);

		expect(document.querySelector('[role="status"]')?.textContent).toBe(
			"Generando respuesta…",
		);
	});

	it("generationFinished tiene prioridad sobre loading — anuncia el final aunque loading siga en true (persistencia en curso)", () => {
		useChatMock.mockReturnValue(
			baseChatReturn({
				// Exactamente el estado real durante la persistencia posterior al
				// streaming: loading todavía true, isStreaming ya no importa,
				// generationFinished ya true (ver useChat.submit()).
				loading: true,
				isStreaming: false,
				stageMessage: "Buscando fuentes jurídicas relevantes…",
				generationFinished: true,
			}),
		);
		render(<ChatInterface />);

		expect(document.querySelector('[role="status"]')?.textContent).toBe(
			"Respuesta finalizada.",
		);
	});

	it("sin carga ni generación finalizada (estado ocioso), la región de progreso queda vacía", () => {
		useChatMock.mockReturnValue(
			baseChatReturn({ loading: false, generationFinished: false }),
		);
		render(<ChatInterface />);

		expect(document.querySelector('[role="status"]')?.textContent).toBe("");
	});

	it("la región de progreso expone aria-live=\"polite\" y aria-atomic=\"true\"", () => {
		useChatMock.mockReturnValue(baseChatReturn({ loading: true, isStreaming: true }));
		render(<ChatInterface />);

		const region = document.querySelector('[role="status"]');
		expect(region).toHaveAttribute("aria-live", "polite");
		expect(region).toHaveAttribute("aria-atomic", "true");
	});
});
