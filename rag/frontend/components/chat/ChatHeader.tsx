"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";

interface ChatHeaderProps {
  onNewChat?: () => void;
  onOpenAuth?: () => void;
  onToggleSidebar?: () => void;
  sidebarOpen?: boolean;
  /** true cuando ya hay un sidebar (autenticado o invitado) mostrando estas mismas acciones */
  hideActions?: boolean;
}

const headerButtonClass =
  "inline-flex items-center rounded-full border border-border bg-background px-3.5 py-1.5 text-xs font-medium text-muted transition-colors duration-150 hover:border-border-strong hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export function ChatHeader({ onNewChat, onOpenAuth, onToggleSidebar, sidebarOpen, hideActions }: ChatHeaderProps) {
  const { user, loading } = useAuth();

  return (
    <header className="shrink-0 bg-transparent px-4">
      <div className="mx-auto flex h-12 w-full max-w-3xl items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-1">
          {onToggleSidebar && (user || hideActions) && (
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
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {!loading && !user && !hideActions && (
            <Link href="/about" className={`hidden sm:inline-flex ${headerButtonClass}`}>
              Cómo funciona
            </Link>
          )}

          {onNewChat && !hideActions && (
            <button onClick={onNewChat} aria-label="Iniciar nueva conversación" className={headerButtonClass}>
              Nuevo chat
            </button>
          )}

          {!loading && !user && !hideActions && (
            <button onClick={() => onOpenAuth?.()} className={headerButtonClass}>
              Iniciar sesión
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
