import { createRef, useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CajaPregunta, PantallaInicio } from "@/components/guia/Pantallas";
import { EJEMPLOS, TXT } from "@/lib/guia/textos";
import { TEMAS } from "@/lib/guia/temas";

function Caja({ onPreguntar }: { onPreguntar: (t: string) => void }) {
	const [valor, setValor] = useState("");
	return <CajaPregunta id="texto" valor={valor} onCambio={setValor} onPreguntar={onPreguntar} />;
}

function pintar() {
	const onPreguntar = vi.fn();
	render(<Caja onPreguntar={onPreguntar} />);
	return onPreguntar;
}

/** Simula un celular (pantalla táctil) o un computador. */
function puntero(tactil: boolean) {
	vi.stubGlobal(
		"matchMedia",
		vi.fn((q: string) => ({
			matches: tactil && q === "(pointer: coarse)",
			media: q,
			addEventListener() {},
			removeEventListener() {},
		})),
	);
}

afterEach(() => vi.unstubAllGlobals());

/** El nombre de la playa va en itálica (otro elemento): se compara sin espacios. */
const nombre = (texto: string) => (n: string) => n.replace(/\s+/g, "") === texto.replace(/\s+/g, "");

describe("CajaPregunta", () => {
	it("sin texto pide escribir la pregunta", async () => {
		const onPreguntar = pintar();
		await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));
		expect(screen.getByRole("alert")).toHaveTextContent(TXT.escribirVacio);
		expect(onPreguntar).not.toHaveBeenCalled();
	});

	it("con una pregunta muy corta dice que es corta, no que está vacía (QA-31)", async () => {
		const onPreguntar = pintar();
		await userEvent.type(screen.getByLabelText("Su pregunta"), "pez");
		await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));
		expect(screen.getByRole("alert")).toHaveTextContent(TXT.escribirCorta);
		expect(onPreguntar).not.toHaveBeenCalled();
	});

	it("con una pregunta de verdad la envía", async () => {
		const onPreguntar = pintar();
		await userEvent.type(screen.getByLabelText("Su pregunta"), "¿Puedo vender en El Rodadero?");
		await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));
		expect(onPreguntar).toHaveBeenCalledWith("¿Puedo vender en El Rodadero?");
	});

	it("en el computador, Enter envía la pregunta", async () => {
		puntero(false);
		const onPreguntar = pintar();
		await userEvent.type(screen.getByLabelText("Su pregunta"), "¿Puedo pescar en Taganga?{Enter}");
		expect(onPreguntar).toHaveBeenCalledWith("¿Puedo pescar en Taganga?");
	});

	it("en el celular, Enter hace otro renglón y no envía", async () => {
		puntero(true);
		const onPreguntar = pintar();
		const caja = screen.getByLabelText("Su pregunta");
		await userEvent.type(caja, "Vendo cocadas{Enter}en Taganga");
		expect(onPreguntar).not.toHaveBeenCalled();
		expect(caja).toHaveValue("Vendo cocadas\nen Taganga");
	});
});

describe("PantallaInicio", () => {
	function Inicio({ onPreguntar, onTema }: { onPreguntar: (t: string) => void; onTema: () => void }) {
		const [borrador, setBorrador] = useState("");
		return (
			<PantallaInicio
				tituloRef={createRef<HTMLHeadingElement>()}
				cajaRef={createRef<HTMLTextAreaElement>()}
				borrador={borrador}
				onCambio={setBorrador}
				onPreguntar={onPreguntar}
				onTema={onTema}
			/>
		);
	}

	it("muestra la caja, los ejemplos y los seis temas", () => {
		render(<Inicio onPreguntar={vi.fn()} onTema={vi.fn()} />);
		expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(TXT.inicioTitulo);
		expect(screen.getByLabelText("Su pregunta")).toHaveAttribute("placeholder", TXT.cajaPista);
		expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(TXT.guiarTitulo);
		for (const e of EJEMPLOS) expect(screen.getByRole("button", { name: nombre(e) })).toBeInTheDocument();
		for (const t of TEMAS) expect(screen.getByRole("button", { name: new RegExp(t.titulo) })).toBeInTheDocument();
	});

	it("un ejemplo llena la caja sin enviar", async () => {
		const onPreguntar = vi.fn();
		render(<Inicio onPreguntar={onPreguntar} onTema={vi.fn()} />);
		await userEvent.click(screen.getByRole("button", { name: nombre(EJEMPLOS[1]) }));
		expect(screen.getByLabelText("Su pregunta")).toHaveValue(EJEMPLOS[1]);
		expect(onPreguntar).not.toHaveBeenCalled();
	});

	it("tocar un tema lo abre", async () => {
		const onTema = vi.fn();
		render(<Inicio onPreguntar={vi.fn()} onTema={onTema} />);
		await userEvent.click(screen.getByRole("button", { name: new RegExp(TEMAS[1].titulo) }));
		expect(onTema).toHaveBeenCalledWith(TEMAS[1]);
	});
});
