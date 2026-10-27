import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConPrivacidad } from "@/components/guia/Privacidad";
import { autorizarPrivacidad, pedirPrivacidad } from "@/lib/privacidad";

vi.mock("@/lib/privacidad", () => ({
	pedirPrivacidad: vi.fn(),
	autorizarPrivacidad: vi.fn(),
}));

const AVISO = {
	version: "2026-10-27",
	parrafos: ["Responsable del tratamiento: el equipo del proyecto ATLAS.", "Sus derechos (Ley 1581 de 2012)…"],
	aceptada: false,
	fecha: null,
};

function pintar(onSalir = vi.fn()) {
	render(
		<ConPrivacidad tituloRef={{ current: null }} onSalir={onSalir}>
			<p>Flujo de preguntas</p>
		</ConPrivacidad>,
	);
	return onSalir;
}

beforeEach(() => {
	vi.mocked(pedirPrivacidad).mockReset();
	vi.mocked(autorizarPrivacidad).mockReset();
});

describe("ConPrivacidad — aviso y autorización en el primer ingreso", () => {
	it("sin autorizar no deja ver el flujo; con la casilla marcada guarda y continúa", async () => {
		vi.mocked(pedirPrivacidad).mockResolvedValue(AVISO);
		vi.mocked(autorizarPrivacidad).mockResolvedValue({ ...AVISO, aceptada: true, fecha: "2026-10-27T10:00:00Z" });
		pintar();
		expect(await screen.findByRole("heading", { name: "Antes de empezar: sus datos" })).toBeInTheDocument();
		expect(screen.queryByText("Flujo de preguntas")).not.toBeInTheDocument();
		const continuar = screen.getByRole("button", { name: "Continuar" });
		expect(continuar).toBeDisabled();
		await userEvent.click(screen.getByRole("checkbox"));
		await userEvent.click(continuar);
		expect(autorizarPrivacidad).toHaveBeenCalled();
		expect(await screen.findByText("Flujo de preguntas")).toBeInTheDocument();
	});

	it("si ya autorizó pasa directo; 'No autorizo' sale", async () => {
		vi.mocked(pedirPrivacidad).mockResolvedValue({ ...AVISO, aceptada: true, fecha: "x" });
		pintar();
		expect(await screen.findByText("Flujo de preguntas")).toBeInTheDocument();
	});

	it("'No autorizo, salir' cierra la sesión", async () => {
		vi.mocked(pedirPrivacidad).mockResolvedValue(AVISO);
		const onSalir = pintar();
		await userEvent.click(await screen.findByRole("button", { name: "No autorizo, salir" }));
		expect(onSalir).toHaveBeenCalled();
	});

	it("PQ-110: con correo configurado da el enlace para revocar; sin correo no inventa uno", async () => {
		vi.mocked(pedirPrivacidad).mockResolvedValue({ ...AVISO, correo: "datos@ejemplo.edu.co" });
		const { unmount } = render(
			<ConPrivacidad tituloRef={{ current: null }} onSalir={vi.fn()}>
				<p>Flujo</p>
			</ConPrivacidad>,
		);
		const enlace = await screen.findByRole("link", { name: "datos@ejemplo.edu.co" });
		expect(enlace).toHaveAttribute("href", "mailto:datos@ejemplo.edu.co");
		unmount();
		vi.mocked(pedirPrivacidad).mockResolvedValue(AVISO);
		pintar();
		await screen.findByRole("heading", { name: "Antes de empezar: sus datos" });
		expect(screen.queryByText(/Para revocar esta autorización/)).toBeNull();
	});
});
