import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FormCalificacion } from "@/components/admin/evaluacion/FormCalificacion";
import type { Rubrica } from "@/lib/admin/evaluacion";

const RUBRICA: Rubrica = {
	forma: {
		f1: { nombre: "F1 - Contextualización", pregunta: "¿Contexto?", niveles: { "1": "Sin contexto", "2": "Algo", "3": "Claro" } },
		f2: { nombre: "F2 - Problema concreto", pregunta: "¿Problema?", niveles: { "1": "No", "2": "Algo", "3": "Sí" } },
		f3: { nombre: "F3 - Redacción", pregunta: "¿Clara?", niveles: { "1": "Confusa", "2": "Regular", "3": "Clara" } },
	},
	fondo: {
		S: { nivel: "Sencillo", como: "Aplicación directa", guia: { "3": "básico", "4": "con contexto", "5": "bien", "6": "muy completo" } },
		I: { nivel: "Intermedio", como: "Conflicto real", guia: { "7": "identificable", "8": "claro", "9": "muy bien" } },
		A: { nivel: "Avanzado", como: "Problemática compleja", guia: { "10": "clara", "11": "varios actores", "12": "completo" } },
	},
	rangos: { S: [3, 6], I: [7, 9], A: [10, 12] },
	umbral_diferencia: 2,
};

describe("FormCalificacion — planilla del ejercicio", () => {
	it("Cv solo ofrece los valores del nivel elegido y el total se calcula solo", async () => {
		const user = userEvent.setup();
		const onGuardar = vi.fn(async () => {});
		render(<FormCalificacion rubrica={RUBRICA} inicial={null} textoBoton="Guardar calificación" onGuardar={onGuardar} />);
		await user.click(screen.getByRole("radio", { name: /3 Claro/ }));
		await user.click(screen.getByRole("radio", { name: /3 Sí/ }));
		await user.click(screen.getByRole("radio", { name: /2 Regular/ }));
		expect(screen.getByText("8")).toBeInTheDocument(); // forma 3+3+2
		await user.click(screen.getByRole("radio", { name: /I: Intermedio/ }));
		const cvs = screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).name.endsWith("-cv"));
		expect(cvs.map((r) => (r as HTMLInputElement).value)).toEqual(["7", "8", "9"]);
		await user.click(screen.getByRole("radio", { name: /9 muy bien/ }));
		expect(screen.getByText("17")).toBeInTheDocument(); // 8 + 9
		await user.click(screen.getByRole("button", { name: "Guardar calificación" }));
		expect(onGuardar).toHaveBeenCalledWith({
			f1: 3,
			f2: 3,
			f3: 2,
			ct: "I",
			cv: 9,
			valida: true,
			observaciones: null,
		});
	});

	it("al cambiar de nivel el Cv vuelve al rango del nuevo nivel", async () => {
		const user = userEvent.setup();
		render(<FormCalificacion rubrica={RUBRICA} inicial={null} textoBoton="Guardar" onGuardar={vi.fn()} />);
		await user.click(screen.getByRole("radio", { name: /A: Avanzado/ }));
		await user.click(screen.getByRole("radio", { name: /12 completo/ }));
		await user.click(screen.getByRole("radio", { name: /S: Sencillo/ }));
		const marcado = screen
			.getAllByRole("radio")
			.find((r) => (r as HTMLInputElement).name.endsWith("-cv") && (r as HTMLInputElement).checked) as HTMLInputElement;
		expect(marcado.value).toBe("3");
	});

	it("si falta algo, lo dice y no guarda", async () => {
		const user = userEvent.setup();
		const onGuardar = vi.fn();
		render(<FormCalificacion rubrica={RUBRICA} inicial={null} textoBoton="Guardar" onGuardar={onGuardar} />);
		await user.click(screen.getByRole("button", { name: "Guardar" }));
		expect(screen.getByRole("alert")).toHaveTextContent("Falta elegir: F1, F2, F3, Ct (nivel), Cv.");
		expect(onGuardar).not.toHaveBeenCalled();
	});
});
