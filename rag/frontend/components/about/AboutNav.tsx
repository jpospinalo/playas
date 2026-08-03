"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { AtlasWordmark } from "@/components/common/AtlasWordmark";

const EASE = [0.16, 1, 0.3, 1] as const;

export function AboutNav() {
  return (
    <motion.header
      className="sticky top-0 z-50 bg-background/70 backdrop-blur-md"
      initial={{ y: -8, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      <nav
        className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6 lg:px-10 xl:px-16"
        aria-label="Navegación principal"
      >
        <Link
          href="/"
          className="flex items-center gap-2 rounded-full px-1 py-0.5 transition-opacity duration-150 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          aria-label="ATLAS — inicio"
        >
          <AtlasWordmark iconSize={26} />
        </Link>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-colors duration-150 hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Empezar a preguntar
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="13"
            height="13"
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
      </nav>
    </motion.header>
  );
}
