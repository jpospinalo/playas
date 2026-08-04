"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";

type Variant = "hero" | "docked";

interface ChatInputProps {
	value: string;
	loading: boolean;
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
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			onSubmit();
		}
	}

	const trimmed = value.trim();
	const canSend = !loading && trimmed.length > 0;
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
					className="min-w-0 flex-1 resize-none bg-transparent py-1 text-[15px] leading-6 text-foreground placeholder:text-subtle focus:outline-none disabled:opacity-50"
					style={{ overflowY: "hidden" }}
				/>
				<button
					type="submit"
					disabled={!canSend}
					aria-label={loading ? "Consultando…" : "Enviar consulta"}
					onClick={() => canSend && setSwing((s) => s + 1)}
					className={`flex h-8 w-8 shrink-0 items-center justify-center self-end rounded-xl transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
						canSend
							? "bg-accent text-accent-fg hover:bg-accent-hover"
							: "bg-elevated text-subtle"
					}`}
				>
					{loading ? (
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
			<div className="relative mx-auto w-full max-w-3xl">
				{form}
				{sideSlot && (
					<div className="pointer-events-auto absolute left-full top-1/2 -translate-y-1/2 pl-[0.5cm]">
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
