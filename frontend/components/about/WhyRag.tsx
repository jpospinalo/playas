"use client";

import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

export function WhyRag() {
  return (
    <section
      className="mx-auto w-full max-w-5xl px-6 py-24"
      aria-labelledby="why-rag-heading"
    >
      <div className="grid gap-10 md:grid-cols-[1fr_auto] md:items-start">
        <motion.div
          className="max-w-2xl"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55, ease: EASE }}
        >
          <p className="mb-3 text-xs font-medium text-accent">
            Por qué confiar
          </p>
          <h2
            id="why-rag-heading"
            className="text-balance text-3xl font-medium leading-tight tracking-tight text-foreground md:text-4xl"
            style={{ letterSpacing: "-0.02em" }}
          >
            ATLAS no inventa, ATLAS cita.
          </h2>
          <p className="mt-6 text-base leading-relaxed text-muted">
            Los asistentes de IA tradicionales a veces se inventan información,
            sobre todo en temas legales donde un detalle mal dicho puede tener
            consecuencias. ATLAS está diseñado para que eso no pase: cada cosa
            que afirma debe estar respaldada por una sentencia real que puedas
            abrir y verificar.
          </p>
          <p className="mt-4 text-base leading-relaxed text-muted">
            Si tu pregunta no tiene respuesta en el corpus, ATLAS te lo dice en
            vez de improvisar. Eso lo hace una primera puerta confiable cuando
            quieres entender tus derechos sobre playas y zonas costeras, sin
            necesidad de saber leer un fallo judicial.
          </p>
        </motion.div>

        <motion.aside
          className="rounded-2xl border border-border bg-surface/40 p-6 backdrop-blur-sm md:w-72"
          aria-label="Principio fundamental"
          initial={{ opacity: 0, x: 24 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55, ease: EASE, delay: 0.12 }}
        >
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft" aria-hidden="true">
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
              className="text-accent"
              aria-hidden="true"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <p className="text-base font-medium leading-snug text-foreground">
            Si la información no está en el corpus, ATLAS lo dice.
          </p>
          <p className="mt-3 text-xs leading-relaxed text-subtle">
            No inventamos respuestas para parecer útiles. La honestidad sobre
            los límites es parte del producto.
          </p>
        </motion.aside>
      </div>
    </section>
  );
}
