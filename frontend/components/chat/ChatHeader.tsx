"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { AtlasWordmark } from "@/components/common/AtlasWordmark";

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
            className="rounded-md px-2 py-1 transition-opacity duration-150 hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            aria-label="ATLAS — inicio"
          >
            <AtlasWordmark className="text-base" />
          </Link>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <Link
            href="/about"
            className="hidden items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-muted transition-colors duration-150 hover:bg-subtle hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:flex"
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
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
            Cómo funciona
          </Link>

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
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
                <circle cx="9" cy="7" r="4" />
                <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
                <path d="M16 11h6" />
                <path d="M19 8v6" />
              </svg>
              Iniciar sesión
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
