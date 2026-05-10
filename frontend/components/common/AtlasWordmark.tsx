export function AtlasWordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`font-[family-name:var(--font-display)] font-medium tracking-[0.06em] uppercase leading-none text-foreground ${className}`}
      translate="no"
    >
      ATLAS
    </span>
  );
}
