"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "@/components/providers/AuthProvider";
import { getLastEmail } from "@/lib/auth";


function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
      <line x1="2" x2="22" y1="2" y2="22" />
    </svg>
  );
}

const inputClass =
  "w-full rounded-2xl border border-border bg-surface px-3.5 py-2.5 text-sm text-foreground placeholder:text-subtle transition-[border-color,box-shadow] duration-150 focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)] disabled:opacity-60";

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
  /** false para el gate obligatorio de inicio: oculta el botón de cerrar. Por defecto true. */
  dismissible?: boolean;
}

export function AuthModal({ open, onClose, dismissible = true }: AuthModalProps) {
  const { signIn, sessionExpiredMessage } = useAuth();
  const [email, setEmail] = useState(getLastEmail);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function resetForm() {
    setEmail(getLastEmail());
    setPassword("");
    setShowPassword(false);
    setError(null);
    setSubmitting(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);

    setSubmitting(true);
    try {
      await signIn(email, password);
      resetForm();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ocurrió un error. Intenta de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    resetForm();
    onClose();
  }

  const submitDisabled = submitting || !email || !password;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className="absolute inset-0 bg-background/70 backdrop-blur-md"
            aria-hidden="true"
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-modal-title"
            className="relative z-10 w-full max-w-sm rounded-3xl border border-border bg-elevated p-6 shadow-2xl shadow-secondary-turquoise/20"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            {dismissible && (
              <button
                onClick={handleClose}
                aria-label="Cerrar"
                className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            )}

            <div className="mb-6 text-center">
              <h2
                id="auth-modal-title"
                className="text-lg font-medium text-foreground"
              >
                Iniciar sesión
              </h2>
            </div>

            {sessionExpiredMessage && (
              <p
                role="status"
                className="mb-3.5 rounded-2xl border border-accent/30 bg-accent-soft px-3.5 py-2.5 text-sm text-accent"
              >
                {sessionExpiredMessage}
              </p>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
              <div>
                <label
                  htmlFor="auth-email"
                  className="mb-1.5 block text-xs font-medium text-muted"
                >
                  Correo electrónico
                </label>
                <input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="correo@ejemplo.com"
                  className={inputClass}
                  disabled={submitting}
                />
              </div>

              <div>
                <label
                  htmlFor="auth-password"
                  className="mb-1.5 block text-xs font-medium text-muted"
                >
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    id="auth-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className={`${inputClass} pr-11`}
                    disabled={submitting}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-subtle transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    tabIndex={-1}
                  >
                    <EyeIcon open={showPassword} />
                  </button>
                </div>
              </div>

              <AnimatePresence>
                {error && (
                  <motion.p
                    role="alert"
                    className="rounded-2xl border border-danger/30 bg-danger-bg px-3.5 py-2.5 text-sm text-danger"
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    {error}
                  </motion.p>
                )}
              </AnimatePresence>

              <button
                type="submit"
                disabled={submitDisabled}
                className="mt-2 w-full rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-elevated disabled:cursor-not-allowed disabled:opacity-45"
              >
                {submitting ? "Procesando…" : "Iniciar sesión"}
              </button>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
