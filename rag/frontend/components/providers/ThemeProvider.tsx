"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import { MotionConfig } from "motion/react";

export { useTheme } from "next-themes";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {/* Respeta la preferencia de movimiento reducido del sistema en las
         animaciones administradas por motion/react (AnimatePresence,
         motion.div, etc.), que la regla `@media (prefers-reduced-motion:
         reduce)` de globals.css no alcanza a cubrir por sí sola. No
         garantiza que toda animación se vuelva instantánea: motion/react
         puede conservar efectos no basados en movimiento (opacidad, color)
         según cada transición. */}
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </NextThemesProvider>
  );
}
