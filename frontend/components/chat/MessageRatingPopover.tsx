"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";

interface MessageRatings {
	pertinence: number;
	accuracy: number;
}

interface MessageRatingPopoverProps {
	open: boolean;
	onSubmit: (ratings: MessageRatings, expectedAnswer?: string) => Promise<void>;
	onClose: () => void;
}

const RATING_LABELS: Record<number, string> = {
	1: "Muy malo",
	2: "Malo",
	3: "Regular",
	4: "Bueno",
	5: "Excelente",
};

const TOOLTIP_TEXT: Record<string, string> = {
	pertinence:
		"¿Qué tan relevante fue la respuesta para la pregunta que hicaste? Un 1 indica que no tuvo nada que ver; un 5 indica que fue directamente relevante.",
	accuracy:
		"¿La respuesta contiene la información necesaria y está completa para responder la pregunta? Un 1 indica que le faltó información clave; un 5 indica que fue una respuesta completa.",
};

type SubmitState = "idle" | "loading" | "success" | "error";

function StarRow({
	label,
	value,
	onChange,
	disabled,
	tooltipText,
}: {
	label: string;
	value: number;
	onChange: (v: number) => void;
	disabled: boolean;
	tooltipText: string;
}) {
	const [hovered, setHovered] = useState(0);
	const [showTooltip, setShowTooltip] = useState(false);
	const activeVal = hovered || value;
	const tooltipId = `tooltip-msg-${label.toLowerCase().replace(/\s+/g, "-")}`;

	return (
		<div className="relative">
			<div className="mb-1.5 flex items-center gap-1.5">
				<label className="text-sm font-medium text-foreground">{label}</label>
				<button
					type="button"
					className="rounded-full text-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
					onMouseEnter={() => setShowTooltip(true)}
					onMouseLeave={() => setShowTooltip(false)}
					onFocus={() => setShowTooltip(true)}
					onBlur={() => setShowTooltip(false)}
					aria-describedby={tooltipId}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="14"
						height="14"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
						aria-hidden="true"
					>
						<circle cx="12" cy="12" r="10" />
						<path d="M12 16v-4" />
						<path d="M12 8h.01" />
					</svg>
				</button>
				<AnimatePresence>
					{showTooltip && (
						<motion.div
							id={tooltipId}
							role="tooltip"
							className="absolute left-0 top-8 z-50 max-w-[260px] rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted shadow-lg"
							initial={{ opacity: 0, y: -4 }}
							animate={{ opacity: 1, y: 0 }}
							exit={{ opacity: 0, y: -4 }}
							transition={{ duration: 0.15 }}
						>
							{tooltipText}
						</motion.div>
					)}
				</AnimatePresence>
			</div>
			<div className="flex items-center gap-2" role="group" aria-label={label}>
				<div className="flex gap-1.5">
					{[1, 2, 3, 4, 5].map((star) => (
						<button
							key={star}
							type="button"
							aria-label={`${star} estrella${star > 1 ? "s" : ""}`}
							aria-pressed={value === star}
							onClick={() => onChange(star)}
							onMouseEnter={() => setHovered(star)}
							onMouseLeave={() => setHovered(0)}
							disabled={disabled}
							className="transition-transform duration-100 hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:pointer-events-none"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="28"
								height="28"
								viewBox="0 0 24 24"
								aria-hidden="true"
								className="transition-colors duration-100"
								fill={star <= activeVal ? "currentColor" : "none"}
								stroke="currentColor"
								strokeWidth="1.5"
								strokeLinecap="round"
								strokeLinejoin="round"
								style={{
									color:
										star <= activeVal
											? "var(--color-accent)"
											: "var(--color-muted)",
								}}
							>
								<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
							</svg>
						</button>
					))}
				</div>
				<div className="min-w-[4rem]">
					<AnimatePresence mode="wait">
						{activeVal > 0 && (
							<motion.p
								key={activeVal}
								className="text-xs font-medium text-accent"
								initial={{ opacity: 0, y: -4 }}
								animate={{ opacity: 1, y: 0 }}
								exit={{ opacity: 0, y: 4 }}
								transition={{ duration: 0.15 }}
							>
								{RATING_LABELS[activeVal]}
							</motion.p>
						)}
					</AnimatePresence>
				</div>
			</div>
		</div>
	);
}

