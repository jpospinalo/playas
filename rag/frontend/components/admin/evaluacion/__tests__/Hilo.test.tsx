import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Hilo } from "@/components/admin/evaluacion/Hilo";
import type { DetalleEvaluacion } from "@/lib/admin/validacion";

const base: DetalleEvaluacion = {
	evaluacion: {
		id: "e1234567890",
		sede: "Santa Marta",
		evaluador: "Semillerista Santa Marta 1",
		f1: 3,
		f2: 3,
		f3: 2,
		forma: 8,
		ct: "I",
		cv: 9,
		total: 17,
		valida: true,
		observaciones: null,
		estado: "por_validar",
		comentarios: 0,
	},
	hilo: [],
};

describe("Hilo (J6-A2/A3)", () => {
	it("sin mensajes, quien calificó no ve un cuadro para responder", () => {
		render(<Hilo detalle={base} onCambio={vi.fn()} lado="semillerista" />);
		expect(screen.getByText("Cuando la validación se haga, aquí verá su comentario.")).toBeInTheDocument();
		expect(screen.queryByRole("textbox")).toBeNull();
	});

	it("con mensajes, responde a la persona por su nombre", () => {
		const detalle = {
			...base,
			hilo: [{ autor: "Ana María Muelle", tipo: "desacuerdo" as const, texto: "Revise el nivel", fecha: "2026-10-27T10:00:00" }],
		};
		render(<Hilo detalle={detalle} onCambio={vi.fn()} lado="semillerista" />);
		expect(screen.getByLabelText("Responder a Ana María Muelle")).toBeInTheDocument();
	});

	it("quien valida le escribe a quien calificó por su nombre", () => {
		render(<Hilo detalle={base} onCambio={vi.fn()} lado="validacion" />);
		expect(screen.getByLabelText("Escribirle a Semillerista Santa Marta 1")).toBeInTheDocument();
	});

	it("PQ-111: una corrección propia no abre el cuadro para responder", () => {
		const detalle = {
			...base,
			hilo: [
				{ autor: "Semillerista Santa Marta 1", tipo: "correccion" as const, texto: "Cv 4 → 5", fecha: "2026-10-27T10:00:00" },
			],
		};
		render(<Hilo detalle={detalle} onCambio={vi.fn()} lado="semillerista" />);
		expect(screen.getByText("Cv 4 → 5")).toBeInTheDocument();
		expect(screen.queryByRole("textbox")).toBeNull();
		expect(screen.getByText("Cuando la validación se haga, aquí verá su comentario.")).toBeInTheDocument();
	});
});
