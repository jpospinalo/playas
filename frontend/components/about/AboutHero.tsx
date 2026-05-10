"use client";

import Link from "next/link";
import { motion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const;

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
};

export function AboutHero() {
  return (
    <motion.section
      className="mx-auto w-full max-w-5xl px-6 pb-16 pt-20 md:pt-28"
      variants={container}
      initial="hidden"
      animate="show"
    >
      <motion.p
        variants={item}
        className="mb-3 text-xs font-semibold uppercase tracking-widest text-accent"
      >
        Acerca de ATLAS
      </motion.p>

      <motion.h1
        variants={item}
        className="font-[family-name:var(--font-display)] text-balance mb-6 text-4xl font-semibold leading-[1.15] tracking-tight text-foreground md:text-5xl"
      >
        Un sistema agéntico para la jurisprudencia costera colombiana.
      </motion.h1>

      <motion.p
        variants={item}
        className="mb-8 max-w-2xl text-pretty text-lg leading-relaxed text-muted"
      >
        ATLAS combina recuperación híbrida, modelos de lenguaje y un corpus
        verificado de sentencias del Consejo de Estado para ofrecer respuestas
        jurídicas precisas, con cita explícita a sus fuentes.
      </motion.p>

      <motion.div variants={item}>
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-surface shadow-sm transition-colors duration-150 hover:bg-accent-bright focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
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
            <path d="m15 18-6-6 6-6" />
          </svg>
          Volver a ATLAS
        </Link>
      </motion.div>
    </motion.section>
  );
}
