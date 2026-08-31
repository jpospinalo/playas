"use client";

import { motion, AnimatePresence } from "motion/react";
import { TypingDots } from "@/components/chat/TypingDots";

interface LoadingBubbleProps {
  /** Optional live status label (from the agent's current stage). */
  label?: string | null;
}

export function LoadingBubble({ label }: LoadingBubbleProps) {
  return (
    <motion.div
      className="flex justify-start"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="flex items-center gap-3 py-2">
        <TypingDots />
        <AnimatePresence mode="wait">
          {label ? (
            <motion.span
              key={label}
              className="text-xs text-muted"
              // Sin `aria-live` propio: ChatInterface ya expone una única
              // región de estado angosta (`role="status" aria-live="polite"`)
              // que anuncia el mismo progreso de la generación (ver
              // `streamingStatus` allí); una región viva aquí también
              // anunciaría cada cambio de etapa dos veces. Este `<span>`
              // sigue siendo el texto VISIBLE junto a los puntos de carga,
              // sin convertirse en una región viva propia.
              initial={{ opacity: 0, x: 4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              {label}
            </motion.span>
          ) : (
            // Sin `label` no hay ningún texto visible junto a los puntos de
            // carga: este `sr-only` es la única forma en que un lector de
            // pantalla se entera de que hay una generación en curso. Con
            // `label` presente, el `motion.span` de arriba ya expone ese
            // mismo texto — repetirlo aquí duplicaba el nombre accesible.
            <span className="sr-only">
              Buscando fuentes jurídicas relevantes…
            </span>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
