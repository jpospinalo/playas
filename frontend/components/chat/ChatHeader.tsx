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
  const { user, loading, signOut } = useAuth();

  // Inicial del email para el avatar
  const initial = user?.email?.[0]?.toUpperCase() ?? "";

  return (
    <header className="shrink-0 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto grid max-w-3xl grid-cols-[1fr_auto_1fr] items-center px-4 py-3">
        {/* Izquierda: toggle sidebar + volver al inicio */}
        <div className="-ml-1 flex items-center gap-0.5">
          {onToggleSidebar && user && (
            <button
              onClick={onToggleSidebar}
              aria-label={sidebarOpen ? "Cerrar historial" : "Ver historial"}
              aria-expanded={sidebarOpen}
              className="flex w-fit items-center rounded-md px-2 py-1 text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
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
            aria-label="Volver a la página principal"
            className="flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
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
              <path d="m15 18-6-6 6-6" />
            </svg>
            Inicio
          </Link>
        </div>

        {/* Centro: título */}
        <div className="flex flex-col items-center gap-0.5">
          <span
            className="font-[family-name:var(--font-display)] text-center text-sm font-semibold tracking-wide text-foreground"
            translate="no"
          >
            Agente de Jurisprudencia <span className="text-accent">Costera</span>
          </span>
        </div>

        {/* Derecha: nuevo chat + auth */}
        <div className="-mr-1 ml-auto flex items-center gap-1">
          {onNewChat && (
            <button
              onClick={onNewChat}
              aria-label="Iniciar nueva conversación"
              className="flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
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

          {/* Estado de autenticación */}
          {!loading && (
            <>
              {user ? (
                <div className="flex items-center gap-1.5">
                  {/* Avatar con inicial */}
                  <span
                    aria-label={`Sesión iniciada como ${user.email}`}
                    title={user.email ?? ""}
                    className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/10 text-[10px] font-semibold text-accent"
                  >
                    {initial}
                  </span>
                  <button
                    onClick={() => signOut()}
                    aria-label="Cerrar sesión"
                    title="Cerrar sesión"
                    className="rounded-md px-2 py-1 text-xs text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                  >
                    Salir
                  </button>
                </div>
              ) : (
                <button
                  onClick={onOpenAuth}
                  className="rounded-md px-2 py-1 text-xs text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                >
                  Iniciar sesión
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </header>
  );
}
