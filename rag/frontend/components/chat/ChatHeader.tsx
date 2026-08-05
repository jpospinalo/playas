"use client";

interface ChatHeaderProps {
  onToggleSidebar?: () => void;
  sidebarOpen?: boolean;
}

export function ChatHeader({ onToggleSidebar, sidebarOpen }: ChatHeaderProps) {
  return (
    <header className="shrink-0 bg-transparent px-4">
      <div className="mx-auto flex h-12 w-full max-w-3xl items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-1">
          {onToggleSidebar && (
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
      </div>
    </header>
  );
}
