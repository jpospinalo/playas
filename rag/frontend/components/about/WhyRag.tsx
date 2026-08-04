"use client";

import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

export function WhyRag() {
  return (
    <section
      className="mx-auto w-full max-w-5xl px-4 py-24 sm:px-6 lg:px-10 xl:px-16"
      aria-labelledby="why-rag-heading"
    >
      <motion.div
        className="mx-auto max-w-2xl text-center"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.55, ease: EASE }}
      >
        <h2
          id="why-rag-heading"
          className="text-balance text-4xl font-medium leading-tight tracking-tight text-accent md:text-5xl"
          style={{ letterSpacing: "-0.02em" }}
        >
          No invento. Cito
        </h2>
      </motion.div>

      <div className="mt-10 grid gap-8 md:grid-cols-[1fr_320px] md:items-start">
        <motion.p
          className="text-base leading-relaxed text-muted"
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55, ease: EASE }}
        >
          Los asistentes de IA tradicionales a veces se inventan información,
          sobre todo en temas legales donde un detalle mal dicho puede tener
          consecuencias. Estoy diseñado para que eso no pase: cada afirmación
          que hago está respaldada por una sentencia real que puedes abrir y
          verificar.
        </motion.p>

        <motion.aside
          className="flex items-center gap-4 rounded-2xl border border-border bg-surface/40 p-5 backdrop-blur-sm"
          aria-label="Principio fundamental"
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55, ease: EASE, delay: 0.12 }}
        >
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-secondary-yellow-soft text-secondary-yellow"
            aria-hidden="true"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <p className="text-sm font-medium leading-snug text-foreground">
            Si no encuentro la base de referencia documental, lo informo.
          </p>
        </motion.aside>
      </div>
    </section>
  );
}
