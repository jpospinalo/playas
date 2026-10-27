import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Aparece } from "@/components/admin/panel/Aparece";

function Dos() {
	const [panel, setPanel] = useState<"a" | "b" | null>(null);
	return (
		<>
			<button type="button" onClick={() => setPanel("a")}>
				Cambiar
			</button>
			<button type="button" onClick={() => setPanel("b")}>
				Desactivar
			</button>
			<Aparece abierto={panel === "a"} enfocar>
				<label htmlFor="rol">Rol</label>
				<select id="rol" />
			</Aparece>
			<Aparece abierto={panel === "b"} enfocar>
				<button type="button">Sí, desactivar</button>
			</Aparece>
		</>
	);
}

describe("Aparece (J5-6)", () => {
	it("abre un solo panel a la vez y lleva el foco a su primer campo", async () => {
		const user = userEvent.setup();
		render(<Dos />);
		expect(screen.queryByLabelText("Rol")).toBeNull();

		await user.click(screen.getByRole("button", { name: "Cambiar" }));
		expect(screen.getByLabelText("Rol")).toHaveFocus();

		await user.click(screen.getByRole("button", { name: "Desactivar" }));
		// Sin matchMedia (o con movimiento reducido) se cierra al instante.
		expect(screen.queryByLabelText("Rol")).toBeNull();
		expect(screen.getByRole("button", { name: "Sí, desactivar" })).toHaveFocus();
	});

	it("PQ-99: en una confirmación destructiva el foco va a Cancelar", async () => {
		const user = userEvent.setup();
		function Baja() {
			const [abierto, setAbierto] = useState(false);
			return (
				<>
					<button type="button" onClick={() => setAbierto(true)}>
						Desactivar
					</button>
					<Aparece abierto={abierto} enfocar>
						<button type="button">Sí, desactivar</button>
						<button type="button" data-foco>
							Cancelar
						</button>
					</Aparece>
				</>
			);
		}
		render(<Baja />);
		await user.click(screen.getByRole("button", { name: "Desactivar" }));
		expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
	});
});
