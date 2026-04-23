"use client";

import { useEffect, useState } from "react";
import {
  collection,
  getDocs,
  orderBy,
  query,
  where,
} from "firebase/firestore";
import { db } from "@/lib/firebase";

interface UserRow {
  uid: string;
  email: string;
  displayName: string | null;
  role: string;
  createdAt: Date | null;
  conversationCount: number;
}

const ROLE_STYLES: Record<string, string> = {
  "super-admin": "bg-navy/10 text-navy border-navy/20",
  admin: "bg-accent/10 text-accent border-accent/20",
  user: "bg-border/60 text-muted border-border",
};

function RoleBadge({ role }: { role: string }) {
  const style = ROLE_STYLES[role] ?? ROLE_STYLES.user;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${style}`}
    >
      {role}
    </span>
  );
}

function formatDate(d: Date | null): string {
  if (!d) return "—";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" }).format(d);
}

export default function UsuariosPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        // Leer colección users desde Firestore (las reglas permiten list si es admin)
        const usersSnap = await getDocs(
          query(collection(db, "users"), orderBy("createdAt", "desc"))
        );

        const rows: UserRow[] = [];
        for (const snap of usersSnap.docs) {
          const data = snap.data();
          const uid = snap.id;

          // Contar conversaciones del usuario
          let conversationCount = 0;
          try {
            const convsSnap = await getDocs(
              query(collection(db, "conversations"), where("userId", "==", uid))
            );
            conversationCount = convsSnap.size;
          } catch {
            // Si falla el conteo, seguimos sin bloquear la carga
          }

          rows.push({
            uid,
            email: data.email ?? "",
            displayName: data.displayName ?? null,
            role: data.role ?? "user",
            createdAt: data.createdAt?.toDate?.() ?? null,
            conversationCount,
          });
        }

        setUsers(rows);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error desconocido");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground">
          Usuarios
        </h1>
        <p className="mt-1 text-sm text-muted">
          {loading ? "Cargando…" : `${users.length} usuario${users.length !== 1 ? "s" : ""} registrado${users.length !== 1 ? "s" : ""}`}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          Los roles se asignan manualmente desde la consola de Firebase.
        </p>
      </div>

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
                    Conversaciones
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
                    <td className="whitespace-nowrap px-4 py-3 text-right text-xs text-muted tabular-nums">
                      {u.conversationCount}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
