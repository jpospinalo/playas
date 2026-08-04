"use client";

import Image from "next/image";
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
		<div className="relative flex flex-1 flex-col items-center justify-start px-4 pb-12 pt-[3vh] sm:px-6 sm:pt-[4vh] lg:px-10 xl:px-16">
			{/* Glow ambiental — la firma visual, contenida detrás del input */}
			<div className="pointer-events-none absolute inset-0 flex items-start justify-center overflow-hidden">
				<div className="relative h-[42vh] w-[64vw] max-h-[440px] max-w-[720px] translate-y-[14vh]">
					<div className="atlas-glow atlas-glow--intense" aria-hidden="true" />
				</div>
			</div>

			<motion.div
				className="relative z-10 flex w-full max-w-3xl flex-col items-center"
				initial={{ opacity: 0, y: 12 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.55, ease: EASE }}
			>
				<motion.div
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.6, delay: 0.02, ease: EASE }}
				>
					<Image
						src="/brand/atlas-logo-full-v2.png"
						alt="ATLAS"
						width={204}
						height={208}
						className="h-[190px] w-auto sm:h-[220px]"
						priority
					/>
				</motion.div>

				<motion.h1
					className="mt-4 text-center text-5xl font-medium tracking-tight text-accent sm:text-6xl md:text-[4rem]"
					style={{ lineHeight: 1, letterSpacing: "-0.03em" }}
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.6, delay: 0.08, ease: EASE }}
				>
					Bienvenido
				</motion.h1>

				<motion.p
					className="mt-4 max-w-xl text-balance text-center text-[15px] leading-relaxed text-muted sm:text-base"
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.55, delay: 0.16, ease: EASE }}
				>
					Soy tu asistente para consultar jurisprudencia y derecho de playas
					costeras en Colombia.
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
					Respondo con base en sentencias del Consejo de Estado. No reemplazo
					la asesoría de un abogado.
				</motion.p>
			</motion.div>
		</div>
	);
}
