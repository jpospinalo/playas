"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { doc, getDoc } from "firebase/firestore";
import { useAuth } from "@/components/providers/AuthProvider";
import { db } from "@/lib/firebase";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [role, setRole] = useState<string | null>(null);
  const [checkingRole, setCheckingRole] = useState(true);

  useEffect(() => {
    if (loading) return;

    if (!user) {
      router.replace("/chat");
      return;
    }

    async function fetchRole() {
      if (!user) return;
      try {
        const snap = await getDoc(doc(db, "users", user.uid));
        const r = snap.exists() ? (snap.data()?.role ?? "user") : "user";
        setRole(r);
      } catch {
        setRole("user");
      } finally {
        setCheckingRole(false);
      }
    }

    fetchRole();
  }, [user, loading, router]);

  // Mientras resuelve auth o rol
  if (loading || checkingRole) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <span className="text-sm text-muted">Verificando acceso…</span>
      </div>
    );
  }

  // Sin sesión (ya redirige, pero por si acaso)
  if (!user) return null;

  // Autenticado pero sin rol admin
  if (role !== "admin" && role !== "super-admin") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4 text-center">
        <div className="text-4xl font-bold text-accent">403</div>
        <p className="text-foreground font-semibold">Acceso restringido</p>
        <p className="text-sm text-muted max-w-sm">
          No tienes permisos para acceder al panel de administración. Contacta al
          administrador del sistema.
        </p>
        <Link
          href="/chat"
          className="mt-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 transition-opacity"
        >
          Volver al chat
        </Link>
      </div>
    );
  }

  const navLinks = [
    { href: "/admin", label: "Resumen" },
    { href: "/admin/feedback", label: "Feedback" },
    { href: "/admin/usuarios", label: "Usuarios" },
  ];

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar nav */}
      <aside className="w-52 shrink-0 border-r border-border bg-surface flex flex-col">
        <div className="px-5 py-4 border-b border-border">
          <span className="font-[family-name:var(--font-display)] text-sm font-semibold text-foreground">
            Panel <span className="text-accent">Admin</span>
          </span>
        </div>
        <nav className="flex flex-col gap-0.5 px-2 py-3">
          {navLinks.map(({ href, label }) => {
            const isActive =
              href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-accent/10 text-accent font-medium"
                    : "text-muted hover:text-foreground hover:bg-border/40"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto px-2 py-3 border-t border-border">
          <Link
            href="/chat"
            className="flex items-center gap-1.5 rounded-md px-3 py-2 text-xs text-muted hover:text-foreground transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="12"
              height="12"
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
            Volver al chat
          </Link>
        </div>
      </aside>

      {/* Contenido */}
      <main className="flex-1 overflow-auto p-6 lg:p-8">{children}</main>
    </div>
  );
}
