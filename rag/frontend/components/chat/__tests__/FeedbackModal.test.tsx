import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackModal } from "@/components/chat/FeedbackModal";
import { submitConversationFeedback } from "@/lib/api";

vi.mock("@/lib/api", () => ({
	submitConversationFeedback: vi.fn(),
}));

const submitMock = submitConversationFeedback as unknown as ReturnType<typeof vi.fn>;

async function rateAll(user: ReturnType<typeof userEvent.setup>) {
	for (const label of [
		"Tono de las respuestas",
		"Longitud de las respuestas",
		"Usabilidad del sistema",
		"Calificación general",
	]) {
		const group = screen.getByRole("group", { name: label });
		await user.click(
			// Cualquier estrella sirve; se usa la de valor 5 ("Excelente"/"Muy larga").
			group.querySelectorAll("button")[4],
		);
	}
}

describe("FeedbackModal — nombre accesible persistente y reflow", () => {
	beforeEach(() => {
		submitMock.mockReset();
	});

	afterEach(() => {
		vi.clearAllMocks();
	});

	it("el panel tiene nombre accesible no vacío en idle, loading y success", async () => {
		const user = userEvent.setup();
		let resolveSubmit: (v: { id: string }) => void = () => {};
		submitMock.mockReturnValue(
			new Promise((resolve) => {
				resolveSubmit = resolve;
			}),
		);

		render(<FeedbackModal open onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		const accessibleNameOf = () => {
			const labelledBy = dialog.getAttribute("aria-labelledby");
			expect(labelledBy).toBeTruthy();
			const labelEl = document.getElementById(labelledBy as string);
			expect(labelEl).not.toBeNull();
			return labelEl?.textContent?.trim() ?? "";
		};

		// idle
		expect(accessibleNameOf()).toBe("Califica la conversación");

		// loading
		await rateAll(user);
		await user.click(screen.getByRole("button", { name: "Enviar calificación" }));
		expect(accessibleNameOf()).toBe("Califica la conversación");

		// success
		resolveSubmit({ id: "fb-1" });
		await waitFor(() =>
			expect(screen.getByText("¡Gracias por tu calificación!")).toBeInTheDocument(),
		);
		expect(accessibleNameOf()).toBe("Califica la conversación");
	});

	it("en el estado de éxito no hay dos elementos con el mismo id del título", async () => {
		const user = userEvent.setup();
		submitMock.mockResolvedValue({ id: "fb-1" });

		render(<FeedbackModal open onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		const titleId = dialog.getAttribute("aria-labelledby") as string;

		await rateAll(user);
		await user.click(screen.getByRole("button", { name: "Enviar calificación" }));
		await waitFor(() =>
			expect(screen.getByText("¡Gracias por tu calificación!")).toBeInTheDocument(),
		);

		expect(document.querySelectorAll(`#${titleId}`)).toHaveLength(1);
	});

	it("el mensaje de éxito se marca role=\"status\" sin volver todo el panel una región viva", async () => {
		const user = userEvent.setup();
		submitMock.mockResolvedValue({ id: "fb-1" });

		render(<FeedbackModal open onClose={vi.fn()} />);

		await rateAll(user);
		await user.click(screen.getByRole("button", { name: "Enviar calificación" }));

		const status = await screen.findByRole("status");
		expect(status).toHaveTextContent("¡Gracias por tu calificación!");

		// El panel del diálogo en sí no debe llevar un rol/aria-live que lo
		// convierta en una región viva completa.
		const dialog = screen.getByRole("dialog");
		expect(dialog).not.toHaveAttribute("aria-live");
	});

	it("el panel tiene un límite de altura relativo al viewport con scroll local", () => {
		render(<FeedbackModal open onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		expect(dialog.className).toMatch(/max-h-\[calc\(100dvh-2rem\)\]/);
		expect(dialog.className).toMatch(/overflow-y-auto/);
	});

	it("closeBlocked sigue impidiendo Escape y el botón de cierre mientras se envía", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		submitMock.mockReturnValue(new Promise(() => {})); // nunca resuelve: se queda en "loading"

		render(<FeedbackModal open onClose={onClose} />);

		await rateAll(user);
		await user.click(screen.getByRole("button", { name: "Enviar calificación" }));

		// El botón de cierre explícito no se renderiza mientras se envía.
		expect(screen.queryByRole("button", { name: "Cerrar" })).not.toBeInTheDocument();

		await user.keyboard("{Escape}");
		expect(onClose).not.toHaveBeenCalled();
	});
});

describe("FeedbackModal — un único <h2> semántico, sin duplicarlo en el DOM", () => {
	it("en idle/loading, el texto del título aparece dos veces en el DOM (una visible, otra sr-only), pero un solo <h2>", () => {
		render(<FeedbackModal open onClose={vi.fn()} />);

		// El texto del título sigue existiendo dos veces a nivel de DOM (un
		// <h2> sr-only siempre presente, y un <p> visible en la rama
		// "form") — eso no cambia, ya que no se puede alterar el texto
		// visible ni el diseño. Lo que ya no ocurre es que el segundo sea
		// también un <h2>: eso duplicaría el encabezado semántico del
		// diálogo, aunque estuviera oculto de la tecnología de asistencia.
		const domMatches = screen.getAllByText("Califica la conversación");
		expect(domMatches).toHaveLength(2);

		const headings = screen.getAllByRole("heading", {
			name: "Califica la conversación",
			hidden: true,
		});
		expect(headings).toHaveLength(1);
		expect(headings[0].tagName).toBe("H2");

		// El elemento visible NO es un <h2>: es presentacional.
		const visibleTitle = domMatches.find((el) => el !== headings[0]);
		expect(visibleTitle?.tagName).not.toBe("H2");
		expect(visibleTitle).toHaveAttribute("aria-hidden", "true");

		// Y ese único <h2> es el que da nombre accesible al diálogo.
		const dialog = screen.getByRole("dialog");
		expect(dialog).toHaveAccessibleName("Califica la conversación");
		expect(headings[0].id).toBe(dialog.getAttribute("aria-labelledby"));
	});
});
