"use client";

import { motion } from "motion/react";
import { ChatInput } from "@/components/chat/ChatInput";

const EASE = [0.16, 1, 0.3, 1] as const;

const SEED_QUESTIONS = [
	"Me multaron por construir cerca a la playa, ¿qué hago?",
	"¿Puedo vender comida o alquilar carpas en la playa?",
	"¿De quién es la playa frente a mi casa o lote?",
	"Me dijeron que tengo que desalojar un predio costero, ¿es legal?",
] as const;

interface EmptyStateProps {
	input: string;
	loading: boolean;
	textareaRef: React.RefObject<HTMLTextAreaElement | null>;
	onChange: (value: string) => void;
	onSubmit: (value: string) => void;
}

export function EmptyState({
	input,
	loading,
	textareaRef,
	onChange,
	onSubmit,
}: EmptyStateProps) {
	return (
		<div className="relative flex flex-1 flex-col items-center justify-center px-4 pb-12 pt-8 sm:pt-12">
			{/* Glow ambiental — la firma visual, contenida detrás del input */}
			<div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden">
				<div className="relative h-[42vh] w-[64vw] max-h-[440px] max-w-[720px] translate-y-[2vh]">
					<div className="atlas-glow atlas-glow--intense" aria-hidden="true" />
				</div>
			</div>

			<motion.div
				className="relative z-10 flex w-full max-w-3xl flex-col items-center"
				initial={{ opacity: 0, y: 12 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.55, ease: EASE }}
			>
				<motion.h1
					className="text-center text-5xl font-medium tracking-tight text-foreground sm:text-6xl md:text-[4rem]"
					style={{ lineHeight: 1, letterSpacing: "-0.03em" }}
					translate="no"
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.6, delay: 0.08, ease: EASE }}
				>
					ATLAS
				</motion.h1>

				<motion.p
					className="mt-4 max-w-xl text-balance text-center text-[15px] leading-relaxed text-muted sm:text-base"
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.55, delay: 0.16, ease: EASE }}
				>
					Tu asistente para entender la jurisprudencia sobre playas y derecho
					costero en Colombia. Pregunta en lenguaje cotidiano y recibe una
					respuesta clara, con las sentencias que la respaldan.
				</motion.p>

				<motion.ul
					className="mt-10 flex w-full max-w-2xl flex-wrap justify-center gap-2"
					role="list"
					aria-label="Preguntas para empezar"
					initial="hidden"
					animate="show"
					variants={{
						hidden: {},
						show: { transition: { staggerChildren: 0.06, delayChildren: 0.24 } },
					}}
				>
					{SEED_QUESTIONS.map((q) => (
						<motion.li
							key={q}
							variants={{
								hidden: { opacity: 0, y: 8 },
								show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
							}}
						>
							<button
								type="button"
								onClick={() => {
									onChange(q);
									textareaRef.current?.focus();
								}}
								className="rounded-full border border-border bg-surface/40 px-3.5 py-2 text-sm leading-snug text-muted backdrop-blur-sm transition-all duration-150 hover:border-border-strong hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
							>
								{q}
							</button>
						</motion.li>
					))}
				</motion.ul>

				<motion.div
					className="mt-6 w-full"
					initial={{ opacity: 0, y: 12 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.55, delay: 0.42, ease: EASE }}
				>
					<ChatInput
						variant="hero"
						value={input}
						loading={loading}
						textareaRef={textareaRef}
						onChange={onChange}
						onSubmit={() => onSubmit(input)}
					/>
				</motion.div>

				<motion.p
					className="mt-6 max-w-md text-center text-xs leading-relaxed text-subtle"
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					transition={{ duration: 0.5, delay: 0.6 }}
				>
					ATLAS responde con base en sentencias del Consejo de Estado.
					No reemplaza la asesoría de un abogado.
				</motion.p>
			</motion.div>
		</div>
	);
}
