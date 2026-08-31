import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "@/components/chat/ChatInput";
import { MAX_QUESTION_CHARS, QUESTION_COUNTER_THRESHOLD } from "@/lib/contracts";

function setup(props: Partial<React.ComponentProps<typeof ChatInput>> = {}) {
	const textareaRef = createRef<HTMLTextAreaElement>();
	const onChange = vi.fn();
	const onSubmit = vi.fn();
	const utils = render(
		<ChatInput
			value=""
			loading={false}
			textareaRef={textareaRef}
			onChange={onChange}
			onSubmit={onSubmit}
			{...props}
		/>,
	);
	return { ...utils, onChange, onSubmit, textareaRef };
}

describe("ChatInput — campo de consulta (A7)", () => {
	it("vacío: el botón de enviar está deshabilitado", () => {
		setup({ value: "" });
		expect(
			screen.getByRole("button", { name: "Enviar consulta" }),
		).toBeDisabled();
	});

	it("vacío tras solo espacios: sigue deshabilitado (se usa el valor recortado)", () => {
		setup({ value: "   " });
		expect(
			screen.getByRole("button", { name: "Enviar consulta" }),
		).toBeDisabled();
	});

	it("envío válido: Enter (sin Shift) dispara onSubmit una vez", async () => {
		const user = userEvent.setup();
		const { onSubmit } = setup({ value: "¿Qué dice la norma?" });

		const textarea = screen.getByPlaceholderText("Pregúntale a ATLAS…");
		textarea.focus();
		await user.keyboard("{Enter}");

		expect(onSubmit).toHaveBeenCalledTimes(1);
	});

	it("Shift+Enter no envía (inserta salto de línea)", async () => {
		const user = userEvent.setup();
		const { onSubmit } = setup({ value: "¿Qué dice la norma?" });

		const textarea = screen.getByPlaceholderText("Pregúntale a ATLAS…");
		textarea.focus();
		await user.keyboard("{Shift>}{Enter}{/Shift}");

		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("composición IME: Enter que confirma la composición no envía la consulta", () => {
		const { onSubmit } = setup({ value: "こんにちは" });

		const textarea = screen.getByPlaceholderText("Pregúntale a ATLAS…");
		// userEvent no modela `isComposing`; se dispara el evento nativo
		// directamente para simular un IME en composición (p. ej. japonés,
		// chino, coreano, o acentos compuestos).
		textarea.dispatchEvent(
			new KeyboardEvent("keydown", {
				key: "Enter",
				bubbles: true,
				cancelable: true,
				composed: true,
				isComposing: true,
			}),
		);

		expect(onSubmit).not.toHaveBeenCalled();
	});

	it(`el textarea aplica maxLength=${MAX_QUESTION_CHARS}`, () => {
		setup();
		const textarea = screen.getByPlaceholderText(
			"Pregúntale a ATLAS…",
		) as HTMLTextAreaElement;
		expect(textarea.maxLength).toBe(MAX_QUESTION_CHARS);
	});

	it("el contador de caracteres no aparece por debajo del umbral", () => {
		setup({ value: "x".repeat(QUESTION_COUNTER_THRESHOLD - 1) });
		expect(
			screen.queryByText(`${QUESTION_COUNTER_THRESHOLD - 1}/${MAX_QUESTION_CHARS}`),
		).not.toBeInTheDocument();
	});

	it("el contador de caracteres aparece a partir del umbral", () => {
		setup({ value: "x".repeat(QUESTION_COUNTER_THRESHOLD) });
		expect(
			screen.getByText(`${QUESTION_COUNTER_THRESHOLD}/${MAX_QUESTION_CHARS}`),
		).toBeInTheDocument();
	});
});
