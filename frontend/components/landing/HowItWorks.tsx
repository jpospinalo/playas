"use client";

import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
};

const STEPS = [
  {
    number: "1",
    title: "Recuperación",
    description:
      "Ante su consulta, el sistema realiza una búsqueda híbrida —léxica BM25 y semántica vectorial— sobre el corpus de jurisprudencia, identificando los fragmentos más relevantes.",
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
    number: "2",
    title: "Aumentación",
    description:
      "Solo los fragmentos verificados del corpus legal se incorporan como contexto al modelo. El modelo no puede ir más allá de las fuentes recuperadas.",
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
    number: "3",
    title: "Generación",
    description:
      "El modelo redacta una respuesta en lenguaje jurídico natural, siempre con referencia explícita a los documentos fuente utilizados.",
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
      className="mx-auto w-full max-w-5xl px-6 py-24"
      aria-labelledby="how-it-works-heading"
    >
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.5, ease: EASE }}
      >
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-accent">
          Cómo funciona
        </p>
        <h2
          id="how-it-works-heading"
          className="font-[family-name:var(--font-display)] mb-14 max-w-xl text-pretty text-3xl font-semibold leading-snug text-foreground"
        >
          Arquitectura RAG: respuestas ancladas en documentos reales.
        </h2>
      </motion.div>

      <motion.ol
        className="relative grid gap-10 md:grid-cols-3"
        role="list"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        transition={{ staggerChildren: 0.14 }}
      >
        {/* Connecting line — desktop only */}
        <li
          aria-hidden="true"
          className="pointer-events-none absolute left-0 right-0 top-[22px] hidden border-t border-dashed border-border md:block"
          style={{ left: "calc(1/6 * 100%)", right: "calc(1/6 * 100%)" }}
        />

        {STEPS.map((step) => (
          <motion.li key={step.number} className="flex flex-col gap-4" variants={fadeUp}>
            <div className="relative flex items-center gap-3">
              <div
                className="relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-accent shadow-sm"
                aria-hidden="true"
              >
                {step.icon}
              </div>
              <span
                className="font-[family-name:var(--font-display)] text-2xl font-semibold text-border select-none"
                aria-hidden="true"
              >
                {step.number}
              </span>
            </div>
            <h3 className="font-[family-name:var(--font-display)] text-balance text-xl font-semibold text-foreground">
              {step.title}
            </h3>
            <p className="text-sm leading-relaxed text-muted">{step.description}</p>
          </motion.li>
        ))}
      </motion.ol>
    </section>
  );
}
