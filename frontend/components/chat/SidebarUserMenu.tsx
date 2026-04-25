"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";

interface SidebarUserMenuProps {
  expanded: boolean;
  open: boolean;
  userName: string;
  userEmail: string;
  userInitial: string;
  onToggle: () => void;
  onClose: () => void;
  onSignOut: () => Promise<void>;
}

export function SidebarUserMenu({
  expanded,
  open,
  userName,
  userEmail,
  userInitial,
  onToggle,
  onClose,
  onSignOut,
}: SidebarUserMenuProps) {
  useEffect(() => {
    if (!open) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      const target = event.target as Element;
      if (target.closest("[data-user-menu-root]")) return;
      onClose();
    };

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose, open]);

  return expanded ? (
    <ExpandedUserMenu
      open={open}
      userName={userName}
      userEmail={userEmail}
      userInitial={userInitial}
      onToggle={onToggle}
      onSignOut={onSignOut}
    />
  ) : (
    <CollapsedUserMenu
      open={open}
      userName={userName}
      userEmail={userEmail}
      userInitial={userInitial}
      onToggle={onToggle}
      onSignOut={onSignOut}
    />
  );
}

function ExpandedUserMenu({
  open,
  userName,
  userEmail,
  userInitial,
  onToggle,
  onSignOut,
}: Omit<SidebarUserMenuProps, "expanded" | "onClose">) {
  return (
    <div className="relative p-2" data-user-menu-root>
      <button
        type="button"
        onClick={onToggle}
        aria-label="Abrir menú de perfil"
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left transition-colors hover:bg-accent/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <UserAvatar initial={userInitial} size="md" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-semibold text-foreground">
            {userName}
          </span>
          <span className="block truncate text-[10px] text-muted">{userEmail}</span>
        </span>
        <ChevronIcon />
      </button>

      <UserMenuPopover
        open={open}
        userName={userName}
        userEmail={userEmail}
        onSignOut={onSignOut}
        positionClassName="absolute bottom-14 left-2 right-2"
      />
    </div>
  );
}

function CollapsedUserMenu({
  open,
  userName,
  userEmail,
  userInitial,
  onToggle,
  onSignOut,
}: Omit<SidebarUserMenuProps, "expanded" | "onClose">) {
  return (
    <div className="relative mt-auto pb-2" data-user-menu-root>
      <button
        type="button"
        onClick={onToggle}
        aria-label="Abrir menú de perfil"
        aria-haspopup="menu"
        aria-expanded={open}
        title={userEmail}
        className="flex h-10 w-10 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      >
        {userInitial}
      </button>

      <UserMenuPopover
        open={open}
        userName={userName}
        userEmail={userEmail}
        onSignOut={onSignOut}
        positionClassName="absolute bottom-14 left-2 w-56"
      />
    </div>
  );
}

function UserMenuPopover({
  open,
  userName,
  userEmail,
  positionClassName,
  onSignOut,
}: {
  open: boolean;
  userName: string;
  userEmail: string;
  positionClassName: string;
  onSignOut: () => Promise<void>;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          role="menu"
          className={`${positionClassName} z-50 rounded-2xl border border-border bg-surface p-2 shadow-xl shadow-foreground/10`}
          initial={{ opacity: 0, y: 6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 6, scale: 0.98 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="border-b border-border px-2 py-2">
            <p className="truncate text-sm font-semibold text-foreground">
              {userName}
            </p>
            <p className="truncate text-xs text-muted">{userEmail}</p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={onSignOut}
            className="mt-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          >
            <SignOutIcon />
            Cerrar sesión
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function UserAvatar({ initial, size }: { initial: string; size: "md" }) {
  const sizeClass = size === "md" ? "h-8 w-8" : "h-10 w-10";
  return (
    <span
      className={`flex ${sizeClass} shrink-0 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white`}
    >
      {initial}
    </span>
  );
}

function ChevronIcon() {
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
      className="shrink-0 text-muted"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function SignOutIcon() {
  return (
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
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  );
}
