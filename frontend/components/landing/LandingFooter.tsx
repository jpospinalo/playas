export function LandingFooter() {
  return (
    <footer className="border-t border-border">
      {/* Thin accent top line */}
      <div className="h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent" aria-hidden="true" />
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-y-1 px-6 py-6 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span
            className="font-[family-name:var(--font-display)] font-semibold text-foreground"
            translate="no"
          >
            RAG PLAYAS
          </span>
          <span aria-hidden="true">&middot;</span>
          <span>&copy; {new Date().getFullYear()}</span>
        </span>
        <span>Jurisprudencia marítima y costera &middot; República de Colombia</span>
      </div>
    </footer>
  );
}
