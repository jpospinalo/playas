"use client";

import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.15 } },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
};

const EXAMPLE_QUESTIONS = [
  "¿Cuál es el régimen jurídico de las playas en Colombia?",
  "¿Qué regula la Ley 99 de 1993 en materia de zonas costeras?",
  "¿Cómo se tramita una concesión sobre bienes de uso público costero?",
] as const;

interface EmptyStateProps {
  onSelectExample: (question: string) => void;
}

export function EmptyState({ onSelectExample }: EmptyStateProps) {
  return (
    <motion.div
      className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center"
      variants={container}
      initial="hidden"
      animate="show"
    >
      {/* Scales icon — spring pop */}
      <motion.div
        className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface shadow-sm"
        aria-hidden="true"
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 280, damping: 18, delay: 0.05 }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-accent"
        >
          <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
          <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
          <path d="M7 21h10" />
          <path d="M12 3v18" />
          <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
        </svg>
      </motion.div>

      <motion.h2
        variants={item}
        className="font-[family-name:var(--font-display)] mb-2 text-xl font-semibold text-foreground"
      >
        Asistente de Jurisprudencia Costera
      </motion.h2>

      <motion.p variants={item} className="mb-1 max-w-xs text-sm leading-relaxed text-muted">
        Consultas respondidas con base exclusiva en el corpus de
        jurisprudencia colombiana indexado.
      </motion.p>

      <motion.p variants={item} className="mb-8 max-w-xs text-xs leading-relaxed text-muted/60">
        Cada respuesta incluye referencia explícita a las fuentes utilizadas.
      </motion.p>

      <motion.p
        variants={item}
        className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted/50"
      >
        Consultas frecuentes
      </motion.p>

      <motion.ul
        className="flex w-full max-w-sm flex-col gap-2"
        role="list"
        aria-label="Consultas de ejemplo"
        variants={container}
      >
        {EXAMPLE_QUESTIONS.map((q) => (
          <motion.li key={q} variants={item}>
            <button
              type="button"
              onClick={() => onSelectExample(q)}
              className="group w-full rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm leading-snug text-muted transition-all duration-150 hover:border-accent/40 hover:bg-accent-light hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            >
              <span className="flex items-start gap-2.5">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="mt-0.5 shrink-0 text-accent/50 transition-colors duration-150 group-hover:text-accent"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                {q}
              </span>
            </button>
          </motion.li>
        ))}
      </motion.ul>
    </motion.div>
  );
}
