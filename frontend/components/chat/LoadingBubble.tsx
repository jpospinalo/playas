import { TypingDots } from "@/components/chat/TypingDots";

interface LoadingBubbleProps {
  /** Optional live status label (from the agent's current stage). */
  label?: string | null;
}

export function LoadingBubble({ label }: LoadingBubbleProps) {
  const visibleLabel = label ?? "Consultando jurisprudencia…";
  return (
    <div className="flex justify-start animate-message-in">
      <div
        className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm bg-surface px-5 py-4 shadow-sm"
        style={{
          border: "1px solid var(--border)",
          borderLeftColor: "var(--accent)",
          borderLeftWidth: "2px",
        }}
      >
        <TypingDots />
        {label ? (
          <span
            key={label}
            className="animate-message-in text-xs text-muted"
            aria-live="polite"
          >
            {label}
          </span>
        ) : null}
        <span className="sr-only">{visibleLabel}</span>
      </div>
    </div>
  );
}
