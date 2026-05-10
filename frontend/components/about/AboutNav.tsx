"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { AtlasWordmark } from "@/components/common/AtlasWordmark";

const EASE = [0.16, 1, 0.3, 1] as const;

export function AboutNav() {
  return (
    <motion.header
      className="sticky top-0 z-50 border-b border-border bg-surface/95 backdrop-blur-sm"
      initial={{ y: -8, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      <nav
        className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4"
        aria-label="Navegación principal"
      >
        <Link
          href="/"
          className="rounded-md px-1 py-0.5 transition-opacity duration-150 hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          aria-label="ATLAS — inicio"
        >
          <AtlasWordmark className="text-lg" />
        </Link>
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-bright focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          >
            Iniciar consulta
          </Link>
        </div>
      </nav>
    </motion.header>
  );
}
