"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { MAX_QUESTION_CHARS, QUESTION_COUNTER_THRESHOLD } from "@/lib/contracts";

type Variant = "hero" | "docked";

interface ChatInputProps {
	value: string;
	loading: boolean;
	/** A6 — true solo mientras hay una generación en streaming activa que se puede detener. */
	canCancel?: boolean;
	/** A6 — detiene la generación en curso. Requerido si `canCancel` puede ser true. */
	onCancel?: () => void;
	textareaRef: React.RefObject<HTMLTextAreaElement | null>;
	onChange: (value: string) => void;
	onSubmit: () => void;
	variant?: Variant;
	sideSlot?: React.ReactNode;
}

const MAX_HEIGHT_PX = 200; // ~8 lines

export function ChatInput({
	value,
	loading,
	canCancel = false,
	onCancel,
	textareaRef,
	onChange,
	onSubmit,
	variant = "docked",
	sideSlot,
}: ChatInputProps) {
	/* Auto-resize: runs on user typing and on programmatic value changes */
	useEffect(() => {
		const el = textareaRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
	}, [value, textareaRef]);

	function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
		// A7 — mientras un IME sigue componiendo (acentos, teclados CJK, etc.),
		// el Enter que confirma la composición no debe también enviar la
		// consulta: `isComposing` distingue ese Enter "interno" del real.
		if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
			e.preventDefault();
			onSubmit();
		}
	}

	const trimmed = value.trim();
	const canSend = !loading && trimmed.length > 0;
	// A6 — mientras la generación está activa, el mismo botón se convierte
	// en "Detener": nunca aparece durante la creación de la conversación ni
	// la persistencia de la pregunta/respuesta (fases donde `loading` es
	// true pero `canCancel` es false).
	const showCancel = canCancel && Boolean(onCancel);
	const [swing, setSwing] = useState(0);

	const form = (
		<form
			onSubmit={(e) => {
				e.preventDefault();
				if (canSend) onSubmit();
			}}
			aria-label="Formulario de consulta"
			className="group/input relative mx-auto w-full max-w-3xl"
		>
			<label htmlFor={`chat-input-${variant}`} className="sr-only">
				Escribe tu pregunta sobre playas o derecho costero
			</label>

			<div className="relative flex items-center gap-2 rounded-[28px] border border-border bg-surface/90 py-2 pl-5 pr-2 shadow-sm backdrop-blur-md transition-[border-color,box-shadow] duration-200 focus-within:border-accent focus-within:shadow-[0_0_0_4px_var(--accent-soft)]">
				<textarea
					ref={textareaRef}
					id={`chat-input-${variant}`}
					name="question"
					rows={1}
					placeholder="Pregúntale a ATLAS…"
					value={value}
					onChange={(e) => onChange(e.target.value)}
					onKeyDown={handleKeyDown}
					autoComplete="off"
					spellCheck
					disabled={loading}
					maxLength={MAX_QUESTION_CHARS}
					className="min-w-0 flex-1 resize-none bg-transparent py-1 text-[15px] leading-6 text-foreground placeholder:text-subtle focus:outline-none disabled:opacity-50"
					style={{ overflowY: "hidden" }}
				/>
				{/* A7 — contador visible solo cerca del límite; no es una
				    validación en sí (el backend y `useChat.submit` ya la
				    aplican), solo evita que el límite tome al usuario por
				    sorpresa. */}
				{value.length >= QUESTION_COUNTER_THRESHOLD && (
					<span
						aria-hidden="true"
						className={`shrink-0 self-end pb-1.5 text-[11px] tabular-nums ${
							value.length >= MAX_QUESTION_CHARS
								? "text-danger"
								: "text-subtle"
						}`}
					>
						{value.length}/{MAX_QUESTION_CHARS}
					</span>
				)}
				<button
					type={showCancel ? "button" : "submit"}
					disabled={showCancel ? false : !canSend}
					aria-label={
						showCancel
							? "Detener generación"
							: loading
								? "Consultando…"
								: "Enviar consulta"
					}
					onClick={(e) => {
						if (showCancel) {
							e.preventDefault();
							onCancel?.();
							return;
						}
						if (canSend) setSwing((s) => s + 1);
					}}
					className={`flex h-8 w-8 shrink-0 items-center justify-center self-end rounded-xl transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
						showCancel
							? "bg-danger text-surface hover:opacity-90"
							: canSend
								? "bg-accent text-accent-fg hover:bg-accent-hover"
								: "bg-elevated text-subtle"
					}`}
				>
					{showCancel ? (
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="12"
							height="12"
							viewBox="0 0 24 24"
							fill="currentColor"
							aria-hidden="true"
						>
							<rect x="4" y="4" width="16" height="16" rx="2" />
						</svg>
					) : loading ? (
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="13"
							height="13"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2.2"
							strokeLinecap="round"
							strokeLinejoin="round"
							aria-hidden="true"
							className="animate-spin"
						>
							<path d="M21 12a9 9 0 1 1-6.219-8.56" />
						</svg>
					) : (
						<motion.svg
							key={swing}
							xmlns="http://www.w3.org/2000/svg"
							width="15"
							height="15"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2"
							strokeLinecap="round"
							strokeLinejoin="round"
							aria-hidden="true"
							initial={{ rotate: 0 }}
							animate={{ rotate: [0, -12, 8, -4, 0] }}
							transition={{ duration: 0.5, ease: "easeInOut" }}
						>
							<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
							<path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
							<path d="M7 21h10" />
							<path d="M12 3v18" />
							<path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
						</motion.svg>
					)}
				</button>
			</div>
		</form>
	);

	if (variant === "hero") {
		return form;
	}

	return (
		<div className="relative shrink-0 px-4 pb-[calc(1rem+1cm)] pt-2 sm:pb-[calc(1.5rem+1cm)]">
			{/* `sideSlot` (el botón de feedback) NO debe usar `absolute
			    left-full` de forma incondicional: al posicionarlo fuera del
			    ancho de este contenedor (ya `max-w-3xl` y centrado), en un
			    viewport angosto de 320px no queda espacio a la derecha y el
			    botón terminaría fuera del viewport, inalcanzable. Por debajo de
			    `xl` se mantiene en flujo normal (fila flex, junto al
			    formulario, compitiendo por el ancho disponible); solo a partir
			    de `xl` — donde sí sobra espacio horizontal a los lados del
			    bloque centrado — vuelve a flotar afuera con la posición
			    absoluta original. Sin cálculos de ancho por JS: es un cambio
			    puramente de CSS por punto de quiebre. */}
			<div className="mx-auto flex w-full max-w-3xl items-center gap-2 xl:relative xl:block">
				<div className="min-w-0 flex-1">{form}</div>
				{sideSlot && (
					<div className="pointer-events-auto shrink-0 xl:absolute xl:left-full xl:top-1/2 xl:-translate-y-1/2 xl:pl-[0.5cm]">
						{sideSlot}
					</div>
				)}
			</div>
			<p className="mt-2 text-center text-[11px] text-subtle">
				ATLAS puede equivocarse. Verifica las fuentes y no reemplaza un abogado · Shift + Enter para nueva línea
			</p>
		</div>
	);
}
