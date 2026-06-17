"use client";

import { motion } from "motion/react";
import { ChatInput } from "@/components/chat/ChatInput";

const EASE = [0.16, 1, 0.3, 1] as const;

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

				<motion.div
					className="mt-10 w-full"
					initial={{ opacity: 0, y: 12 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.55, delay: 0.28, ease: EASE }}
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
					transition={{ duration: 0.5, delay: 0.44 }}
				>
					ATLAS responde con base en sentencias del Consejo de Estado.
					No reemplaza la asesoría de un abogado.
				</motion.p>
			</motion.div>
		</div>
	);
}
