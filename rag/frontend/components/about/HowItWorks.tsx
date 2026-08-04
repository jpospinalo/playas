"use client";

import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
};

const STEPS = [
  {
    number: "01",
    title: "Busco en los documentos",
    description:
      "Cuando preguntas algo, reviso las sentencias del Consejo de Estado y selecciono los fragmentos más relevantes para tu caso, combinando búsqueda por palabras clave y búsqueda semántica.",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    number: "02",
    title: "Referencio",
    description:
      "Uso fragmentos reales de las sentencias. No invento, ni hago afirmaciones legales sin un documento que las respalde.",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
        <path d="M9 10h6" />
        <path d="M9 14h4" />
      </svg>
    ),
  },
  {
    number: "03",
    title: "Respondo",
    description:
      "Redacto la respuesta en lenguaje cotidiano, con citas a las sentencias usadas. Cada cita es expandible: puedes ver el extracto exacto y verificarlo.",
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <path d="M8 10h8" />
        <path d="M8 14h5" />
      </svg>
    ),
  },
] as const;

export function HowItWorks() {
  return (
    <section
      className="mx-auto w-full max-w-5xl px-4 py-24 sm:px-6 lg:px-10 xl:px-16"
      aria-labelledby="how-it-works-heading"
    >
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.5, ease: EASE }}
        className="mx-auto max-w-2xl text-center"
      >
        <h2
          id="how-it-works-heading"
          className="text-balance text-4xl font-medium leading-tight tracking-tight text-accent md:text-5xl"
          style={{ letterSpacing: "-0.02em" }}
        >
          Cada respuesta se construye en tres pasos
        </h2>
      </motion.div>

      <motion.ol
        className="mt-14 grid gap-8 md:grid-cols-3"
        role="list"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        transition={{ staggerChildren: 0.12 }}
      >
        {STEPS.map((step) => (
          <motion.li
            key={step.number}
            className="flex flex-col gap-4 rounded-2xl border border-border bg-surface/40 p-6 backdrop-blur-sm"
            variants={fadeUp}
          >
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
                aria-hidden="true"
              >
                {step.icon}
              </div>
              <span
                className="font-mono text-xs text-subtle"
                aria-hidden="true"
              >
                {step.number}
              </span>
            </div>
            <h3 className="text-balance text-lg font-semibold text-foreground">
              {step.title}
            </h3>
            <p className="text-sm leading-relaxed text-muted">
              {step.description}
            </p>
          </motion.li>
        ))}
      </motion.ol>
    </section>
  );
}
