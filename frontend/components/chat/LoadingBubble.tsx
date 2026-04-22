"use client";

import { motion, AnimatePresence } from "motion/react";
import { TypingDots } from "@/components/chat/TypingDots";

interface LoadingBubbleProps {
  /** Optional live status label (from the agent's current stage). */
  label?: string | null;
}

export function LoadingBubble({ label }: LoadingBubbleProps) {
  const visibleLabel = label ?? "Consultando jurisprudencia…";
  return (
    <motion.div
      className="flex justify-start"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      <div
        className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm bg-surface px-5 py-4 shadow-sm"
        style={{
          border: "1px solid var(--border)",
          borderLeftColor: "var(--navy)",
          borderLeftWidth: "3px",
        }}
      >
        <TypingDots />
        <AnimatePresence mode="wait">
          {label ? (
            <motion.span
              key={label}
              className="text-xs text-muted"
              aria-live="polite"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              {label}
            </motion.span>
          ) : null}
        </AnimatePresence>
        <span className="sr-only">{visibleLabel}</span>
      </div>
    </motion.div>
  );
}
