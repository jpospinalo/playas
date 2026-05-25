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
    <section className="relative overflow-hidden">
      {/* Glow ambiental — firma visual, sutil detrás del título */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden="true">
        <div className="relative h-[50vh] w-[70vw] max-h-[480px] max-w-[820px] -translate-y-[8vh]">
          <div className="atlas-glow" />
        </div>
      </div>

      <motion.div
        className="relative mx-auto w-full max-w-3xl px-6 pb-20 pt-24 text-center md:pt-32"
        variants={container}
        initial="hidden"
        animate="show"
      >
        <motion.span
          variants={item}
          className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/40 px-3 py-1 text-[11px] font-medium text-muted backdrop-blur-sm"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
          Cómo funciona ATLAS
        </motion.span>

        <motion.h1
          variants={item}
          className="text-balance text-4xl font-medium leading-[1.05] tracking-tight text-foreground md:text-6xl"
          style={{ letterSpacing: "-0.025em" }}
        >
          Respuestas claras sobre playas, ancladas en sentencias reales.
        </motion.h1>

        <motion.p
          variants={item}
          className="mx-auto mt-6 max-w-xl text-balance text-base leading-relaxed text-muted md:text-lg"
        >
          ATLAS lee la jurisprudencia colombiana sobre playas y derecho costero,
          y te la traduce a un lenguaje que puedes entender, citando siempre las
          sentencias que respaldan cada cosa que dice.
        </motion.p>

        <motion.div variants={item} className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-fg transition-colors duration-150 hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Hacer una consulta
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M5 12h14" />
              <path d="m13 5 7 7-7 7" />
            </svg>
          </Link>
          <a
            href="#how-it-works-heading"
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/40 px-5 py-2.5 text-sm font-medium text-muted backdrop-blur-sm transition-colors duration-150 hover:border-border-strong hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Ver cómo funciona
          </a>
        </motion.div>
      </motion.div>
    </section>
  );
}
