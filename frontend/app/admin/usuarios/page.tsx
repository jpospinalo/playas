"use client";

import { useEffect, useState } from "react";
import {
  type AdminUserRow,
  createAdminUser,
  listAdminUsers,
  updateAdminUserPassword,
} from "@/lib/api";

const ROLE_STYLES: Record<string, string> = {
  "super-admin": "bg-foreground/8 text-foreground border-foreground/15",
  admin: "bg-accent-soft text-accent border-accent/20",
  user: "bg-surface text-muted border-border",
};

const ROLE_LABELS: Record<string, string> = {
  "super-admin": "Super Admin",
  admin: "Administrador",
  user: "Usuario",
};

function RoleBadge({ role }: { role: string }) {
  const style = ROLE_STYLES[role] ?? ROLE_STYLES.user;
  const label = ROLE_LABELS[role] ?? role;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${style}`}
    >
      {label}
    </span>
  );
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" }).format(d);
}

const modalInputClass =
  "mt-1 block w-full rounded-2xl border border-border bg-surface px-3.5 py-2.5 text-sm text-foreground transition-[border-color,box-shadow] duration-150 focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]";

const modalInputMonoClass =
  "mt-1 block w-full rounded-2xl border border-border bg-surface px-3.5 py-2.5 font-mono text-sm text-foreground transition-[border-color,box-shadow] duration-150 focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]";

export default function UsuariosPage() {
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [pwdTarget, setPwdTarget] = useState<AdminUserRow | null>(null);

  async function refresh() {
    try {
      const items = await listAdminUsers();
      setUsers(items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function showBanner(msg: string) {
    setBanner(msg);
    setTimeout(() => setBanner(null), 4000);
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-medium tracking-tight text-foreground" style={{ letterSpacing: "-0.02em" }}>
            Usuarios
          </h1>
          <p className="mt-1.5 text-sm text-muted">
            {loading
              ? "Cargando…"
              : `${users.length} usuario${users.length !== 1 ? "s" : ""} registrado${users.length !== 1 ? "s" : ""}`}
          </p>
          <p className="mt-1 text-xs text-subtle">
            Los roles se asignan manualmente desde la consola de Firebase.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-medium text-accent-fg transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          Crear usuario
        </button>
      </div>

      {banner ? (
        <div className="rounded-full border border-accent/30 bg-accent-soft px-4 py-2 text-sm text-accent">
          {banner}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-border bg-elevated/40 p-6 text-sm text-muted">
          Error: {error}
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-16">
          <span className="text-sm text-muted">Cargando usuarios…</span>
        </div>
      ) : users.length === 0 ? (
        <div className="rounded-2xl border border-border bg-elevated/40 p-8 text-center text-sm text-muted">
          No hay usuarios registrados.
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-elevated/40 backdrop-blur-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead>
                <tr className="bg-surface/50">
                  <th className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Email</th>
                  <th className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Nombre</th>
                  <th className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Rol</th>
                  <th className="px-4 py-3 text-left text-[11px] font-medium text-subtle">Registro</th>
                  <th className="px-4 py-3 text-right text-[11px] font-medium text-subtle">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.map((u) => (
                  <tr key={u.uid} className="transition-colors hover:bg-surface/40">
                    <td className="px-4 py-3 text-xs text-foreground">
                      <span className="font-mono">{u.email}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">
                      {u.displayName ?? <span className="italic text-subtle">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-muted tabular-nums">
                      {formatDate(u.createdAt)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setPwdTarget(u)}
                        className="rounded-full border border-border px-3 py-1 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        Cambiar contraseña
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {createOpen ? (
        <CreateUserModal
          onClose={() => setCreateOpen(false)}
          onCreated={(u) => {
            setUsers((prev) => [u, ...prev]);
            setCreateOpen(false);
            showBanner(`Usuario ${u.email} creado.`);
          }}
        />
      ) : null}

      {pwdTarget ? (
        <ChangePasswordModal
          target={pwdTarget}
          onClose={() => setPwdTarget(null)}
          onUpdated={() => {
            const email = pwdTarget.email;
            setPwdTarget(null);
            showBanner(`Contraseña actualizada para ${email}.`);
          }}
        />
      ) : null}
    </div>
  );
}

function ModalShell({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-3xl border border-border bg-elevated p-6 shadow-2xl shadow-black/40"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function PasswordToggleButton({
  visible,
  onToggle,
}: {
  visible: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      tabIndex={-1}
      onClick={onToggle}
      className="absolute inset-y-0 right-0 flex items-center px-3 text-subtle transition-colors hover:text-foreground"
      aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
    >
      {visible ? (
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      )}
    </button>
  );
}

function CreateUserModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (u: AdminUserRow) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setErr("Las contraseñas no coinciden.");
      return;
    }
    setErr(null);
    setSubmitting(true);
    try {
      const u = await createAdminUser({
        email: email.trim(),
        password,
        displayName: displayName.trim() || null,
      });
      onCreated(u);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error desconocido");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell onClose={onClose}>
      <h2 className="text-lg font-medium text-foreground">Crear usuario</h2>
      <p className="mt-1.5 text-xs text-muted">
        El usuario se creará con rol <code className="font-mono text-foreground">user</code>.
      </p>
      <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
        <label className="block text-xs font-medium text-muted">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={modalInputClass}
          />
        </label>
        <div className="block text-xs font-medium text-muted">
          Contraseña
          <div className="relative mt-1">
            <input
              type={showPwd ? "text" : "password"}
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${modalInputMonoClass} pr-11`}
            />
            <PasswordToggleButton visible={showPwd} onToggle={() => setShowPwd((v) => !v)} />
          </div>
        </div>
        <label className="block text-xs font-medium text-muted">
          Confirmar contraseña
          <input
            type={showPwd ? "text" : "password"}
            required
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={`${modalInputMonoClass} ${confirm && confirm !== password ? "border-danger focus:border-danger focus:shadow-[0_0_0_3px_var(--danger-bg)]" : ""}`}
          />
          {confirm && confirm !== password ? (
            <span className="mt-1 block text-[11px] text-danger">No coincide.</span>
          ) : null}
        </label>
        <label className="block text-xs font-medium text-muted">
          Nombre <span className="text-subtle">(opcional)</span>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={modalInputClass}
          />
        </label>

        {err ? (
          <div className="rounded-2xl border border-danger/30 bg-danger-bg px-3.5 py-2.5 text-xs text-danger">
            {err}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-full px-4 py-2 text-xs font-medium text-muted transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-full bg-accent px-4 py-2 text-xs font-medium text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-elevated"
          >
            {submitting ? "Creando…" : "Crear"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function ChangePasswordModal({
  target,
  onClose,
  onUpdated,
}: {
  target: AdminUserRow;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setErr("Las contraseñas no coinciden.");
      return;
    }
    setErr(null);
    setSubmitting(true);
    try {
      await updateAdminUserPassword(target.uid, password);
      onUpdated();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error desconocido");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell onClose={onClose}>
      <h2 className="text-lg font-medium text-foreground">Cambiar contraseña</h2>
      <p className="mt-1.5 text-xs text-muted">
        Para <span className="font-mono text-foreground">{target.email}</span>. El cambio
        es inmediato y no envía notificaciones.
      </p>
      <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
        <div className="block text-xs font-medium text-muted">
          Nueva contraseña
          <div className="relative mt-1">
            <input
              type={showPwd ? "text" : "password"}
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              className={`${modalInputMonoClass} pr-11`}
            />
            <PasswordToggleButton visible={showPwd} onToggle={() => setShowPwd((v) => !v)} />
          </div>
        </div>
        <label className="block text-xs font-medium text-muted">
          Confirmar contraseña
          <input
            type={showPwd ? "text" : "password"}
            required
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={`${modalInputMonoClass} ${confirm && confirm !== password ? "border-danger focus:border-danger focus:shadow-[0_0_0_3px_var(--danger-bg)]" : ""}`}
          />
          {confirm && confirm !== password ? (
            <span className="mt-1 block text-[11px] text-danger">No coincide.</span>
          ) : null}
        </label>

        {err ? (
          <div className="rounded-2xl border border-danger/30 bg-danger-bg px-3.5 py-2.5 text-xs text-danger">
            {err}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-full px-4 py-2 text-xs font-medium text-muted transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-full bg-accent px-4 py-2 text-xs font-medium text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-elevated"
          >
            {submitting ? "Actualizando…" : "Actualizar"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
