import { createRef } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Fuente, LARGO_VISIBLE } from "@/components/guia/Fuente";
import { PantallaEspera, PantallaSeguir, SEGUNDOS_AVISO_LENTO } from "@/components/guia/Pantallas";
import { Respuesta } from "@/components/guia/Respuesta";
import { SourcesAccordion } from "@/components/chat/SourcesAccordion";
import { TXT } from "@/lib/guia/textos";
import type { SourceGroup } from "@/lib/types";

const LARGO = "Artículo 166. ".concat("Las playas son bienes de uso público. ".repeat(30));
const grupo: SourceGroup = {
	source: "decreto-2324.md",
	title: "Decreto 2324 de 1984",
	doc_type: "normativa",
	metadata: { doc_type: "normativa", norma: "Decreto 2324 de 1984", articulo: "166" },
	fragments: [{ index: 1, content: LARGO, metadata: {} }],
};

afterEach(() => vi.restoreAllMocks());

describe("UX-01: fuentes completas en el flujo guiado", () => {
	it("muestra el texto completo a pedido y copia la referencia", async () => {
		const escribir = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
		Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: escribir } });
		render(
			<ol>
				<Fuente grupo={grupo} fragmento={grupo.fragments[0]} marcada={false} />
			</ol>,
		);
		const cita = screen.getByText(/^Artículo 166\./);
		expect(cita.textContent!.length).toBeLessThanOrEqual(LARGO_VISIBLE + 1);
		await userEvent.click(screen.getByRole("button", { name: "Ver todo el fragmento" }));
		expect(cita.textContent).toBe(LARGO.replace(/\s+/g, " ").trim());
		expect(screen.getByRole("button", { name: "Ver menos" })).toHaveAttribute("aria-expanded", "true");

		await userEvent.click(screen.getByRole("button", { name: "Copiar la referencia" }));
		expect(escribir).toHaveBeenCalledWith("Decreto 2324 de 1984, artículo 166");
		expect(await screen.findByText(/Copiado: Decreto 2324 de 1984, artículo 166/)).toBeInTheDocument();
	});
});

describe("UX-01: acordeón de fuentes del chat del equipo", () => {
	it("no corta títulos ni datos y deja leer el fragmento completo", async () => {
		render(<SourcesAccordion sources={[grupo]} />);
		await userEvent.click(screen.getByRole("button", { name: /fuente consultada/ }));
		expect(screen.getByText("Decreto 2324 de 1984").className).not.toContain("truncate");
		await userEvent.click(screen.getByRole("button", { name: "Ver todo el fragmento" }));
		expect(screen.getByRole("button", { name: "Ver menos" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Copiar referencia" })).toBeInTheDocument();
	});
});

describe("UX-02: espera por etapas", () => {
	it("marca la etapa actual, las hechas y el tiempo, sin anunciar los segundos", () => {
		render(<PantallaEspera tituloRef={createRef()} etapa="retrieving" segundos={12} onVolver={() => {}} />);
		const pasos = within(screen.getByRole("list", { name: "Pasos" })).getAllByRole("listitem");
		expect(pasos.map((p) => p.className)).toEqual(["hecho", "ahora", "despues"]);
		expect(pasos[1]).toHaveAttribute("aria-current", "step");
		expect(screen.getByText("Lleva 12 segundos.")).not.toHaveAttribute("role");
		expect(screen.getByRole("status")).toHaveTextContent("Buscando en las normas y las sentencias…");
	});

	it("avisa cuando tarda más de lo normal", () => {
		render(
			<PantallaEspera tituloRef={createRef()} etapa="generating" segundos={SEGUNDOS_AVISO_LENTO} onVolver={() => {}} />,
		);
		expect(screen.getByRole("status")).toHaveTextContent(TXT.esperaLenta);
	});
});

describe("Flujos: pregunta guardada y respuesta no guardada", () => {
	it("ofrece seguir con la pregunta que quedó sin respuesta", async () => {
		const onSeguir = vi.fn();
		render(
			<PantallaSeguir tituloRef={createRef()} pregunta="¿Puedo vender?" playa="Taganga" onSeguir={onSeguir} onEmpezar={() => {}} />,
		);
		expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(TXT.seguirTitulo);
		await userEvent.click(screen.getByRole("button", { name: "Seguir con mi pregunta" }));
		expect(onSeguir).toHaveBeenCalled();
	});

	it("si la respuesta no se guardó, avisa y permite guardarla otra vez", async () => {
		const onGuardarOtraVez = vi.fn();
		render(
			<Respuesta
				pregunta="x"
				playa={null}
				texto="Sí. Texto."
				fuentes={[]}
				puedeCalificar={false}
				onCalificar={vi.fn()}
				onVolver={vi.fn()}
				onOtraPregunta={vi.fn()}
				onEscribirDeNuevo={vi.fn()}
				tituloRef={createRef()}
				guardado="fallo"
				onGuardarOtraVez={onGuardarOtraVez}
			/>,
		);
		expect(screen.getByText(/no se pudo guardar/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Guardar otra vez" }));
		expect(onGuardarOtraVez).toHaveBeenCalled();
	});
});

describe("E2-12: datos parciales de la fuente", () => {
	it("aclara que son los datos disponibles y no muestra campos vacíos", () => {
		const parcial: SourceGroup = {
			source: "s.md",
			title: "Acción popular de prueba",
			doc_type: "jurisprudencia",
			metadata: { doc_type: "jurisprudencia", Radicado: "123" },
			fragments: [{ index: 3, content: "Texto corto.", metadata: {} }],
		};
		render(
			<ol>
				<Fuente grupo={parcial} fragmento={parcial.fragments[0]} marcada={false} />
			</ol>,
		);
		expect(screen.getByText("Datos disponibles de esta fuente:")).toBeInTheDocument();
		expect(screen.getByText("Radicado:")).toBeInTheDocument();
		expect(screen.queryByText("Corporación:")).not.toBeInTheDocument();
	});
});