export function MessageRatingPopover({
	open,
	onSubmit,
	onClose,
}: MessageRatingPopoverProps) {
	const [pertinence, setPertinence] = useState(0);
	const [accuracy, setAccuracy] = useState(0);
	const [expectedAnswer, setExpectedAnswer] = useState("");
	const [submitState, setSubmitState] = useState<SubmitState>("idle");

	const allRated = pertinence > 0 && accuracy > 0;

	function handleClose() {
		if (submitState === "loading") return;
		if (submitState !== "success") {
			setPertinence(0);
			setAccuracy(0);
			setExpectedAnswer("");
			setSubmitState("idle");
		}
		onClose();
	}

	function handleExited() {
		setPertinence(0);
		setAccuracy(0);
		setExpectedAnswer("");
		setSubmitState("idle");
	}

	const handleSubmit = useCallback(
		async (e: React.FormEvent) => {
			e.preventDefault();
			if (!allRated || submitState === "loading") return;

			setSubmitState("loading");
			try {
				await onSubmit(
					{ pertinence, accuracy },
					expectedAnswer.trim() || undefined,
				);
				setSubmitState("success");
			} catch {
				setSubmitState("error");
			}
		},
		[allRated, submitState, pertinence, accuracy, expectedAnswer, onSubmit],
	);

	return (
		<AnimatePresence onExitComplete={handleExited}>
			{open && (
				<motion.div
					className="fixed inset-0 z-50 flex items-center justify-center p-4"
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					exit={{ opacity: 0 }}
					transition={{ duration: 0.2 }}
				>
					{/* Fondo oscuro con blur */}
					<motion.div
						className="absolute inset-0 bg-black/50 backdrop-blur-sm"
						onClick={handleClose}
						aria-hidden="true"
					/>

					{/* Tarjeta del dialog */}
					<motion.div
						role="dialog"
						aria-modal="true"
						aria-labelledby="msg-rating-title"
						className="relative z-10 w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-xl"
						initial={{ opacity: 0, scale: 0.96, y: 8 }}
						animate={{ opacity: 1, scale: 1, y: 0 }}
						exit={{ opacity: 0, scale: 0.96, y: 8 }}
						transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
					>
						{/* Botón cerrar */}
						{submitState !== "loading" && (
							<button
								onClick={handleClose}
								aria-label="Cerrar"
								className="absolute right-4 top-4 rounded-md p-1 text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									width="16"
									height="16"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth="2"
									strokeLinecap="round"
									strokeLinejoin="round"
									aria-hidden="true"
								>
									<path d="M18 6 6 18M6 6l12 12" />
								</svg>
							</button>
						)}

						<AnimatePresence mode="wait">
							{submitState === "success" ? (
								/* Estado de éxito */
								<motion.div
									key="success"
									className="flex flex-col items-center gap-3 py-4 text-center"
									initial={{ opacity: 0, scale: 0.9 }}
									animate={{ opacity: 1, scale: 1 }}
									exit={{ opacity: 0 }}
									transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
								>
									<div className="flex h-12 w-12 items-center justify-center rounded-full bg-success-bg text-success">
										<svg
											xmlns="http://www.w3.org/2000/svg"
											width="22"
											height="22"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											strokeWidth="2.5"
											strokeLinecap="round"
											strokeLinejoin="round"
											aria-hidden="true"
										>
											<path d="M20 6 9 17l-5-5" />
										</svg>
									</div>
									<div>
										<p className="font-[family-name:var(--font-display)] font-semibold text-foreground">
											¡Gracias por tu calificación!
										</p>
										<p className="mt-1 text-sm text-muted">
											Tu opinión nos ayuda a mejorar el sistema.
										</p>
									</div>
									<button
										onClick={handleClose}
										className="mt-2 rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
									>
										Cerrar
									</button>
								</motion.div>
							) : (
								/* Formulario */
								<motion.div
									key="form"
									initial={{ opacity: 1 }}
									exit={{ opacity: 0 }}
								>
									<h2
										id="msg-rating-title"
										className="mb-1 font-[family-name:var(--font-display)] text-lg font-semibold text-foreground"
									>
										Calificar esta respuesta
									</h2>
									<p className="mb-5 text-sm text-muted">
										Tu calificación ayuda a mejorar la calidad de las
										respuestas.
									</p>

									<form
										onSubmit={handleSubmit}
										noValidate
										className="space-y-4"
									>
										<StarRow
											label="Pertinencia de la respuesta"
											value={pertinence}
											onChange={setPertinence}
											disabled={submitState === "loading"}
											tooltipText={TOOLTIP_TEXT.pertinence}
										/>

										<StarRow
											label="Precisión de la respuesta"
											value={accuracy}
											onChange={setAccuracy}
											disabled={submitState === "loading"}
											tooltipText={TOOLTIP_TEXT.accuracy}
										/>

										<div>
											<label
												htmlFor="expected-answer"
												className="mb-1 block text-sm font-medium text-foreground"
											>
												Respuesta adecuada{" "}
												<span className="font-normal text-muted">
													(opcional)
												</span>
											</label>
											<textarea
												id="expected-answer"
												rows={3}
												maxLength={1000}
												value={expectedAnswer}
												onChange={(e) => setExpectedAnswer(e.target.value)}
												placeholder="Escribe la respuesta correcta que esperabas del sistema."
												disabled={submitState === "loading"}
												className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60"
											/>
										</div>

										<AnimatePresence>
											{submitState === "error" && (
												<motion.p
													role="alert"
													className="rounded-lg border border-danger/30 bg-danger-bg px-3 py-2 text-sm text-danger"
													initial={{ opacity: 0, y: -4 }}
													animate={{ opacity: 1, y: 0 }}
													exit={{ opacity: 0 }}
													transition={{ duration: 0.2 }}
												>
													No se pudo enviar la calificación. Intenta de nuevo.
												</motion.p>
											)}
										</AnimatePresence>

										<div className="flex items-center gap-3">
											<button
												type="button"
												onClick={handleClose}
												disabled={submitState === "loading"}
												className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1"
											>
												Cancelar
											</button>
											<button
												type="submit"
												disabled={!allRated || submitState === "loading"}
												className="flex-1 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:opacity-50"
											>
												{submitState === "loading" ? "Enviando…" : "Enviar"}
											</button>
										</div>
									</form>
								</motion.div>
							)}
						</AnimatePresence>
					</motion.div>
				</motion.div>
			)}
		</AnimatePresence>
	);
}
