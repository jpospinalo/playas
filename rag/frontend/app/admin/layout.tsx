"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { ThemeToggle } from "@/components/common/ThemeToggle";

export default function AdminLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	const { user, role, loading } = useAuth();
	const router = useRouter();
	const pathname = usePathname();

	useEffect(() => {
		if (!loading && !user) {
			router.replace("/");
		}
	}, [user, loading, router]);

	if (loading) {
		return (
			<main
				id="main-content"
				className="flex min-h-screen items-center justify-center bg-background"
			>
				<span className="text-sm text-muted">Verificando acceso…</span>
			</main>
		);
	}

	if (!user || loading) return null;

	if (role !== "admin" && role !== "super-admin") {
		return (
			<main
				id="main-content"
				className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4 text-center"
			>
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
			</main>
		);
	}

	const navLinks = [
		{ href: "/admin", label: "Resumen" },
		{ href: "/admin/feedback", label: "Conversaciones" },
		{ href: "/admin/message-feedback", label: "Mensajes" },
		{ href: "/admin/usuarios", label: "Usuarios" },
	];

	return (
		// El `<aside>` de administración no tiene panel off-canvas propio (a
		// diferencia del sidebar del chat): en viewports angostos usa una
		// navegación superior compacta y desplazable horizontalmente
		// (`< md`); a partir de `md:` vuelve a ser el riel vertical.
		<div className="flex min-h-screen flex-col bg-background md:flex-row">
			<aside className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-elevated/60 px-2 py-2 backdrop-blur-md md:w-60 md:flex-col md:items-stretch md:gap-0 md:overflow-visible md:border-b-0 md:border-r md:px-0 md:py-0">
				<div className="flex h-12 shrink-0 items-center gap-2 px-2 md:px-4">
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
					<span className="hidden text-[11px] font-medium uppercase tracking-[0.1em] text-subtle md:inline">
						Admin
					</span>
				</div>

				<nav className="flex shrink-0 items-center gap-px md:flex-col md:items-stretch md:px-2 md:py-2">
					{navLinks.map(({ href, label }) => {
						const isActive =
							href === "/admin"
								? pathname === "/admin"
								: pathname.startsWith(href);
						return (
							<Link
								key={href}
								href={href}
								aria-current={isActive ? "page" : undefined}
								className={`whitespace-nowrap rounded-full px-4 py-2 text-[13.5px] transition-colors ${
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

				<div className="ml-auto flex shrink-0 items-center gap-2 md:ml-0 md:mt-auto md:flex-col md:items-stretch md:gap-2 md:border-t md:border-border md:px-3 md:py-3">
					<div className="flex items-center gap-2 md:justify-between md:px-1">
						<span className="hidden text-xs text-subtle md:inline">Tema</span>
						<ThemeToggle />
					</div>
					<Link
						href="/"
						aria-label="Volver a ATLAS"
						className="flex items-center gap-1.5 rounded-full px-2 py-1.5 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground md:px-3 md:py-2"
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
						<span className="hidden md:inline">Volver a ATLAS</span>
					</Link>
				</div>
			</aside>

			<main id="main-content" className="flex-1 overflow-auto p-6 lg:p-8">
				{children}
			</main>
		</div>
	);
}
