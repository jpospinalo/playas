import Link from "next/link";

function ScalesIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="text-accent shrink-0"
    >
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  );
}

export function LandingNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-surface/95 backdrop-blur-sm shadow-[0_1px_0_0_var(--border)]">
      <nav
        className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4"
        aria-label="Navegación principal"
      >
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md px-1 py-0.5 transition-opacity duration-150 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          aria-label="Agente de Jurisprudencia Costera — inicio"
        >
          <ScalesIcon />
          <span
            className="font-[family-name:var(--font-display)] text-base font-semibold tracking-wide text-foreground"
            translate="no"
          >
            Agente de Jurisprudencia <span className="text-accent">Costera</span>
          </span>
        </Link>
        <Link
          href="/chat"
          className="rounded-md bg-navy px-4 py-1.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
        >
          Iniciar consulta
        </Link>
      </nav>
    </header>
  );
}
