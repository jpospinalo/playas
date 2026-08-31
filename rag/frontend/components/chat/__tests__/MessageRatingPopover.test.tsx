import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MessageRatingPopover } from "@/components/chat/MessageRatingPopover";

async function rate(
	user: ReturnType<typeof userEvent.setup>,
	label: string,
	star = 5,
) {
	const group = screen.getByRole("group", { name: label });
	await user.click(group.querySelectorAll("button")[star - 1]);
}

describe("MessageRatingPopover — nombre accesible persistente y reflow", () => {
	it("el panel tiene nombre accesible no vacío en idle, loading y success", async () => {
		const user = userEvent.setup();
		let resolveSubmit: () => void = () => {};
		const onSubmit = vi.fn(
			() =>
				new Promise<void>((resolve) => {
					resolveSubmit = resolve;
				}),
		);

		render(<MessageRatingPopover open onSubmit={onSubmit} onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		const accessibleNameOf = () => {
			const labelledBy = dialog.getAttribute("aria-labelledby");
			expect(labelledBy).toBeTruthy();
			const labelEl = document.getElementById(labelledBy as string);
			expect(labelEl).not.toBeNull();
			return labelEl?.textContent?.trim() ?? "";
		};

		expect(accessibleNameOf()).toBe("Calificar esta respuesta");

		await rate(user, "Pertinencia de la respuesta");
		await rate(user, "Precisión de la respuesta");
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		expect(accessibleNameOf()).toBe("Calificar esta respuesta");

		resolveSubmit();
		await waitFor(() =>
			expect(screen.getByText("¡Gracias por tu calificación!")).toBeInTheDocument(),
		);
		expect(accessibleNameOf()).toBe("Calificar esta respuesta");
	});

	it("en el estado de éxito no hay dos elementos con el mismo id del título", async () => {
		const user = userEvent.setup();
		const onSubmit = vi.fn().mockResolvedValue(undefined);

		render(<MessageRatingPopover open onSubmit={onSubmit} onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		const titleId = dialog.getAttribute("aria-labelledby") as string;

		await rate(user, "Pertinencia de la respuesta");
		await rate(user, "Precisión de la respuesta");
		await user.click(screen.getByRole("button", { name: "Enviar" }));
		await waitFor(() =>
			expect(screen.getByText("¡Gracias por tu calificación!")).toBeInTheDocument(),
		);

		expect(document.querySelectorAll(`#${titleId}`)).toHaveLength(1);
	});

	it("el mensaje de éxito se marca role=\"status\" sin volver todo el panel una región viva", async () => {
		const user = userEvent.setup();
		const onSubmit = vi.fn().mockResolvedValue(undefined);

		render(<MessageRatingPopover open onSubmit={onSubmit} onClose={vi.fn()} />);

		await rate(user, "Pertinencia de la respuesta");
		await rate(user, "Precisión de la respuesta");
		await user.click(screen.getByRole("button", { name: "Enviar" }));

		const status = await screen.findByRole("status");
		expect(status).toHaveTextContent("¡Gracias por tu calificación!");

		const dialog = screen.getByRole("dialog");
		expect(dialog).not.toHaveAttribute("aria-live");
	});

	it("el panel tiene un límite de altura relativo al viewport con scroll local", () => {
		render(<MessageRatingPopover open onSubmit={vi.fn()} onClose={vi.fn()} />);

		const dialog = screen.getByRole("dialog");
		expect(dialog.className).toMatch(/max-h-\[calc\(100dvh-2rem\)\]/);
		expect(dialog.className).toMatch(/overflow-y-auto/);
	});

	it("closeBlocked sigue impidiendo Escape y el botón de cierre mientras se envía", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		const onSubmit = vi.fn(() => new Promise<void>(() => {})); // nunca resuelve

		render(<MessageRatingPopover open onSubmit={onSubmit} onClose={onClose} />);

		await rate(user, "Pertinencia de la respuesta");
		await rate(user, "Precisión de la respuesta");
		await user.click(screen.getByRole("button", { name: "Enviar" }));

		expect(screen.queryByRole("button", { name: "Cerrar" })).not.toBeInTheDocument();

		await user.keyboard("{Escape}");
		expect(onClose).not.toHaveBeenCalled();
	});
});

describe("MessageRatingPopover — un único <h2> semántico, sin duplicarlo en el DOM", () => {
	it("en idle/loading, el texto del título aparece dos veces en el DOM (una visible, otra sr-only), pero un solo <h2>", () => {
		render(<MessageRatingPopover open onSubmit={vi.fn()} onClose={vi.fn()} />);

		// El texto del título sigue existiendo dos veces a nivel de DOM (un
		// <h2> sr-only siempre presente, y un <p> visible en la rama
		// "form") — eso no cambia, ya que no se puede alterar el texto
		// visible ni el diseño. Lo que ya no ocurre es que el segundo sea
		// también un <h2>: eso duplicaría el encabezado semántico del
		// diálogo, aunque estuviera oculto de la tecnología de asistencia.
		const domMatches = screen.getAllByText("Calificar esta respuesta");
		expect(domMatches).toHaveLength(2);

		const headings = screen.getAllByRole("heading", {
			name: "Calificar esta respuesta",
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
		expect(dialog).toHaveAccessibleName("Calificar esta respuesta");
		expect(headings[0].id).toBe(dialog.getAttribute("aria-labelledby"));
	});
});
