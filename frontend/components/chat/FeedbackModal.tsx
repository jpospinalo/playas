"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { submitFeedback } from "@/lib/api";

interface FeedbackModalProps {
  open: boolean;
  conversationId?: string | null;
  onClose: () => void;
}

type SubmitState = "idle" | "loading" | "success" | "error";

export function FeedbackModal({ open, conversationId, onClose }: FeedbackModalProps) {
  const [hovered, setHovered] = useState<number>(0);
  const [selected, setSelected] = useState<number>(0);
  const [comment, setComment] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");

  function handleClose() {
    if (submitState === "loading") return;
    // Resetear estado al cerrar (salvo éxito — se limpia al reabrir)
    if (submitState !== "success") {
      setHovered(0);
      setSelected(0);
      setComment("");
      setSubmitState("idle");
    }
    onClose();
  }

  function handleExited() {
    // Limpiar estado después de que la animación de salida termine
    setHovered(0);
    setSelected(0);
    setComment("");
    setSubmitState("idle");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selected === 0 || submitState === "loading") return;

    setSubmitState("loading");
    try {
      await submitFeedback({
        rating: selected,
        comment: comment.trim() || undefined,
        conversation_id: conversationId ?? undefined,
      });
      setSubmitState("success");
    } catch {
      setSubmitState("error");
    }
  }

  const activeRating = hovered || selected;

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
          {/* Fondo oscuro */}
          <motion.div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={handleClose}
            aria-hidden="true"
          />

          {/* Tarjeta */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-modal-title"
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
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-600">
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
                <motion.div key="form" initial={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <h2
                    id="feedback-modal-title"
                    className="mb-1 font-[family-name:var(--font-display)] text-lg font-semibold text-foreground"
                  >
                    Califica el sistema
                  </h2>
                  <p className="mb-5 text-sm text-muted">
                    {conversationId
                      ? "Tu calificación se asociará a la conversación actual."
                      : "¿Qué tan útil fue el agente?"}
                  </p>

                  <form onSubmit={handleSubmit} noValidate className="space-y-5">
                    {/* Estrellas */}
                    <div className="flex justify-center gap-2" role="group" aria-label="Calificación">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          aria-label={`${star} estrella${star > 1 ? "s" : ""}`}
                          aria-pressed={selected === star}
                          onClick={() => setSelected(star)}
                          onMouseEnter={() => setHovered(star)}
                          onMouseLeave={() => setHovered(0)}
                          disabled={submitState === "loading"}
                          className="transition-transform duration-100 hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:pointer-events-none"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width="32"
                            height="32"
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                            className="transition-colors duration-100"
                            fill={star <= activeRating ? "currentColor" : "none"}
                            stroke="currentColor"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            style={{
                              color: star <= activeRating ? "var(--color-accent)" : "var(--color-muted)",
                            }}
                          >
                            <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
                          </svg>
                        </button>
                      ))}
                    </div>

                    {/* Etiqueta de la calificación seleccionada */}
                    <div className="h-4 text-center">
                      <AnimatePresence mode="wait">
                        {activeRating > 0 && (
                          <motion.p
                            key={activeRating}
                            className="text-xs font-medium text-accent"
                            initial={{ opacity: 0, y: -4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 4 }}
                            transition={{ duration: 0.15 }}
                          >
                            {ratingLabel(activeRating)}
                          </motion.p>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* Textarea */}
                    <div>
                      <label
                        htmlFor="feedback-comment"
                        className="mb-1 block text-xs font-medium text-muted"
                      >
                        Comentario <span className="font-normal">(opcional)</span>
                      </label>
                      <textarea
                        id="feedback-comment"
                        rows={3}
                        maxLength={500}
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="¿Qué podría mejorar el sistema?"
                        disabled={submitState === "loading"}
                        className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60"
                      />
                    </div>

                    {/* Error */}
                    <AnimatePresence>
                      {submitState === "error" && (
                        <motion.p
                          role="alert"
                          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.2 }}
                        >
                          No se pudo enviar el feedback. Intenta de nuevo.
                        </motion.p>
                      )}
                    </AnimatePresence>

                    <button
                      type="submit"
                      disabled={selected === 0 || submitState === "loading"}
                      className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:opacity-50"
                    >
                      {submitState === "loading" ? "Enviando…" : "Enviar calificación"}
                    </button>
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

function ratingLabel(rating: number): string {
  const labels: Record<number, string> = {
    1: "Muy malo",
    2: "Malo",
    3: "Regular",
    4: "Bueno",
    5: "Excelente",
  };
  return labels[rating] ?? "";
}
