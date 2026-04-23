"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "@/components/providers/AuthProvider";

// Traducción de códigos de error de Firebase Auth al español
function translateFirebaseError(code: string): string {
  const messages: Record<string, string> = {
    "auth/user-not-found": "No existe una cuenta con ese correo.",
    "auth/wrong-password": "Contraseña incorrecta.",
    "auth/invalid-credential": "Correo o contraseña incorrectos.",
    "auth/email-already-in-use": "Este correo ya está registrado.",
    "auth/weak-password": "La contraseña debe tener al menos 6 caracteres.",
    "auth/invalid-email": "El formato del correo no es válido.",
    "auth/too-many-requests": "Demasiados intentos fallidos. Intenta más tarde.",
    "auth/network-request-failed": "Error de red. Verifica tu conexión.",
    "auth/user-disabled": "Esta cuenta ha sido deshabilitada.",
  };
  return messages[code] ?? "Ocurrió un error. Intenta de nuevo.";
}

interface AuthModalProps {
  /** Muestra el modal */
  open: boolean;
  /** Modo: recomendación al entrar a /chat o acción explícita del usuario */
  mode?: "recommendation" | "explicit";
  onClose: () => void;
}

type Tab = "login" | "register";

export function AuthModal({ open, mode = "explicit", onClose }: AuthModalProps) {
  const { signIn, signUp } = useAuth();
  const [tab, setTab] = useState<Tab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function resetForm() {
    setEmail("");
    setPassword("");
    setError(null);
    setSubmitting(false);
  }

  function handleTabChange(next: Tab) {
    setTab(next);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      if (tab === "login") {
        await signIn(email, password);
      } else {
        await signUp(email, password);
      }
      resetForm();
      onClose();
    } catch (err: unknown) {
      const code = (err as { code?: string }).code ?? "";
      setError(translateFirebaseError(code));
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    resetForm();
    onClose();
  }

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
          {/* Fondo oscuro */}
          <motion.div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={handleClose}
            aria-hidden="true"
          />

          {/* Tarjeta */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-modal-title"
            className="relative z-10 w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-xl"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* Botón cerrar */}
            <button
              onClick={handleClose}
              aria-label="Cerrar"
              className="absolute right-4 top-4 rounded-md p-1 text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
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
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>

            {/* Encabezado */}
            {mode === "recommendation" ? (
              <div className="mb-5">
                <h2
                  id="auth-modal-title"
                  className="font-[family-name:var(--font-display)] text-lg font-semibold text-foreground"
                >
                  Guarda tu historial
                </h2>
                <p className="mt-1 text-sm text-muted">
                  Inicia sesión para conservar tus conversaciones y acceder a
                  ellas desde cualquier dispositivo.
                </p>
              </div>
            ) : (
              <h2
                id="auth-modal-title"
                className="mb-5 font-[family-name:var(--font-display)] text-lg font-semibold text-foreground"
              >
                {tab === "login" ? "Iniciar sesión" : "Crear cuenta"}
              </h2>
            )}

            {/* Tabs */}
            <div
              role="tablist"
              aria-label="Modo de acceso"
              className="mb-5 flex gap-1 rounded-lg border border-border bg-background p-1"
            >
              {(["login", "register"] as Tab[]).map((t) => (
                <button
                  key={t}
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => handleTabChange(t)}
                  className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    tab === t
                      ? "bg-surface text-foreground shadow-sm"
                      : "text-muted hover:text-foreground"
                  }`}
                >
                  {t === "login" ? "Iniciar sesión" : "Registrarse"}
                </button>
              ))}
            </div>

            {/* Formulario */}
            <form onSubmit={handleSubmit} noValidate className="space-y-3">
              <div>
                <label
                  htmlFor="auth-email"
                  className="mb-1 block text-xs font-medium text-muted"
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
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60"
                  disabled={submitting}
                />
              </div>

              <div>
                <label
                  htmlFor="auth-password"
                  className="mb-1 block text-xs font-medium text-muted"
                >
                  Contraseña
                </label>
                <input
                  id="auth-password"
                  type="password"
                  autoComplete={
                    tab === "login" ? "current-password" : "new-password"
                  }
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={
                    tab === "register" ? "Mínimo 6 caracteres" : "••••••••"
                  }
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60"
                  disabled={submitting}
                />
              </div>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.p
                    role="alert"
                    className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
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
                disabled={submitting || !email || !password}
                className="mt-1 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:opacity-50"
              >
                {submitting
                  ? "Procesando…"
                  : tab === "login"
                    ? "Iniciar sesión"
                    : "Crear cuenta"}
              </button>
            </form>

            {/* Continuar sin cuenta */}
            <button
              onClick={handleClose}
              className="mt-4 w-full text-center text-xs text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:underline"
            >
              Continuar sin cuenta
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
