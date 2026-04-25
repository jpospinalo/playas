"use client";

import { useEffect, useState } from "react";
import {
  type AdminUserRow,
  createAdminUser,
  listAdminUsers,
  updateAdminUserPassword,
} from "@/lib/api";

const ROLE_STYLES: Record<string, string> = {
  "super-admin": "bg-navy/10 text-navy border-navy/20",
  admin: "bg-accent/10 text-accent border-accent/20",
  user: "bg-border/60 text-muted border-border",
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
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${style}`}
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
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground">
            Usuarios
          </h1>
          <p className="mt-1 text-sm text-muted">
            {loading
              ? "Cargando…"
              : `${users.length} usuario${users.length !== 1 ? "s" : ""} registrado${users.length !== 1 ? "s" : ""}`}
          </p>
          <p className="mt-0.5 text-xs text-muted">
            Los roles se asignan manualmente desde la consola de Firebase.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-accent px-3 py-2 text-xs font-medium text-white hover:bg-accent/90 focus:outline-none focus:ring-2 focus:ring-accent"
        >
          Crear usuario
        </button>
      </div>

      {banner ? (
        <div className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-2 text-sm text-accent">
          {banner}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
          Error: {error}
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-16">
          <span className="text-sm text-muted">Cargando usuarios…</span>
        </div>
      ) : users.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center text-sm text-muted">
          No hay usuarios registrados.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead>
                <tr className="bg-background">
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                    Email
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                    Nombre
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                    Rol
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                    Registro
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.map((u) => (
                  <tr key={u.uid} className="hover:bg-background/50 transition-colors">
                    <td className="px-4 py-3 text-xs text-foreground">
                      <span className="font-mono">{u.email}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">
                      {u.displayName ?? <span className="italic text-border">—</span>}
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
                        className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground hover:bg-accent/5 hover:border-accent/40"
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
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

  const inputClass =
    "mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent";

  return (
    <ModalShell onClose={onClose}>
      <h2 className="text-lg font-semibold text-foreground">Crear usuario</h2>
      <p className="mt-1 text-xs text-muted">
        El usuario se creará con rol <code className="font-mono">user</code>.
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <label className="block text-xs font-medium text-muted">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
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
              className={`${inputClass} pr-10`}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPwd((v) => !v)}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-muted hover:text-foreground"
              aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
            >
              {showPwd ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </button>
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
            className={`${inputClass} ${confirm && confirm !== password ? "border-red-400 focus:ring-red-400" : ""}`}
          />
          {confirm && confirm !== password ? (
            <span className="mt-0.5 block text-[11px] text-red-500">No coincide.</span>
          ) : null}
        </label>
        <label className="block text-xs font-medium text-muted">
          Nombre <span className="text-border">(opcional)</span>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </label>

        {err ? (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
            {err}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-background/60 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-accent px-3 py-2 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
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

  const inputClass =
    "mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent";

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
      <h2 className="text-lg font-semibold text-foreground">Cambiar contraseña</h2>
      <p className="mt-1 text-xs text-muted">
        Para <span className="font-mono text-foreground">{target.email}</span>. El
        cambio es inmediato y no envía notificaciones.
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
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
              className={`${inputClass} pr-10`}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPwd((v) => !v)}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-muted hover:text-foreground"
              aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
            >
              {showPwd ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </button>
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
            className={`${inputClass} ${confirm && confirm !== password ? "border-red-400 focus:ring-red-400" : ""}`}
          />
          {confirm && confirm !== password ? (
            <span className="mt-0.5 block text-[11px] text-red-500">No coincide.</span>
          ) : null}
        </label>

        {err ? (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
            {err}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-background/60 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-accent px-3 py-2 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          >
            {submitting ? "Actualizando…" : "Actualizar"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
