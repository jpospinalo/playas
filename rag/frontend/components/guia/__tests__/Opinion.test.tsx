import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PantallaOpinion } from "@/components/guia/Opinion";
import { submitConversationFeedback } from "@/lib/api";

vi.mock("@/lib/api", () => ({ submitConversationFeedback: vi.fn(async () => ({ id: "f1" })) }));

function pintar() {
	const props = {
		tituloRef: { current: null },
		conversationId: "conv-1",
		onVolver: vi.fn(),
		onOtraPregunta: vi.fn(),
		onSalir: vi.fn(),
	};
	render(<PantallaOpinion {...props} />);
	return props;
}

beforeEach(() => vi.mocked(submitConversationFeedback).mockClear());

describe("PantallaOpinion — encuesta de percepción del flujo guiado", () => {
	it("pregunta claridad, facilidad de uso y percepción general", () => {
		pintar();
		expect(screen.getByRole("group", { name: "¿Qué tan claras fueron las respuestas de ATLAS?" })).toBeInTheDocument();
		expect(screen.getByRole("group", { name: "¿Qué tan fácil fue usar ATLAS?" })).toBeInTheDocument();
		expect(screen.getByRole("group", { name: "En general, ¿cómo le pareció la experiencia?" })).toBeInTheDocument();
	});

	it("no envía si falta una respuesta", async () => {
		pintar();
		await userEvent.click(screen.getByRole("radio", { name: "Claras" }));
		await userEvent.click(screen.getByRole("button", { name: "Enviar mi opinión" }));
		expect(screen.getByRole("alert")).toHaveTextContent("Faltan 2 preguntas");
		expect(submitConversationFeedback).not.toHaveBeenCalled();
	});

	it("guarda clarity, usability y overall con el comentario", async () => {
		const props = pintar();
		await userEvent.click(screen.getByRole("radio", { name: "Muy claras" }));
		await userEvent.click(screen.getByRole("radio", { name: "Fácil" }));
		await userEvent.click(screen.getByRole("radio", { name: "Regular" }));
		await userEvent.type(screen.getByLabelText("¿Quiere contarnos algo más? (opcional)"), "Muy útil");
		await userEvent.click(screen.getByRole("button", { name: "Enviar mi opinión" }));
		expect(submitConversationFeedback).toHaveBeenCalledWith({
			ratings: { clarity: 5, usability: 4, overall: 3 },
			comment: "Muy útil",
			conversation_id: "conv-1",
		});
		expect(await screen.findByRole("heading", { name: "Gracias por su opinión" })).toBeInTheDocument();
		// La acción principal vuelve al inicio; cerrar sesión es secundario y
		// dice para qué sirve (celular compartido, QA E2-11).
		const botones = screen.getAllByRole("button");
		expect(botones[0]).toHaveAccessibleName("Volver al inicio");
		await userEvent.click(screen.getByRole("button", { name: "Volver al inicio" }));
		expect(props.onOtraPregunta).toHaveBeenCalled();
		const dejar = screen.getByRole("button", { name: "Terminar y dejar el celular para otra persona" });
		expect(dejar).toHaveAccessibleDescription(/borra de este celular su pregunta y su correo/);
		await userEvent.click(dejar);
		expect(props.onSalir).toHaveBeenCalled();
	});
});
