"use client";

interface ContextWarningProps {
  percent: number;
  onNewChat: () => void;
}

/**
 * Muestra un aviso cuando la conversación se acerca al límite de contexto del modelo.
 *
 * - 60–80 %: aviso suave — la calidad puede verse afectada.
 * - > 80 %:  aviso prominente — recomienda iniciar una nueva conversación.
 */
export function ContextWarning({ percent, onNewChat }: ContextWarningProps) {
  if (percent < 60) return null;

  const isCritical = percent >= 80;

  return (
    <div
      role="status"
      aria-live="polite"
      className="animate-fade-in mx-auto w-full max-w-3xl px-4 pb-2"
    >
      <div
        className="flex items-center gap-3 rounded-xl border px-4 py-2.5 text-xs"
        style={{
          background: "var(--accent-light)",
          borderColor: isCritical
            ? "color-mix(in srgb, var(--accent) 45%, transparent)"
            : "color-mix(in srgb, var(--accent) 25%, transparent)",
          color: "var(--accent)",
        }}
      >
        {/* Icono */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="shrink-0"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>

        {/* Mensaje */}
        <span className="flex-1 leading-snug" style={{ color: "color-mix(in srgb, var(--accent) 85%, var(--foreground))" }}>
          {isCritical
            ? "La conversación está llegando a su límite. Las respuestas pueden verse afectadas."
            : "La conversación es extensa. La calidad de las respuestas puede reducirse."}
        </span>

        {/* Botón — siempre visible, más prominente en nivel crítico */}
        <button
          onClick={onNewChat}
          className="shrink-0 rounded-lg px-2.5 py-1 font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1"
          style={{
            background: isCritical
              ? "color-mix(in srgb, var(--accent) 15%, transparent)"
              : "transparent",
            color: "var(--accent)",
          }}
          aria-label="Iniciar una nueva conversación"
        >
          Nueva conversación
        </button>
      </div>
    </div>
  );
}
