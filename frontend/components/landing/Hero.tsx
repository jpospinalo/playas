import Link from "next/link";

function ShieldCheckIcon() {
  return (
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
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function Hero() {
  return (
    <section className="mx-auto w-full max-w-5xl px-6 pb-28 pt-20 md:pt-36">
      {/* Trust badge */}
      <div className="mb-7 inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-light px-3 py-1 text-xs font-semibold text-accent">
        <ShieldCheckIcon />
        Fuentes verificadas · Consejo de Estado de Colombia
      </div>

      <h1 className="font-[family-name:var(--font-display)] text-balance mb-7 text-5xl font-semibold leading-[1.15] tracking-tight text-foreground md:text-6xl lg:text-[4.25rem]">
        La jurisprudencia costera
        <br className="hidden md:block" />
        <span className="text-navy"> al alcance de su consulta.</span>
      </h1>

      <p className="mb-10 max-w-2xl text-pretty text-lg leading-relaxed text-muted">
        Acceda a jurisprudencia colombiana sobre playas, bienes de uso público
        costero y derecho marítimo. Respuestas fundamentadas en fuentes
        verificadas, sin búsquedas manuales, sin ambigüedad.
      </p>

      <div className="flex flex-wrap items-center gap-4">
        <Link
          href="/chat"
          className="inline-flex items-center gap-2 rounded-md bg-navy px-6 py-3 text-sm font-medium text-white shadow-sm transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
        >
          Consultar jurisprudencia
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </Link>
        <a
          href="#how-it-works-heading"
          className="text-sm font-medium text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 rounded-sm"
        >
          Conocer la metodología
        </a>
      </div>

      {/* Metadata row */}
      <div className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border pt-6 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-accent/60" aria-hidden="true" />
          Búsqueda híbrida BM25 + vectorial
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-accent/60" aria-hidden="true" />
          Citas a fuentes con referencia explícita
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-accent/60" aria-hidden="true" />
          Sin alucinaciones — respuestas ancladas al corpus
        </span>
      </div>
    </section>
  );
}
