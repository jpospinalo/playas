import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PantallaEscribir } from "@/components/guia/Pantallas";
import { TXT } from "@/lib/guia/textos";

function pintar() {
	const onPreguntar = vi.fn();
	render(
		<PantallaEscribir
			tituloRef={createRef<HTMLHeadingElement>()}
			inicial=""
			onCambio={vi.fn()}
			onVolver={vi.fn()}
			onPreguntar={onPreguntar}
		/>,
	);
	return onPreguntar;
}

describe("PantallaEscribir", () => {
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
});
