import { act, render } from "@testing-library/react";
import { useEffect, useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { ANCHOR_OFFSET, useChatScroll } from "@/hooks/useChatScroll";

/**
 * jsdom no hace layout: se simula un contenedor con scroll fijando
 * `clientHeight`/`scrollHeight` y la posición de la última pregunta.
 */
interface Layout {
	clientHeight: number;
	scrollHeight: number;
	/** Posición de la última pregunta dentro del contenido (px desde arriba). */
	anchorTop: number | null;
}

type ScrollApi = ReturnType<typeof useChatScroll>;
let api: ScrollApi;
const exposeApi = (value: ScrollApi) => {
	api = value;
};

function Harness({ layout, messages, loading }: { layout: Layout; messages: number; loading: boolean }) {
	const containerRef = useRef<HTMLElement | null>(null);
	const contentRef = useRef<HTMLDivElement>(null);

	const setContainer = (el: HTMLElement | null) => {
		containerRef.current = el;
		if (!el) return;
		Object.defineProperty(el, "clientHeight", { configurable: true, get: () => layout.clientHeight });
		Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => layout.scrollHeight });
		el.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;
	};

	const scroll = useChatScroll({ containerRef, contentRef, messages, loading });
	useEffect(() => exposeApi(scroll));

	return (
		<main ref={setContainer} data-testid="container">
			<div ref={contentRef}>
				{layout.anchorTop !== null && (
					<div
						data-message-role="user"
						ref={(el) => {
							if (!el) return;
							// Posición relativa al viewport del contenedor = posición en el
							// contenido menos lo ya desplazado.
							el.getBoundingClientRect = () =>
								({ top: layout.anchorTop! - (containerRef.current?.scrollTop ?? 0) }) as DOMRect;
						}}
					/>
				)}
			</div>
		</main>
	);
}

function setup(initial: Layout, loading = false) {
	const layout = { ...initial };
	let messages = 1;
	let isLoading = loading;
	const utils = render(<Harness layout={layout} messages={messages} loading={isLoading} />);
	const container = utils.getByTestId("container");
	const rerender = (patch: Partial<Layout> = {}, nextLoading = isLoading) => {
		Object.assign(layout, patch);
		messages += 1;
		isLoading = nextLoading;
		utils.rerender(<Harness layout={layout} messages={messages} loading={isLoading} />);
	};
	/** Simula un scroll del usuario: rueda del mouse y luego el `scroll`. */
	const userScroll = (top: number) => {
		act(() => {
			container.dispatchEvent(new Event("wheel"));
			container.scrollTop = top;
			container.dispatchEvent(new Event("scroll"));
		});
	};
	/** Simula un `scroll` que no provocó el usuario (p. ej. ajuste del navegador). */
	const browserScroll = (top: number) => {
		act(() => {
			container.scrollTop = top;
			container.dispatchEvent(new Event("scroll"));
		});
	};
	return { container, rerender, userScroll, browserScroll };
}

describe("useChatScroll", () => {
	it("sigue el final mientras el contenido cabe bajo la última pregunta", () => {
		const { container, rerender } = setup({ clientHeight: 500, scrollHeight: 500, anchorTop: 300 }, true);
		rerender({ scrollHeight: 700 });
		// destino = min(final 200, pregunta 300-16) = 200
		expect(container.scrollTop).toBe(200);
	});

	it("no baja más allá de la última pregunta: el comienzo de una respuesta larga queda visible", () => {
		const { container, rerender } = setup({ clientHeight: 500, scrollHeight: 600, anchorTop: 400 }, true);
		// Llega la respuesta completa de golpe (como en prod): el contenido crece 2000px.
		rerender({ scrollHeight: 2600 });
		expect(container.scrollTop).toBe(400 - ANCHOR_OFFSET);
	});

	it("su propio scroll no muestra el botón 'Ir al final' ni despega la vista (el bug)", () => {
		const { container, rerender } = setup({ clientHeight: 500, scrollHeight: 600, anchorTop: 100 }, true);
		rerender({ scrollHeight: 650 });
		act(() => {
			// El navegador emite el evento del scroll que hizo el hook.
			container.dispatchEvent(new Event("scroll"));
		});
		expect(api.showScrollButton).toBe(false);
		rerender({ scrollHeight: 700 });
		// Sigue pegada: vuelve a bajar al nuevo final.
		expect(container.scrollTop).toBe(84);
	});

	it("un scroll sin intención del usuario (el navegador ajusta al encoger el contenido) no cambia el modo", () => {
		// Caso visto en celular: al desaparecer el indicador de carga el navegador
		// recorta scrollTop al nuevo final. Antes eso se tomaba como "el usuario
		// bajó al final" y la respuesta siguiente saltaba hasta su última línea.
		const { container, rerender, browserScroll } = setup({ clientHeight: 500, scrollHeight: 900, anchorTop: 800 }, true);
		expect(container.scrollTop).toBe(400);
		rerender({ scrollHeight: 880 });
		browserScroll(380);
		rerender({ scrollHeight: 3000 });
		expect(container.scrollTop).toBe(800 - ANCHOR_OFFSET);
	});

	it("nunca muestra el botón mientras llega una respuesta", () => {
		const { rerender, userScroll } = setup({ clientHeight: 500, scrollHeight: 3000, anchorTop: 2000 }, true);
		userScroll(0);
		rerender({}, true);
		expect(api.showScrollButton).toBe(false);
		rerender({}, false);
		expect(api.showScrollButton).toBe(true);
	});

	it("si el usuario sube a leer, no lo mueve aunque llegue más contenido", () => {
		const { container, rerender, userScroll } = setup({ clientHeight: 500, scrollHeight: 1200, anchorTop: 1000 }, true);
		userScroll(100);
		rerender({ scrollHeight: 1800 });
		expect(container.scrollTop).toBe(100);
	});

	it("al enviar una pregunta nueva vuelve a seguir", () => {
		const { container, rerender, userScroll } = setup({ clientHeight: 500, scrollHeight: 1200, anchorTop: 600 }, false);
		userScroll(0);
		act(() => api.pinToLatest());
		rerender({ scrollHeight: 1400, anchorTop: 1300 }, true);
		expect(container.scrollTop).toBe(900); // final = 1400-500
	});

	it("'Ir al final' baja al final y el seguimiento no vuelve a subir a la pregunta", () => {
		const { container, rerender } = setup({ clientHeight: 500, scrollHeight: 600, anchorTop: 400 }, false);
		rerender({ scrollHeight: 2600 }, false);
		expect(container.scrollTop).toBe(384);
		container.scrollTo = vi.fn((opts?: ScrollToOptions | number) => {
			if (typeof opts === "object" && opts?.top !== undefined) container.scrollTop = opts.top;
		}) as typeof container.scrollTo;
		act(() => api.scrollToBottom());
		expect(container.scrollTop).toBe(2100);
		rerender({ scrollHeight: 2700 }, false);
		// Se mantiene abajo (sigue al nuevo final), no salta hacia arriba.
		expect(container.scrollTop).toBe(2200);
	});
});
