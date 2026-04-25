"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";

interface ChatHeaderProps {
  onNewChat?: () => void;
  onOpenAuth?: () => void;
  onToggleSidebar?: () => void;
  sidebarOpen?: boolean;
}

export function ChatHeader({ onNewChat, onOpenAuth, onToggleSidebar, sidebarOpen }: ChatHeaderProps) {
  const { user, loading } = useAuth();

  return (
    <header className="shrink-0 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="flex h-12 items-center justify-between gap-3 px-3">
        <div className="flex min-w-0 items-center gap-1">
          {onToggleSidebar && user && (
            <button
              onClick={onToggleSidebar}
              aria-label={sidebarOpen ? "Cerrar historial" : "Ver historial"}
              aria-expanded={sidebarOpen}
              className="flex w-fit items-center rounded-md px-2 py-1 text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 md:hidden"
            >
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
                <rect width="18" height="18" x="3" y="3" rx="2" />
                <path d="M9 3v18" />
              </svg>
            </button>
          )}

          <Link
            href="/"
            className="flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-accent/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            aria-label="Volver a la página principal"
            translate="no"
          >
            <span className="font-display truncate text-sm font-semibold tracking-wide text-foreground">
              Agente de Jurisprudencia <span className="text-accent">Costera</span>
            </span>
          </Link>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {onNewChat && (
            <button
              onClick={onNewChat}
              aria-label="Iniciar nueva conversación"
              className="flex w-fit items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
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
                <path d="M12 20h9" />
                <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 19.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z" />
              </svg>
              Nuevo chat
            </button>
          )}

          {!loading && !user && (
            <button
              onClick={() => onOpenAuth?.()}
              className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Iniciar sesión
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
