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
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-accent">
            Por qué RAG
          </p>
          <h2
            id="why-rag-heading"
            className="font-[family-name:var(--font-display)] text-balance mb-6 text-3xl font-semibold leading-snug text-foreground"
          >
            La tecnología idónea para el ejercicio del derecho.
          </h2>
          <p className="mb-4 text-base leading-relaxed text-muted">
            Los modelos de lenguaje generativo pueden «alucinar» —fabricar
            referencias inexistentes o distorsionar hechos—, un riesgo
            inaceptable en el ámbito jurídico. La arquitectura RAG elimina ese
            riesgo al vincular cada respuesta a fragmentos reales del corpus: si
            la información no está en la base documental, el sistema lo indica.
          </p>
          <p className="text-base leading-relaxed text-muted">
            El resultado es un asistente que actúa como un colaborador que ha
            leído toda la jurisprudencia disponible y cita sus fuentes con
            precisión, liberando al profesional para centrarse en el análisis y
            la estrategia.
          </p>
        </motion.div>

        {/* Callout card — slides in from the right */}
        <motion.aside
          className="rounded-xl border border-accent/20 bg-accent-light px-6 py-5 md:w-64"
          aria-label="Principio fundamental"
          initial={{ opacity: 0, x: 24 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55, ease: EASE, delay: 0.12 }}
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
            className="mb-3 text-accent"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          <p className="font-[family-name:var(--font-display)] text-base font-semibold leading-snug text-foreground">
            «Si la información no está en el corpus, el sistema lo declara
            expresamente.»
          </p>
          <p className="mt-2 text-xs leading-relaxed text-accent/80">
            Principio de honestidad epistémica del sistema RAG.
          </p>
        </motion.aside>
      </div>
    </section>
  );
}
