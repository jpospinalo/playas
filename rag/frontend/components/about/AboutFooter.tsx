export function AboutFooter() {
  return (
    <footer className="mt-12">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-y-2 px-6 py-6 text-xs text-subtle">
        <span className="flex items-center gap-1.5">
          <span
            className="font-medium tracking-[0.18em] text-foreground"
            translate="no"
          >
            ATLAS
          </span>
          <span aria-hidden="true">·</span>
          <span>© {new Date().getFullYear()}</span>
        </span>
        <span>Jurisprudencia costera colombiana</span>
      </div>
    </footer>
  );
}
