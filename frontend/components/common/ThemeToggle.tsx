"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "@/components/providers/ThemeProvider";

const subscribeNoop = () => () => {};
const useIsMounted = () =>
  useSyncExternalStore(subscribeNoop, () => true, () => false);

function SunIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  );
}

function MonitorIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="20" height="14" x="2" y="3" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

const THEMES = [
  { value: "light", label: "Claro", Icon: SunIcon },
  { value: "system", label: "Sistema", Icon: MonitorIcon },
  { value: "dark", label: "Oscuro", Icon: MoonIcon },
] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useIsMounted();

  if (!mounted) return null;

  return (
    <div
      className="flex items-center gap-0.5 rounded-full border border-border bg-elevated/60 p-0.5 backdrop-blur-md"
      role="group"
      aria-label="Tema de color"
    >
      {THEMES.map(({ value, label, Icon }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          aria-label={label}
          aria-pressed={theme === value}
          className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-background ${
            theme === value
              ? "bg-surface text-accent"
              : "text-muted hover:text-foreground"
          }`}
          title={label}
        >
          <Icon />
        </button>
      ))}
    </div>
  );
}
