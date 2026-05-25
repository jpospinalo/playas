"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { doc, getDoc } from "firebase/firestore";
import { useAuth } from "@/components/providers/AuthProvider";
import { db } from "@/lib/firebase";
import { ThemeToggle } from "@/components/common/ThemeToggle";

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
			router.replace("/");
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

	if (loading || checkingRole) {
		return (
			<div className="flex min-h-screen items-center justify-center bg-background">
				<span className="text-sm text-muted">Verificando acceso…</span>
			</div>
		);
	}

	if (!user) return null;

	if (role !== "admin" && role !== "super-admin") {
		return (
			<div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4 text-center">
				<div className="text-5xl font-medium tracking-tight text-accent">403</div>
				<p className="text-base font-medium text-foreground">Acceso restringido</p>
				<p className="max-w-sm text-sm text-muted">
					No tienes permisos para acceder al panel de administración. Contacta
					al administrador del sistema.
				</p>
				<Link
					href="/"
					className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
				>
					Volver a ATLAS
				</Link>
			</div>
		);
	}

	const navLinks = [
		{ href: "/admin", label: "Resumen" },
		{ href: "/admin/feedback", label: "Conversaciones" },
		{ href: "/admin/message-feedback", label: "Mensajes" },
		{ href: "/admin/usuarios", label: "Usuarios" },
	];

	return (
		<div className="flex min-h-screen bg-background">
			<aside className="flex w-60 shrink-0 flex-col border-r border-border bg-elevated/60 backdrop-blur-md">
				<div className="flex h-12 items-center gap-2 px-4">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="20"
						height="20"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="1.6"
						strokeLinecap="round"
						strokeLinejoin="round"
						className="text-accent"
						aria-hidden="true"
					>
						<path d="M12 3 L20 20 L4 20 Z" opacity="0.4" />
						<path d="M12 3 L20 20" />
						<path d="M12 3 L4 20" />
						<path d="M8 14 H16" opacity="0.55" />
					</svg>
					<span
						className="text-[13px] font-medium tracking-[0.12em] text-foreground"
						translate="no"
					>
						ATLAS
					</span>
					<span className="text-[11px] font-medium uppercase tracking-[0.1em] text-subtle">
						Admin
					</span>
				</div>

				<nav className="flex flex-col gap-px px-2 py-2">
					{navLinks.map(({ href, label }) => {
						const isActive =
							href === "/admin"
								? pathname === "/admin"
								: pathname.startsWith(href);
						return (
							<Link
								key={href}
								href={href}
								className={`rounded-full px-4 py-2 text-[13.5px] transition-colors ${
									isActive
										? "bg-elevated text-foreground"
										: "text-muted hover:bg-elevated hover:text-foreground"
								}`}
							>
								{label}
							</Link>
						);
					})}
				</nav>

				<div className="mt-auto flex flex-col gap-2 border-t border-border px-3 py-3">
					<div className="flex items-center justify-between px-1">
						<span className="text-xs text-subtle">Tema</span>
						<ThemeToggle />
					</div>
					<Link
						href="/"
						className="flex items-center gap-1.5 rounded-full px-3 py-2 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground"
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
						Volver a ATLAS
					</Link>
				</div>
			</aside>

			<main className="flex-1 overflow-auto p-6 lg:p-8">{children}</main>
		</div>
	);
}
