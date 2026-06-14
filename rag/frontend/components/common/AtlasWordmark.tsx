export function AtlasWordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`font-medium tracking-[0.18em] uppercase leading-none text-foreground ${className}`}
      translate="no"
    >
      ATLAS
    </span>
  );
}
